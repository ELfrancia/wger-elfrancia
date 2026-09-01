# -*- coding: utf-8 -*-
import datetime

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import Day, WorkoutSession, WorkoutLog


class WorkoutDiscardTestCase(WgerTestCase):
    """
    Regression coverage for empty "test" workout sessions being persisted and
    for 'Interrompi e Scarta' leaving a saved session behind.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.client.force_login(self.user)
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        self.routine.user = self.user
        self.routine.save()
        profile = self.user.userprofile
        profile.onboarding_completed = True
        profile.save()
        self.url = reverse(
            'manager:day:overview',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )

    def _log_a_set(self):
        slot = self.day.slots.first()
        self.client.post(self.url, {
            'action': 'complete_exercise',
            'slot_id': slot.id,
        })

    # -- autosave must never persist anything -----------------------------

    def test_autosave_on_fresh_workout_creates_no_session(self):
        self.client.get(self.url)
        before = WorkoutSession.objects.count()
        resp = self.client.post(self.url, {
            'action': 'auto_save_snapshot',
            'snapshot_payload': '{"elapsed_seconds": 900, "completed_sets": []}',
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(WorkoutSession.objects.count(), before)
        self.assertFalse(
            WorkoutSession.objects.filter(user=self.user, day=self.day).exists()
        )

    def test_autosave_creates_no_workout_logs(self):
        slot = self.day.slots.first()
        entry = slot.entries.first()
        before = WorkoutLog.objects.count()
        self.client.post(self.url, {
            'action': 'auto_save_snapshot',
            'snapshot_payload': (
                '{"elapsed_seconds": 900, "completed_sets": '
                '[{"slot_entry_id": %d, "exercise_id": %d, "repetitions": 8, "weight": 20}]}'
                % (entry.id, slot.obj.id)
            ),
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(WorkoutLog.objects.count(), before)

    # -- discard leaves nothing ------------------------------------------

    def test_discard_after_logging_removes_session_and_logs(self):
        self.client.get(self.url, {'start': 'true'})
        self._log_a_set()
        session = WorkoutSession.objects.get(
            user=self.user, day=self.day, status='active',
        )
        self.assertTrue(session.logs.exists())

        resp = self.client.post(self.url, {'action': 'discard_workout'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(WorkoutSession.objects.filter(pk=session.pk).exists())
        self.assertFalse(WorkoutLog.objects.filter(session_id=session.pk).exists())
        self.assertFalse(
            WorkoutSession.objects.filter(user=self.user, status='active').exists()
        )

    def test_discard_sweeps_a_stray_empty_active_session(self):
        """A concurrent autosave landing after the discard must not survive."""
        self.client.get(self.url, {'start': 'true'})
        self._log_a_set()
        # Simulate a stray empty active session created by a racing request.
        WorkoutSession.objects.create(
            user=self.user, routine=self.routine, day=self.day,
            date=datetime.date.today(),
            time_start=timezone.localtime(timezone.now()).time(),
            status='active',
        )
        self.client.post(self.url, {'action': 'discard_workout'})
        self.assertFalse(
            WorkoutSession.objects.filter(user=self.user, status='active').exists()
        )

    # -- interrupt of an empty session deletes it -----------------------

    def test_interrupt_empty_session_deletes_it(self):
        self.client.get(self.url, {'start': 'true'})
        session = WorkoutSession.objects.get(
            user=self.user, day=self.day, status='active',
        )
        resp = self.client.post(self.url, {'action': 'interrupt_workout'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(WorkoutSession.objects.filter(pk=session.pk).exists())

    # -- stale empty active sessions are purged on load ----------------

    def test_opening_workout_purges_stale_empty_active_sessions(self):
        stale = WorkoutSession.objects.create(
            user=self.user, routine=self.routine, day=self.day,
            date=datetime.date.today() - datetime.timedelta(days=3),
            time_start=datetime.time(10, 0),
            status='active',
        )
        self.client.get(self.url)
        self.assertFalse(WorkoutSession.objects.filter(pk=stale.pk).exists())

    # -- finishing must not promote a sibling to 'finished' ------------

    def test_finish_does_not_promote_sibling_empty_active_session(self):
        # A real, current session with a logged set.
        self.client.get(self.url, {'start': 'true'})
        self._log_a_set()
        # A leftover empty active session for the same day (e.g. a second tab).
        leftover = WorkoutSession.objects.create(
            user=self.user, routine=self.routine, day=self.day,
            date=datetime.date.today(),
            time_start=timezone.localtime(timezone.now()).time(),
            status='active',
        )

        self.client.post(self.url, {'action': 'finish_workout'})

        # The leftover was dropped, not promoted to 'finished'.
        self.assertFalse(WorkoutSession.objects.filter(pk=leftover.pk).exists())
        from django.db.models import Count
        self.assertFalse(
            WorkoutSession.objects
            .filter(user=self.user, status='finished')
            .annotate(n=Count('logs')).filter(n=0)
            .exists()
        )
