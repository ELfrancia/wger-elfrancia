#  This file is part of wger Workout Manager <https://github.com/wger-project>.
#  Copyright (C) 2013 - 2021 wger Team
#
#  wger Workout Manager is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  wger Workout Manager is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Signal handlers for the trophies app.

These signals trigger statistics updates and trophy evaluations
when workouts are logged, edited, or deleted.
"""

# Standard Library
import logging
import threading

# Django
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models.signals import (
    post_delete,
    post_save,
)
from django.dispatch import receiver

# wger
from wger.manager.models import (
    WorkoutLog,
    WorkoutSession,
)
from wger.trophies.checkers.registry import CheckerRegistry
from wger.trophies.models.trophy import Trophy
from wger.trophies.models.user_trophy import UserTrophy
from wger.trophies.services import UserStatisticsService
from wger.trophies.services.trophy import TrophyService
from wger.trophies.tasks import evaluate_user_trophies_task
from wger.utils.helpers import disable_for_loaddata


logger = logging.getLogger(__name__)


def _deletion_originates_from_user(origin) -> bool:
    """
    True if this delete is part of removing a User account.

    During a user deletion the statistics row is cascade-deleted too;
    recreating it from a workout-deletion signal would leave an orphan row
    and break the transaction's foreign key check at COMMIT.
    """
    return isinstance(origin, User) or getattr(origin, 'model', None) is User


_pending_eval = set()
_pending_stats = set()
_pending_lock = threading.Lock()


def _run_stats_recalc(user_id: int):
    try:
        user = User.objects.get(id=user_id)
        UserStatisticsService.update_statistics(user)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f'Error recalculating statistics for user {user_id}: {e}')
    finally:
        with _pending_lock:
            _pending_stats.discard(user_id)


def _schedule_stats_recalc(user_id: int):
    """
    Deferred, deduped full statistics recalculation (used for log edits).

    An auto-save snapshot can update dozens of existing sets in one request;
    without this each one would run a full recalculation inside the transaction.
    """
    with _pending_lock:
        if user_id in _pending_stats:
            return
        _pending_stats.add(user_id)
    transaction.on_commit(
        lambda: threading.Thread(
            target=_run_stats_recalc, args=(user_id,), daemon=True
        ).start()
    )


def _run_trophy_evaluation(user_id: int):
    try:
        user = User.objects.get(id=user_id)
        TrophyService.evaluate_all_trophies(user)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f'Error evaluating trophies for user {user_id}: {e}')
    finally:
        with _pending_lock:
            _pending_eval.discard(user_id)


def _trigger_trophy_evaluation(user_id: int):
    """
    Schedule a full trophy evaluation for a user, after the current DB
    transaction commits and off the request thread.

    The full evaluation loops over every active trophy and each checker runs
    its own aggregation queries, so it must never run inside the workout-logging
    transaction (it would serialize SQLite writes for the whole request). It is
    also deduped per user: many ``session.save()`` / log writes in one request
    collapse into a single evaluation.
    """
    with _pending_lock:
        if user_id in _pending_eval:
            return
        _pending_eval.add(user_id)

    if settings.WGER_SETTINGS['USE_CELERY']:
        def _dispatch():
            try:
                evaluate_user_trophies_task.delay(user_id)
            finally:
                with _pending_lock:
                    _pending_eval.discard(user_id)
        transaction.on_commit(_dispatch)
    else:
        transaction.on_commit(
            lambda: threading.Thread(
                target=_run_trophy_evaluation, args=(user_id,), daemon=True
            ).start()
        )


@receiver(post_save, sender=WorkoutLog)
@disable_for_loaddata
def workout_log_saved(sender, instance: WorkoutLog, created: bool, **kwargs):
    """
    Handle WorkoutLog save events.

    Updates user statistics when a new workout log is created.
    For edits, triggers a full recalculation to ensure accuracy.
    Then triggers trophy evaluation.
    """
    if not instance.user_id:
        return

    try:
        if created:
            # New log - incremental update
            UserStatisticsService.increment_workout(
                user=instance.user,
                workout_log=instance,
            )

            # Personal Record award (respect the same skip rules as full evaluation)
            if not TrophyService.should_skip_user(instance.user):
                trophy = Trophy.objects.get(name='Personal Record', is_active=True)
                checker = CheckerRegistry.create_checker(instance.user, trophy)
                checker.params = {'log': instance}
                existing = UserTrophy.objects.filter(
                    user=instance.user, trophy=trophy, context_data__log_id=str(instance.id)
                ).exists()
                if not existing and checker and checker.check():
                    context = checker.get_context_data()
                    TrophyService.award_trophy(
                        instance.user, trophy, progress=100.0, context_data=context
                    )
                    # Expose the fresh PR to the request so the workout UI can
                    # show a celebratory toast (see wger.manager.views.workout).
                    instance._pr_awarded = context

        else:
            # Edited log - full recalculation, deferred off the request/transaction
            _schedule_stats_recalc(instance.user_id)

        # NOTE: the full trophy evaluation is intentionally NOT triggered here.
        # It runs once per workout on session finish (workout_session_saved),
        # off the request transaction. Per-set PRs are handled inline above.
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f'Error updating statistics for user {instance.user_id}: {e}', exc_info=True)


@receiver(post_delete, sender=WorkoutLog)
def workout_log_deleted(sender, instance: WorkoutLog, origin=None, **kwargs):
    """
    Handle WorkoutLog delete events.

    Triggers full statistics recalculation when a log is deleted.
    """
    if not instance.user_id:
        return

    if _deletion_originates_from_user(origin):
        return

    try:
        UserStatisticsService.handle_workout_deletion(instance.user)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(
            f'Error updating statistics after deletion for user {instance.user_id}: {e}',
            exc_info=True,
        )


@receiver(post_save, sender=WorkoutSession)
@disable_for_loaddata
def workout_session_saved(sender, instance: WorkoutSession, created: bool, **kwargs):
    """
    Handle WorkoutSession save events.

    Updates user statistics when a workout session is created or updated.
    This captures session-level data like start/end times.
    Then triggers trophy evaluation.
    """
    if not instance.user_id:
        return

    try:
        # New or updated session - keep session-level stats (times, counts) fresh
        UserStatisticsService.increment_workout(
            user=instance.user,
            session=instance,
        )

        # Full trophy evaluation only when a workout is actually completed.
        # This is the single place per workout where every trophy is checked;
        # per-set logging no longer triggers it (perf).
        if getattr(instance, 'status', None) == 'finished':
            _trigger_trophy_evaluation(instance.user_id)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(f'Error updating statistics for session {instance.id}: {e}', exc_info=True)


@receiver(post_delete, sender=WorkoutSession)
def workout_session_deleted(sender, instance: WorkoutSession, origin=None, **kwargs):
    """
    Handle WorkoutSession delete events.

    Triggers full statistics recalculation when a session is deleted.
    """
    if not instance.user_id:
        return

    if _deletion_originates_from_user(origin):
        return

    try:
        UserStatisticsService.handle_workout_deletion(instance.user)
    except User.DoesNotExist:
        pass
    except Exception as e:
        logger.error(
            f'Error updating statistics after session deletion for user {instance.user_id}: {e}',
            exc_info=True,
        )
