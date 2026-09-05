# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

# Standard Library
import logging
import time
from typing import Iterable

# Django
from django.core.cache import cache
from django.core.cache.utils import make_template_fragment_key
from django.db import transaction


logger = logging.getLogger(__name__)


#
# Cache namespace (R3: a deploy must never serve payloads of an older shape)
#
# Every key written through the default cache is prefixed with
# "wger.<app version>.<CACHE_SCHEMA_VERSION>" (see build_cache_key_prefix()
# below, which is used to set CACHES['default']['KEY_PREFIX']).
#
# Bump CACHE_SCHEMA_VERSION by hand whenever the *shape* of something we cache
# changes without the application version changing, e.g. when a field is added
# to ExerciseInfoSerializer within the same release. Bumping it orphans every
# previously cached entry instead of letting the new code read back a payload
# that no longer matches its serializer.
#
CACHE_SCHEMA_VERSION = 1


def build_cache_key_prefix() -> str:
    """
    Namespace for every cache key written by this build.

    Called from the settings modules, so it must not touch the app registry
    (wger.version is dependency free and is already imported there).
    """
    # wger
    from wger.version import get_version

    return f'wger.{get_version()}.{CACHE_SCHEMA_VERSION}'


#
# Generation counter for collections (R2)
#
# Single objects are cached under a key derived from their UUID and can be
# deleted individually. Collections cannot: there is one entry per filter,
# ordering, page, language and header combination (API lists, the exercise
# catalog, the responses cached whole by cache_page) and we cannot enumerate
# them on a backend without wildcard deletes.
#
# Instead, every collection key embeds the current "generation". Any write to
# an exercise bumps the generation, which makes all previously written
# collection keys unreachable at once. This behaves identically on LocMem,
# Redis and a file based cache: no delete_pattern, no SCAN, no backend
# specific code.
#
EXERCISE_GENERATION_KEY = 'exercise-generation'


def _new_generation() -> str:
    """
    A generation value strictly larger than every value used before.

    Using the wall clock in nanoseconds means that even when the counter is
    lost (backend restart, LRU eviction, ...) the next value we come up with
    has never been used before, so orphaned entries stay orphaned and can never
    be resurrected.
    """
    return str(time.time_ns())


def get_exercise_generation() -> str:
    """
    Current generation, seeding it when the cache does not know it yet.
    """
    generation = cache.get(EXERCISE_GENERATION_KEY)
    if not generation:
        generation = _new_generation()
        # No timeout: losing this key is safe, but pointlessly expensive
        cache.set(EXERCISE_GENERATION_KEY, generation, None)
    return generation


def bump_exercise_generation() -> str:
    """
    Invalidate every cached exercise collection at once.
    """
    generation = _new_generation()
    cache.set(EXERCISE_GENERATION_KEY, generation, None)
    return generation


def _bump_exercise_catalog_version() -> None:
    """
    Invalidate the compact exercise catalog served by /api/v1/exercises/.

    The catalog lives in wger.manager but is built entirely out of exercise
    data, so the exercise side is the only place that knows when it went
    stale. Imported lazily and defensively: a problem there must never make
    saving an exercise fail.
    """
    try:
        # wger
        from wger.manager.services.exercise_catalog import bump_catalog_version

        bump_catalog_version()
    except Exception:  # pragma: no cover - defensive
        logger.exception('Could not invalidate the exercise catalog cache')


def _invalidate(keys: list[str]) -> None:
    """
    Drop the given single object keys and invalidate every collection.
    """
    if keys:
        cache.delete_many(keys)
    bump_exercise_generation()
    _bump_exercise_catalog_version()


def reset_exercise_api_cache(uuid) -> None:
    """
    Invalidate everything that depends on the given exercise.
    """
    reset_exercise_api_cache_many([uuid])


def reset_exercise_api_cache_many(uuids: Iterable) -> None:
    """
    Same as reset_exercise_api_cache() for a batch of exercises.

    Use this from bulk code paths (bulk_create, bulk_update,
    queryset.update(), sync and other management commands) which do not go
    through Model.save() and therefore emit no signals.

    The invalidation is done twice on purpose:

    * immediately, so that code reading the cache inside the same transaction
      (and the test suite, which runs inside a transaction that is never
      committed) sees the fresh state right away;
    * again on commit, because between the first delete and the commit another
      process can read the *old* row from the database and write it back into
      the cache. Without the second pass that resurrected entry would survive
      until its TTL expired.

    Outside of an atomic block on_commit() runs the callback immediately, so
    the second pass costs one extra delete and nothing else.
    """
    keys = [CacheKeyMapper.get_exercise_api_key(uuid) for uuid in uuids]

    _invalidate(keys)
    transaction.on_commit(lambda: _invalidate(keys))


class CacheKeyMapper:
    """
    Simple class for mapping the cache keys of different objects
    """

    def get_pk(self, param):
        """
        Small helper function that returns the PK for the given parameter
        """
        return param.pk if hasattr(param, 'pk') else param

    def get_language_key(self, param):
        """
        Return the language cache key
        """
        return f'language-{self.get_pk(param)}'

    def get_nutrition_cache_by_key(self, params):
        """
        get nutritional info values canonical representation  using primary key.
        """
        return f'nutrition-cache-log-{self.get_pk(params)}'

    @classmethod
    def get_exercise_api_key(cls, base_uuid) -> str:
        """
        get the exercise base cache key used in the API
        """
        return f'base-uuid-{base_uuid}'

    @classmethod
    def get_exercise_collection_prefix(cls) -> str:
        """
        Prefix for anything caching *several* exercises at once.

        Includes the current generation, so a write to any exercise leaves
        every previously cached collection unreachable.
        """
        return f'exercise-collection-{get_exercise_generation()}'

    @classmethod
    def routine_date_sequence_key(cls, pk: int):
        return f'routine-date-sequence-{pk}'

    @classmethod
    def routine_api_date_sequence_display_key(cls, pk: int, user_id: int):
        return f'routine-api-date-sequence-display-{user_id}-{pk}'

    @classmethod
    def routine_api_date_sequence_gym_key(cls, pk: int, user_id: int):
        return f'routine-api-date-sequence-gym-{user_id}-{pk}'

    @classmethod
    def routine_api_stats(cls, pk: int, user_id: int):
        return f'routine-api-stats-{user_id}-{pk}'

    @classmethod
    def routine_api_logs(cls, pk: int, user_id: int):
        return f'routine-api-logs-{user_id}-{pk}'

    @classmethod
    def routine_api_structure_key(cls, pk: int, user_id: int = None):
        return f'routine-api-structure-{user_id}-{pk}'

    @classmethod
    def slot_entry_configs_key(cls, pk: int):
        return f'slot-entry-configs-{pk}'


cache_mapper = CacheKeyMapper()
