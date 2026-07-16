# -*- coding: utf-8 -*-
from django.test import TestCase
from django.core.management import call_command
from wger.exercises.models import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag

class ImportExerciseDBTestCase(TestCase):
    def test_import_and_promotion(self):
        # Run import management command
        call_command('import_exercisedb')

        # Verify raw staging has all 3 entries from fallback mock data
        self.assertEqual(ExerciseImportRaw.objects.count(), 3)

        # Verify only calisthenics pushup & dip exercises were promoted (not barbell bench press)
        self.assertEqual(CalisthenicsExercise.objects.count(), 2)

        # Retrieve pushup and verify values
        pushup = CalisthenicsExercise.objects.get(source_exercise_id="edb-001")
        self.assertEqual(pushup.name, "Standard Push-Up")
        self.assertEqual(pushup.discipline, "calisthenics")
        self.assertFalse(pushup.is_published)

        # Verify tags generated correctly for pushup
        pushup_tags = list(ExerciseTag.objects.filter(exercise=pushup).values_list('tag', flat=True))
        self.assertIn('bodyweight', pushup_tags)
        self.assertIn('push', pushup_tags)
        self.assertNotIn('pull', pushup_tags)
