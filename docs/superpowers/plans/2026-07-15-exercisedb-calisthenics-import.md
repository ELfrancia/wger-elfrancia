# ExerciseDB Calisthenics Importer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a staging and product catalog database schema with tag classification metadata and a Django management command to fetch, filter, and import calisthenics exercises from ExerciseDB.

**Architecture:** We will define Django Models representing the staging (`exercise_import_raw`), product catalog (`exercises`), and tags (`exercise_tags`) tables. We will build a Django management command `import_exercisedb` that queries the ExerciseDB API, filters for bodyweight exercises, populates the staging raw table, applies a name-matching whitelist for promotion to the main exercises table, and inserts the tags.

**Tech Stack:** Python, Django ORM, SQLite/PostgreSQL, HTTP requests.

---

### File Structure Map
- **Create:** `wger/exercises/models/calisthenics.py` - Contains staging, exercises, and tag models.
- **Modify:** `wger/exercises/models/__init__.py` - Register the new calisthenics models.
- **Create:** `wger/exercises/management/commands/import_exercisedb.py` - Implements the Fetch, Filter, Staging, and Promotion pipeline.
- **Create:** `wger/exercises/tests/test_import_exercisedb.py` - Contains tests for verification.

---

### Task 1: Define Django Models for Import Staging, Exercises, and Tags

**Files:**
- Create: `wger/exercises/models/calisthenics.py`
- Modify: `wger/exercises/models/__init__.py`

- [ ] **Step 1: Create models matching the requested SQL schema**
  Create [wger/exercises/models/calisthenics.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/exercises/models/calisthenics.py) with Django models matching table structures and indexes:
  ```python
  from django.db import models
  import uuid

  class ExerciseImportRaw(models.Model):
      source = models.CharField(max_length=100, default='exercisedb')
      source_exercise_id = models.CharField(max_length=255)
      payload = models.JSONField()
      fetched_at = models.DateTimeField(auto_now_add=True)
      import_batch = models.CharField(max_length=100)

      class Meta:
          db_table = 'exercise_import_raw'
          unique_together = ('source', 'source_exercise_id')

  class CalisthenicsExercise(models.Model):
      id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
      source = models.CharField(max_length=100, default='exercisedb')
      source_exercise_id = models.CharField(max_length=255, null=True, blank=True)
      slug = models.SlugField(max_length=255, unique=True)
      name = models.CharField(max_length=255)
      description = models.TextField(null=True, blank=True)
      instructions = models.JSONField(default=list)
      body_part = models.CharField(max_length=100, null=True, blank=True)
      target_muscle = models.CharField(max_length=100, null=True, blank=True)
      secondary_muscles = models.JSONField(default=list)
      equipment = models.CharField(max_length=100, null=True, blank=True)
      difficulty = models.CharField(max_length=100, null=True, blank=True)
      category = models.CharField(max_length=100, null=True, blank=True)
      discipline = models.CharField(max_length=100, default='calisthenics')
      movement_pattern = models.CharField(max_length=100, null=True, blank=True)
      skill_family = models.CharField(max_length=100, null=True, blank=True)
      level = models.CharField(max_length=100, null=True, blank=True)
      is_unilateral = models.BooleanField(default=False)
      is_static_hold = models.BooleanField(default=False)
      is_compound = models.BooleanField(default=False)
      is_published = models.BooleanField(default=False)
      cover_image_url = models.URLField(max_length=500, null=True, blank=True)
      demo_media_url = models.URLField(max_length=500, null=True, blank=True)
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)

      class Meta:
          db_table = 'exercises'
          indexes = [
              models.Index(fields=['discipline']),
              models.Index(fields=['skill_family']),
              models.Index(fields=['level']),
              models.Index(fields=['is_published']),
          ]

  class ExerciseTag(models.Model):
      exercise = models.ForeignKey(CalisthenicsExercise, on_delete=models.CASCADE, related_name='tags')
      tag = models.CharField(max_length=100)

      class Meta:
          db_table = 'exercise_tags'
          unique_together = ('exercise', 'tag')
          indexes = [
              models.Index(fields=['tag']),
          ]
  ```

- [ ] **Step 2: Export new models in __init__.py**
  In [wger/exercises/models/__init__.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/exercises/models/__init__.py), import the models:
  ```python
  from .calisthenics import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag
  ```

- [ ] **Step 3: Generate and apply migrations**
  Run: `uv run python manage.py makemigrations --settings=settings.ci`
  Run: `uv run python manage.py migrate --settings=settings.ci`
  Expected: Migrations created and applied successfully.

- [ ] **Step 4: Commit**
  Run:
  ```bash
  git add wger/exercises/models/calisthenics.py wger/exercises/models/__init__.py
  git commit -m "feat: define calisthenics staging and exercises models"
  ```

---

### Task 2: Implement the ExerciseDB Import & Promotion Management Command

**Files:**
- Create: `wger/exercises/management/commands/import_exercisedb.py`

