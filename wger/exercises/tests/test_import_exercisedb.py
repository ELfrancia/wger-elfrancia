# -*- coding: utf-8 -*-
from django.test import TestCase
from django.core.management import call_command
from unittest.mock import patch, MagicMock
from wger.exercises.models import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag

class ImportExerciseDBTestCase(TestCase):
    @patch('requests.get')
    def test_import_and_promotion(self, mock_get):
        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                "id": "edb-001",
                "name": "Standard Push-Up",
                "equipment": "body weight",
                "bodyPart": "chest",
                "target": "pectorals",
                "secondaryMuscles": ["triceps"],
                "instructions": ["Keep body straight", "Lower chest", "Push back up"],
                "gifUrl": "http://example.com/pushup.gif"
            },
            {
                "id": "edb-003",
                "name": "Standard Dip",
                "equipment": "body weight",
                "bodyPart": "chest",
                "target": "pectorals",
                "secondaryMuscles": ["triceps"],
                "instructions": ["Keep body straight", "Lower", "Push back up"],
                "gifUrl": "http://example.com/dip.gif"
            },
            {
                "id": "edb-002",
                "name": "Bodyweight Bicep Curl",
                "equipment": "body weight",
                "bodyPart": "arms",
                "target": "biceps",
                "secondaryMuscles": [],
                "instructions": ["Curl your bodyweight"],
                "gifUrl": "http://example.com/bicep.gif"
            }
        ]
        mock_get.return_value = mock_response

        # Run import management command
        call_command('import_exercisedb')

        # Verify raw staging has 2 entries (since barbell is filtered out before staging)
        self.assertEqual(ExerciseImportRaw.objects.count(), 2)

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


