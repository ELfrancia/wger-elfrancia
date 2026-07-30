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
import datetime
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.urls import reverse

# wger
from wger.core.tests import api_base_test
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import (
    Day,
    WorkoutLog,
    WorkoutSession,
    Slot,
    SlotEntry,
    SetsConfig,
    RepetitionsConfig,
    WeightConfig,
)


class WorkoutSessionApiTestCase(api_base_test.ApiBaseResourceTestCase):
    """
    Tests the workout overview resource
    """

    pk = 'bbbbbbbb-bbbb-bbbb-bbbb-000000000005'
    resource = WorkoutSession
    private_resource = True
    data = {
        'workout': 3,
        'date': datetime.date(2014, 1, 25),
        'notes': 'My new insights',
        'impression': '3',
        'time_start': datetime.time(10, 0),
        'time_end': datetime.time(13, 0),
    }


class WorkoutSessionLifecycleTestCase(WgerTestCase):
    """
    Unit tests for WorkoutSession lifecycle, set creation with bodyweight,
    exercise completion logic, and user ownership verification.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.other_user = User.objects.get(username='admin')
        self.client.force_login(self.user)
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        self.routine.user = self.user
        self.routine.save()

    def test_session_lifecycle(self):
        """
        Verify session status transition: active -> finished / interrupted / restart.
        """
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})

        # GET request initializes an active session
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').order_by('-id').first()
        self.assertIsNotNone(session)
        self.assertEqual(session.status, 'active')

        # Finish workout
        response = self.client.post(url, {'action': 'finish_workout'})
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, 'finished')
        self.assertIsNotNone(session.time_end)

        # Start new session with ?start=true
        response = self.client.get(url + '?start=true')
        self.assertEqual(response.status_code, 302)
        new_session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').order_by('-id').first()
        self.assertIsNotNone(new_session)
        self.assertNotEqual(new_session.id, session.id)

        # Interrupt workout
        response = self.client.post(url, {'action': 'interrupt_workout'})
        self.assertEqual(response.status_code, 302)
        new_session.refresh_from_db()
        self.assertEqual(new_session.status, 'interrupted')
        self.assertIsNotNone(new_session.time_end)

        # Restart workout on an active session
        self.client.get(url)  # create or retrieve active session
        session_to_restart = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').order_by('-id').first()
        response = self.client.post(url, {'action': 'restart_workout'})
        self.assertEqual(response.status_code, 302)
        session_to_restart.refresh_from_db()
        self.assertEqual(session_to_restart.status, 'active')
        self.assertIsNone(session_to_restart.time_end)

    def test_set_creation_bodyweight(self):
        """
        Verify logging set with bodyweight (weight=0 or empty) results in weight Decimal('0').
        """
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        slot_entry = slot.entries.first()
        exercise_id = slot_entry.exercise_id

        # Post set with weight=0
        response = self.client.post(
            url,
            {
                'exercise_id': exercise_id,
                'slot_entry_id': slot_entry.id,
                'repetitions': 12,
                'weight': '0',
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)

        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').first()
        log = session.logs.filter(slot_entry_id=slot_entry.id).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.weight, Decimal('0'))

        # Post set with empty weight string
        session.logs.all().delete()
        response = self.client.post(
            url,
            {
                'exercise_id': exercise_id,
                'slot_entry_id': slot_entry.id,
                'repetitions': 10,
                'weight': '',
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        log = session.logs.filter(slot_entry_id=slot_entry.id).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.weight, Decimal('0'))

    def test_exercise_completion_logic(self):
        """
        Verify exercise completion fills remaining unlogged sets while preserving already logged user sets.
        If all sets are logged, toggling complete_exercise unchecks (deletes) logs.
        """
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        first_entry = slot.entries.first()
        second_entry = SlotEntry.objects.create(
            slot=slot,
            exercise=first_entry.exercise,
            order=first_entry.order + 1
        )
        SetsConfig.objects.create(slot_entry=second_entry, iteration=1, value=1)
        RepetitionsConfig.objects.create(slot_entry=second_entry, iteration=1, value=10)
        WeightConfig.objects.create(slot_entry=second_entry, iteration=1, value=20)
        target_entries = list(slot.entries.filter(exercise_id=first_entry.exercise_id))

        # Log first set manually with custom reps/weight
        self.client.post(
            url,
            {
                'exercise_id': first_entry.exercise_id,
                'slot_entry_id': first_entry.id,
                'repetitions': 15,
                'weight': '50',
            },
            HTTP_HX_REQUEST='true',
        )

        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').first()
        first_log = session.logs.get(slot_entry_id=first_entry.id)
        self.assertEqual(first_log.repetitions, 15)
        self.assertEqual(first_log.weight, Decimal('50'))

        # Now post complete_exercise for the exercise slot (should log second_entry, preserve first_entry)
        self.client.post(
            url,
            {
                'action': 'complete_exercise',
                'exercise_id': first_entry.exercise_id,
                'slot_id': slot.id,
            },
            HTTP_HX_REQUEST='true',
        )

        # All target entries in the slot should now have logs
        session = WorkoutSession.objects.get(pk=session.pk)
        logged_set_ids = set(WorkoutLog.objects.filter(session=session).values_list('slot_entry_id', flat=True))
        for entry in target_entries:
            self.assertIn(entry.id, logged_set_ids)

        # First set's logged values (15 reps, 50 weight) must be preserved!
        first_log_refreshed = session.logs.get(slot_entry_id=first_entry.id)
        self.assertEqual(first_log_refreshed.repetitions, 15)
        self.assertEqual(first_log_refreshed.weight, Decimal('50'))

        # Post complete_exercise again (when all sets are logged) -> should uncheck/delete logs
        self.client.post(
            url,
            {
                'action': 'complete_exercise',
                'exercise_id': first_entry.exercise_id,
                'slot_id': slot.id,
            },
            HTTP_HX_REQUEST='true',
        )
        remaining_logs = session.logs.filter(slot_entry_id__in=[e.id for e in target_entries]).count()
        self.assertEqual(remaining_logs, 0)

    def test_user_ownership_verification(self):
        """
        Verify that accessing a session/day belonging to another user returns 403 Forbidden.
        """
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})

        # Switch login to another user
        self.client.force_login(self.other_user)

        # Attempt GET on routine owned by self.user
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        # Attempt POST on routine owned by self.user
        response = self.client.post(url, {'action': 'complete_exercise'})
        self.assertEqual(response.status_code, 403)

    def test_upload_condition_photo_links_to_session(self):
        """
        Verify that uploading a condition photo creates Image and links it to WorkoutSession.condition_photo.
        """
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        self.client.get(url)
        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day).order_by('-id').first()
        self.assertIsNotNone(session)

        with open('wger/exercises/tests/wildschwein.jpg', 'rb') as photo_file:
            response = self.client.post(
                url,
                {
                    'action': 'upload_condition_photo',
                    'description': 'Test Condition Photo',
                    'image': photo_file,
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )

        self.assertEqual(response.status_code, 200)
        session.refresh_from_db()
        self.assertIsNotNone(session.condition_photo)
        self.assertEqual(session.condition_photo.description, 'Test Condition Photo')

