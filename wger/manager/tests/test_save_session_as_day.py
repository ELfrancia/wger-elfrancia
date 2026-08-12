# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.urls import reverse
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import Day, Routine, WorkoutSession, WorkoutLog
from wger.manager.helpers import create_day_from_session
from wger.exercises.models import Exercise


import datetime


class SaveSessionAsDayTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.client.force_login(self.user)
        self.exercise = Exercise.objects.first()

        # Create a finished session with logs
        start_date = datetime.date.today()
        end_date = start_date + datetime.timedelta(days=28)
        self.routine = Routine.objects.create(user=self.user, name="Original Routine", start=start_date, end=end_date)
        self.day = Day.objects.create(routine=self.routine, name="Giorno Test", order=1)
        self.session = WorkoutSession.objects.create(
            user=self.user,
            routine=self.routine,
            day=self.day,
            status='finished',
        )
        WorkoutLog.objects.create(
            user=self.user,
            session=self.session,
            exercise=self.exercise,
            routine=self.routine,
            repetitions=12,
            weight=50,
        )
        WorkoutLog.objects.create(
            user=self.user,
            session=self.session,
            exercise=self.exercise,
            routine=self.routine,
            repetitions=12,
            weight=50,
        )

    def test_create_day_from_session_helper(self):
        # Create day in new routine
        new_day = create_day_from_session(
            user=self.user,
            session=self.session,
            new_routine_name="Nuova Routine Custom",
            day_name="Giorno A Custom"
        )

        self.assertEqual(new_day.name, "Giorno A Custom")
        self.assertEqual(new_day.routine.name, "Nuova Routine Custom")
        self.assertEqual(new_day.slots.count(), 1)
        
        slot = new_day.slots.first()
        entry = slot.entries.first()
        self.assertEqual(entry.exercise, self.exercise)
        self.assertEqual(entry.setsconfig_set.first().value, 2)  # 2 sets logged
        self.assertEqual(entry.repetitionsconfig_set.first().value, 12)
        self.assertEqual(entry.weightconfig_set.first().value, 50)

    def test_finish_workout_with_save_as_routine_day(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        response = self.client.post(url, {
            'action': 'finish_workout',
            'save_as_routine_day': 'true',
            'routine_day_name': 'Giorno Salvato Da Finish',
            'target_routine_id': self.routine.id,
        })
        self.assertEqual(response.status_code, 302)
        
        saved_day = Day.objects.filter(routine=self.routine, name='Giorno Salvato Da Finish').first()
        self.assertIsNotNone(saved_day)

    def test_session_details_save_as_routine_day(self):
        url = reverse('core:session-details', kwargs={'session_id': self.session.id})
        response = self.client.post(url, {
            'action': 'save_as_routine_day',
            'routine_day_name': 'Giorno Salvato Da Dettagli',
            'new_routine_name': 'Routine Da Dettagli',
            'target_routine_id': 'new',
        })
        self.assertEqual(response.status_code, 302)
        
        saved_day = Day.objects.filter(name='Giorno Salvato Da Dettagli').first()
        self.assertIsNotNone(saved_day)
        self.assertEqual(saved_day.routine.name, 'Routine Da Dettagli')
