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

# Django
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

# wger
from wger.core.tests.base_testcase import WgerTestCase
from wger.exercises.models import (
    Alias,
    Equipment,
    Exercise,
    ExerciseComment,
    ExerciseImage,
    Muscle,
    Translation,
)
from wger.utils.cache import (
    CacheKeyMapper,
    build_cache_key_prefix,
    cache_mapper,
)


class ExerciseApiCacheTestCase(WgerTestCase):
    """
    Tests the API cache for the exerciseinfo endpoint
    """

    exercise_id = 1
    exercise_uuid = 'acad3949-36fb-4481-9a72-be2ddae2bc05'
    url = '/api/v2/exerciseinfo/1/'

    cache_key = cache_mapper.get_exercise_api_key('acad3949-36fb-4481-9a72-be2ddae2bc05')

    def test_edit_exercise(self):
        """
        Tests editing an exercise
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        exercise = Exercise.objects.get(pk=1)
        exercise.category_id = 1
        exercise.save()

        self.assertFalse(cache.get(self.cache_key))

    def test_delete_exercise(self):
        """
        Tests deleting an exercise
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        exercise = Exercise.objects.get(pk=1)
        exercise.delete()

        self.assertFalse(cache.get(self.cache_key))

    def test_edit_translation(self):
        """
        Tests editing a translation
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        translation = Translation.objects.get(pk=1)
        translation.name = 'something else'
        translation.save()

        self.assertFalse(cache.get(self.cache_key))

    def test_delete_translation(self):
        """
        Tests deleting a translation
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        translation = Translation.objects.get(pk=1)
        translation.delete()

        self.assertFalse(cache.get(self.cache_key))

    def test_edit_comment(self):
        """
        Tests editing a comment
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        comment = ExerciseComment.objects.get(pk=1)
        comment.name = 'The Shiba Inu (柴犬) is a breed of hunting dog from Japan'
        comment.save()

        self.assertFalse(cache.get(self.cache_key))

    def test_delete_comment(self):
        """
        Tests deleting a comment
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        comment = ExerciseComment.objects.get(pk=1)
        comment.delete()

        self.assertFalse(cache.get(self.cache_key))

    def test_edit_alias(self):
        """
        Tests editing an alias
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        alias = Alias.objects.get(pk=1)
        alias.name = 'Hachikō'
        alias.save()

        self.assertFalse(cache.get(self.cache_key))

    def test_delete_alias(self):
        """
        Tests deleting an alias
        """
        self.assertFalse(cache.get(self.cache_key))
        self.client.get(self.url)
        self.assertTrue(cache.get(self.cache_key))

        alias = Alias.objects.get(pk=1)
        alias.delete()

        self.assertFalse(cache.get(self.cache_key))


class ExerciseInfoListCacheTestCase(WgerTestCase):
    """
    Tests the bulk cache handling of the exerciseinfo list endpoint
    """

    def test_warm_list_skips_prefetch_joins(self):
        """
        A warm list request reads the cached representations in bulk and must not
        query the related tables that the heavy queryset would otherwise prefetch.
        """
        list_url = reverse('exerciseinfo-list')

        # Warm the cache for every exercise
        self.client.get(list_url, {'limit': 900})

        related_tables = (
            Translation._meta.db_table,
            Alias._meta.db_table,
            ExerciseComment._meta.db_table,
            ExerciseImage._meta.db_table,
        )

        with CaptureQueriesContext(connection) as context:
            self.client.get(list_url, {'limit': 900})

        executed = ' '.join(query['sql'] for query in context.captured_queries)
        for table in related_tables:
            self.assertNotIn(table, executed)

    def test_list_reuses_per_exercise_cache_from_retrieve(self):
        """
        retrieve() and list() share the same per-exercise cache entry, so an
        exercise warmed through the detail endpoint is reused by the list.
        """
        exercise = Exercise.objects.get(pk=1)
        key = cache_mapper.get_exercise_api_key(exercise.uuid)

        self.assertFalse(cache.get(key))
        detail = self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk})).json()
        self.assertTrue(cache.get(key))

        results = self.client.get(reverse('exerciseinfo-list'), {'limit': 900}).json()['results']
        listed = next(row for row in results if row['id'] == exercise.pk)
        self.assertEqual(listed, detail)


class ExerciseCacheStalenessTestCase(WgerTestCase):
    """
    The cache must never answer with data that no longer matches the database.

    Every test here warms the cache first and then performs a write that does
    *not* go through the code path the cache entry was created by.
    """

    list_url_name = 'exerciseinfo-list'

    def _list(self):
        return self.client.get(reverse(self.list_url_name), {'limit': 900})

    def _ids(self, response):
        return [row['id'] for row in response.json()['results']]

    def test_new_exercise_shows_up_immediately(self):
        """
        Creating an exercise must be visible on the very next request.

        This is the case users hit first: an exercise is added and the list
        keeps answering from a cache entry built before it existed.
        """
        warm = self._list()
        self.assertEqual(warm.status_code, 200)

        exercise = Exercise.objects.create(category_id=1)
        Translation.objects.create(
            exercise=exercise,
            language_id=2,
            name='Brand new exercise',
            description='Created after the cache was warmed',
        )

        after = self._list()
        self.assertIn(exercise.pk, self._ids(after))
        self.assertEqual(len(self._ids(after)), len(self._ids(warm)) + 1)

    def test_deleted_exercise_disappears_immediately(self):
        warm = self._list()
        exercise = Exercise.objects.get(pk=1)
        self.assertIn(exercise.pk, self._ids(warm))

        exercise.delete()

        self.assertNotIn(exercise.pk, self._ids(self._list()))

    def test_edit_invalidates_the_object_and_the_list(self):
        """
        An edit must invalidate the single object *and* every collection that
        embeds it, not only the object key.
        """
        exercise = Exercise.objects.get(pk=1)
        key = cache_mapper.get_exercise_api_key(exercise.uuid)

        self._list()
        self.assertTrue(cache.get(key))
        collection_before = CacheKeyMapper.get_exercise_collection_prefix()

        translation = exercise.translations.first()
        translation.name = 'A different name entirely'
        translation.save()

        self.assertFalse(cache.get(key))
        self.assertNotEqual(collection_before, CacheKeyMapper.get_exercise_collection_prefix())

        listed = next(row for row in self._list().json()['results'] if row['id'] == exercise.pk)
        names = [entry['name'] for entry in listed['translations']]
        self.assertIn('A different name entirely', names)

    def test_adding_a_muscle_invalidates_the_cache(self):
        """
        m2m writes go through the related manager and never call save(), so
        without a m2m_changed receiver the cached payload keeps the old list.
        """
        exercise = Exercise.objects.get(pk=1)
        key = cache_mapper.get_exercise_api_key(exercise.uuid)
        muscle = Muscle.objects.exclude(pk__in=exercise.muscles.values('pk')).first()

        self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk}))
        self.assertTrue(cache.get(key))

        exercise.muscles.add(muscle)

        self.assertFalse(cache.get(key))
        fresh = self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk})).json()
        self.assertIn(muscle.pk, [entry['id'] for entry in fresh['muscles']])

    def test_adding_equipment_invalidates_the_cache(self):
        exercise = Exercise.objects.get(pk=1)
        key = cache_mapper.get_exercise_api_key(exercise.uuid)
        equipment = Equipment.objects.exclude(pk__in=exercise.equipment.values('pk')).first()

        self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk}))
        self.assertTrue(cache.get(key))

        exercise.equipment.add(equipment)

        self.assertFalse(cache.get(key))

    def test_renaming_a_muscle_invalidates_the_exercises_using_it(self):
        """
        Muscle names are embedded in every exercise payload that uses them.
        """
        muscle = Muscle.objects.get(pk=1)
        exercise = Exercise.objects.filter(muscles=muscle).first()
        self.assertIsNotNone(exercise, 'fixture needs an exercise with muscle 1')
        key = cache_mapper.get_exercise_api_key(exercise.uuid)

        self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk}))
        self.assertTrue(cache.get(key))

        muscle.name = 'Renamed muscle'
        muscle.save()

        self.assertFalse(cache.get(key))
        fresh = self.client.get(reverse('exerciseinfo-detail', kwargs={'pk': exercise.pk})).json()
        self.assertIn('Renamed muscle', [entry['name'] for entry in fresh['muscles']])

    def test_renamed_muscle_shows_up_on_the_cache_page_endpoint(self):
        """
        /api/v2/muscle/ caches the whole HTTP response with cache_page. Those
        entries are keyed by URL and headers and cannot be deleted one by one,
        so they are namespaced by the exercise generation instead.
        """
        url = reverse('muscle-list')

        warm = self.client.get(url, {'limit': 100})
        self.assertNotIn('Renamed muscle', warm.content.decode())

        muscle = Muscle.objects.get(pk=1)
        muscle.name = 'Renamed muscle'
        muscle.save()

        after = self.client.get(url, {'limit': 100})
        self.assertIn('Renamed muscle', after.content.decode())

    def test_warm_response_is_identical_to_the_cold_one(self):
        """
        R4: a warm cache must not change the answer by a single byte.
        """
        cache.clear()
        cold = self._list()
        warm = self._list()

        self.assertEqual(cold.status_code, warm.status_code)
        self.assertEqual(cold.content, warm.content)

    def test_warm_detail_is_identical_to_the_cold_one(self):
        url = reverse('exerciseinfo-detail', kwargs={'pk': 1})

        cache.clear()
        cold = self.client.get(url)
        warm = self.client.get(url)

        self.assertEqual(cold.content, warm.content)


class ExerciseCacheGenerationTestCase(WgerTestCase):
    """
    The generation counter and the version namespace
    """

    def test_generation_is_stable_without_writes(self):
        first = CacheKeyMapper.get_exercise_collection_prefix()
        self.assertEqual(first, CacheKeyMapper.get_exercise_collection_prefix())

    def test_every_kind_of_exercise_write_bumps_the_generation(self):
        exercise = Exercise.objects.get(pk=1)
        translation = exercise.translations.first()

        writes = (
            ('create an exercise', lambda: Exercise.objects.create(category_id=1)),
            ('save an exercise', lambda: exercise.save()),
            ('add a muscle', lambda: exercise.muscles.add(Muscle.objects.get(pk=2))),
            ('save a translation', lambda: translation.save()),
            ('add an alias', lambda: Alias.objects.create(translation=translation, alias='alias')),
            (
                'add a comment',
                lambda: ExerciseComment.objects.create(
                    translation=translation, comment='a comment'
                ),
            ),
        )

        for label, write in writes:
            with self.subTest(write=label):
                before = CacheKeyMapper.get_exercise_collection_prefix()
                write()
                self.assertNotEqual(
                    before,
                    CacheKeyMapper.get_exercise_collection_prefix(),
                    f'the generation was not bumped when doing: {label}',
                )

    def test_cache_keys_are_namespaced_by_application_version(self):
        """
        R3: a deploy must not be able to read payloads written by an older
        build, whatever shape they had.
        """
        # wger
        from wger.version import get_version

        prefix = build_cache_key_prefix()

        self.assertIn(get_version(), prefix)
        self.assertEqual(settings.CACHES['default']['KEY_PREFIX'], prefix)
