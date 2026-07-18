# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.urls import reverse
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import Day, WorkoutSession, WorkoutLog, SlotEntry, Slot

class WorkoutViewsTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.client.force_login(self.user)
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        # Ensure routine belongs to the logged in user
        self.routine.user = self.user
        self.routine.save()

    def test_log_tailwind_get(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('completed_exercise_ids', response.context)
        # Initially, no exercises are completed
        self.assertEqual(len(response.context['completed_exercise_ids']), 0)

    def test_log_tailwind_post_complete_exercise(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id

        # POST to complete exercise
        response = self.client.post(url, {'action': 'complete_exercise', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        
        # Verify logs were created
        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day).first()
        self.assertIsNotNone(session)
        logs_count = session.logs.filter(exercise_id=exercise_id).count()
        self.assertEqual(logs_count, slot.entries.count())

        # POST again to uncheck/delete logs
        response = self.client.post(url, {'action': 'complete_exercise', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        logs_count = session.logs.filter(exercise_id=exercise_id).count()
        self.assertEqual(logs_count, 0)

    def test_log_tailwind_post_add_and_delete_set_config(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id
        initial_count = slot.entries.count()

        # POST to add set
        response = self.client.post(url, {'action': 'add_set', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(slot.entries.count(), initial_count + 1)

        # Get the newly created slot entry
        new_entry = slot.entries.order_by('-order').first()

        # POST to delete set configuration (not the last one)
        response = self.client.post(url, {'action': 'delete_set_config', 'slot_entry_id': new_entry.id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(slot.entries.count(), initial_count)

        # Let's delete all but one, and then delete the last one
        for entry in list(slot.entries.all())[1:]:
            entry.delete()
        self.assertEqual(slot.entries.count(), 1)
        last_entry = slot.entries.first()

        # Deleting the last slot entry should delete the slot and return empty string
        response = self.client.post(url, {'action': 'delete_set_config', 'slot_entry_id': last_entry.id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')
        self.assertFalse(Slot.objects.filter(id=slot.id).exists())

    def test_log_tailwind_post_delete_set(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id
        slot_entry = slot.entries.first()

        # First, log a set
        response = self.client.post(url, {
            'exercise_id': exercise_id,
            'slot_entry_id': slot_entry.id,
            'repetitions': 10,
            'weight': 50
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)

        session = WorkoutSession.objects.get(user=self.user, routine=self.routine, day=self.day)
        self.assertTrue(session.logs.filter(slot_entry_id=slot_entry.id).exists())

        # Now delete it using delete_set
        response = self.client.post(url, {
            'action': 'delete_set',
            'slot_entry_id': slot_entry.id,
            'exercise_id': exercise_id
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(session.logs.filter(slot_entry_id=slot_entry.id).exists())
