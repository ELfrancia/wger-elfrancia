from django.urls import reverse
from django.contrib.auth.models import User
from wger.core.tests.base_testcase import WgerTestCase
from wger.exercises.models import CalisthenicsExercise, Exercise, Translation
from wger.manager.models import Routine, Day

class CustomExerciseTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user_login('admin')
        self.user = User.objects.get(username='admin')
        
        # Setup dummy routine and day
        self.routine = Routine.objects.create(
            name="Test Routine",
            user=self.user,
            start="2026-07-17",
            end="2026-08-28"
        )
        self.day = Day.objects.create(
            routine=self.routine,
            name="Day 1",
            order=1
        )

    def test_create_custom_exercise_ajax(self):
        url = reverse('manager:routine:add-custom-exercise', kwargs={
            'routine_pk': self.routine.pk,
            'day_pk': self.day.pk
        })
        
        response = self.client.post(url, {
            'name': 'Custom Handstand Push-up',
            'instructions': 'Get in handstand.\nLower yourself.\nPush up.',
            'skill_family': 'handstand',
            'target_muscle': 'shoulders',
            'weighted': 'on'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertEqual(data['name'], 'Custom Handstand Push-up')
        
        # Check database creation
        self.assertEqual(CalisthenicsExercise.objects.filter(name='Custom Handstand Push-up').count(), 1)
        cal_ex = CalisthenicsExercise.objects.get(name='Custom Handstand Push-up')
        self.assertEqual(cal_ex.source, 'custom')
        self.assertEqual(cal_ex.equipment, 'weighted body weight')
        
        # Check native wger structures
        self.assertEqual(Exercise.objects.filter(uuid=cal_ex.id).count(), 1)
        self.assertEqual(Translation.objects.filter(name='Custom Handstand Push-up').count(), 1)