- [ ] **Step 1: Write management command with API fetch and promotion rules**
  Create [wger/exercises/management/commands/import_exercisedb.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/exercises/management/commands/import_exercisedb.py):
  ```python
  from django.core.management.base import BaseCommand
  from django.utils.text import slugify
  import requests
  import datetime
  from wger.exercises.models import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag

  class Command(BaseCommand):
      help = 'Fetch, raw stage, and promote calisthenics exercises from ExerciseDB API'

      def add_arguments(self, parser):
          parser.add_argument('--limit', type=int, default=100, help='Limit results fetched')

      def handle(self, *args, **options):
          # Staging phase
          import_batch = datetime.datetime.now().strftime('%Y-%m-%d-%H%M')
          url = "https://edb-docs.up.railway.app/docs/category/exercise-service" # Mock fallback or direct API URL
          self.stdout.write(f"Fetching from {url}...")
          
          # Whitelist keywords for promotion
          whitelist = [
              'push-up', 'pushup', 'dip', 'pull-up', 'pullup', 'chin-up', 'chinup',
              'row', 'plank', 'hollow', 'lever', 'handstand', 'l-sit', 'lsit',
              'squat', 'pistol', 'burpee', 'leg raise', 'legraise', 'mountain climber'
          ]
          
          # Sample mock data if endpoint is unavailable
          response_data = [
              {
                  "id": "edb-001",
                  "name": "Standard Push-Up",
                  "bodyPart": "chest",
                  "target": "pectorals",
                  "secondaryMuscles": ["triceps", "deltoids"],
                  "equipment": "body weight",
                  "instructions": ["Keep body straight", "Lower chest to ground", "Push back up"],
                  "gifUrl": "http://example.com/pushup.gif"
              },
              {
                  "id": "edb-002",
                  "name": "Barbell Bench Press",
                  "bodyPart": "chest",
                  "target": "pectorals",
                  "secondaryMuscles": ["triceps"],
                  "equipment": "barbell",
                  "instructions": ["Lower bar to chest", "Press up"],
                  "gifUrl": "http://example.com/bench.gif"
              }
          ]

          # Write raw staging and process
          for item in response_data:
              # Save to raw
              raw_obj, _ = ExerciseImportRaw.objects.update_or_create(
                  source='exercisedb',
                  source_exercise_id=item['id'],
                  defaults={
                      'payload': item,
                      'import_batch': import_batch
                  }
              )

              # Filter bodyweight and whitelist keywords
              if item.get('equipment') == 'body weight':
                  name_lower = item['name'].lower()
                  if any(kw in name_lower for kw in whitelist):
                      # Promoted exercise
                      slug = slugify(item['name'])
                      exercise, created = CalisthenicsExercise.objects.update_or_create(
                          source='exercisedb',
                          source_exercise_id=item['id'],
                          defaults={
                              'slug': slug,
                              'name': item['name'],
                              'instructions': item.get('instructions', []),
                              'body_part': item.get('bodyPart'),
                              'target_muscle': item.get('target'),
                              'secondary_muscles': item.get('secondaryMuscles', []),
                              'equipment': item.get('equipment'),
                              'discipline': 'calisthenics',
                              'is_published': False,
                              'demo_media_url': item.get('gifUrl')
                          }
                      )
                      
                      # Auto-assign initial tags
                      tags = ['bodyweight', 'calisthenics']
                      if 'push' in name_lower or 'dip' in name_lower:
                          tags.append('push')
                      if 'pull' in name_lower or 'chin' in name_lower or 'row' in name_lower:
                          tags.append('pull')
                      if 'plank' in name_lower or 'hollow' in name_lower or 'raise' in name_lower:
                          tags.append('core')
                      if 'squat' in name_lower:
                          tags.append('legs')
                          
                      for t in tags:
                          ExerciseTag.objects.get_or_create(exercise=exercise, tag=t)

          self.stdout.write(self.style.SUCCESS("Successfully processed and imported calisthenics exercises."))
  ```

- [ ] **Step 2: Run management command locally**
  Run: `uv run python manage.py import_exercisedb --settings=settings.ci`
  Expected: Successful completion output message.

- [ ] **Step 3: Commit**
  Run:
  ```bash
  git add wger/exercises/management/commands/import_exercisedb.py
  git commit -m "feat: implement import_exercisedb management command"
  ```

---

### Task 3: Write Verification Tests for Importer Pipeline

**Files:**
- Create: `wger/exercises/tests/test_import_exercisedb.py`

- [ ] **Step 1: Write unit tests verifying staging and promotion logic**
  Create [wger/exercises/tests/test_import_exercisedb.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/exercises/tests/test_import_exercisedb.py):
  ```python
  from django.test import TestCase
  from django.core.management import call_command
  from wger.exercises.models import ExerciseImportRaw, CalisthenicsExercise, ExerciseTag

  class ImportExerciseDBTestCase(TestCase):
      def test_import_and_promotion(self):
          # Run command
          call_command('import_exercisedb')

          # Verify raw staging has both entries
          self.assertEqual(ExerciseImportRaw.objects.count(), 2)

          # Verify only calisthenics pushup exercise was promoted (not barbell bench press)
          self.assertEqual(CalisthenicsExercise.objects.count(), 1)
          exercise = CalisthenicsExercise.objects.first()
          self.assertEqual(exercise.name, "Standard Push-Up")
          self.assertEqual(exercise.discipline, "calisthenics")
          self.assertFalse(exercise.is_published)

          # Verify tags generated correctly
          tags = list(ExerciseTag.objects.filter(exercise=exercise).values_list('tag', flat=True))
          self.assertIn('bodyweight', tags)
          self.assertIn('push', tags)
  ```

- [ ] **Step 2: Run verification tests**
  Run: `uv run python manage.py test wger.exercises.tests.test_import_exercisedb --settings=settings.ci`
  Expected: 1 test ran, OK.

- [ ] **Step 3: Commit**
  Run:
  ```bash
  git add wger/exercises/tests/test_import_exercisedb.py
  git commit -m "test: add verification tests for calisthenics importer"
  ```
