# -*- coding: utf-8 -*-
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
