# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from wger.core.tests.base_testcase import WgerTestCase
from wger.exercises.models import Exercise
from wger.manager.models import Day, Routine, Slot, SlotEntry


class ApiV1ViewsTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.client.force_login(self.user)
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        self.routine.user = self.user
        self.routine.save()

    def test_api_v1_routine_add_exercise_with_data_day_id(self):
        """M4: POST to add exercise without day_id in URL reads day_id from request body."""
        url = reverse('api-v1-routine-add-exercise', kwargs={'routine_id': self.routine.id})
        slot = self.day.slots.first()
        exercise = slot.obj

        response = self.client.post(
            url,
            {'day_id': self.day.id, 'exercise_id': exercise.id},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(SlotEntry.objects.filter(id=data['entry_id']).exists())

    def test_api_v1_routine_delete_exercise_cleans_up_slot(self):
        """M4: DELETE exercise correctly uses slot.entries (not slotentry_set) and deletes empty slot."""
        slot = self.day.slots.first()
        # Keep only one entry in the slot
        entries = list(slot.entries.all())
        for e in entries[1:]:
            e.delete()

        entry = slot.entries.first()
        entry_id = entry.id
        slot_id = slot.id

        url = reverse(
            'api-v1-routine-delete-exercise',
            kwargs={'routine_id': self.routine.id, 'exercise_id': entry_id}
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(SlotEntry.objects.filter(id=entry_id).exists())
        # Since slot only had 1 entry, it should be deleted
        self.assertFalse(Slot.objects.filter(id=slot_id).exists())
