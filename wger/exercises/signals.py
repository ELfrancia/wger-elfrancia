# -*- coding: utf-8 -*-

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
import logging

# Django
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver

# Third Party
from easy_thumbnails.files import get_thumbnailer
from easy_thumbnails.signal_handlers import generate_aliases
from easy_thumbnails.signals import saved_file

# wger
from wger.exercises.models import (
    Alias,
    DeletionLog,
    Equipment,
    Exercise,
    ExerciseCategory,
    ExerciseComment,
    ExerciseImage,
    ExerciseVideo,
    Muscle,
    Translation,
)
from wger.utils.cache import (
    bump_exercise_generation,
    reset_exercise_api_cache,
    reset_exercise_api_cache_many,
)


logger = logging.getLogger(__name__)


@receiver(post_delete, sender=ExerciseImage)
def delete_exercise_image_on_delete(sender, instance: ExerciseImage, **kwargs):
    """
    Delete the image along with its thumbnails
    """
    thumbnailer = get_thumbnailer(instance.image)
    thumbnailer.delete_thumbnails()
    instance.image.delete(save=False)


@receiver(pre_save, sender=ExerciseImage)
def delete_exercise_image_on_update(sender, instance: ExerciseImage, **kwargs):
    """
    Delete the corresponding image from the filesystem when the ExerciseImage
    object was edited
    """
    if not instance.pk:
        return False

    try:
        old_file = ExerciseImage.objects.get(pk=instance.pk).image
    except ExerciseImage.DoesNotExist:
        return False

    new_file = instance.image
    if not old_file == new_file and old_file:
        # Deletes the old image as well as its thumbnails
        thumbnailer = get_thumbnailer(old_file)
        thumbnailer.delete_thumbnails()
        old_file.delete(save=False)
    return None


# Generate thumbnails when uploading a new image
saved_file.connect(generate_aliases)


@receiver(post_delete, sender=ExerciseVideo)
def auto_delete_video_on_delete(sender, instance: ExerciseVideo, **kwargs):
    """
    Deletes file when corresponding ExerciseVideo object is deleted
    """
    if instance.video:
        instance.video.delete(save=False)


@receiver(pre_save, sender=ExerciseVideo)
def delete_exercise_video_on_update(sender, instance: ExerciseVideo, **kwargs):
    """
    Deletes file when corresponding ExerciseVideo object was edited
    """
    if not instance.pk:
        return False

    try:
        old_file = ExerciseVideo.objects.get(pk=instance.pk).video
    except ExerciseVideo.DoesNotExist:
        return False

    new_file = instance.video
    if not old_file == new_file and old_file:
        old_file.delete(save=False)
    return None


@receiver(pre_delete, sender=Translation)
def add_deletion_log_translation(sender, instance: Translation, **kwargs):
    DeletionLog.objects.update_or_create(
        uuid=instance.uuid,
        defaults={
            'model_type': DeletionLog.MODEL_TRANSLATION,
            'comment': instance.name,
        },
    )


@receiver(pre_delete, sender=ExerciseImage)
def add_deletion_log_image(sender, instance: ExerciseImage, **kwargs):
    DeletionLog.objects.update_or_create(
        uuid=instance.uuid,
        defaults={'model_type': DeletionLog.MODEL_IMAGE},
    )


@receiver(pre_delete, sender=ExerciseVideo)
def add_deletion_log_video(sender, instance: ExerciseVideo, **kwargs):
    DeletionLog.objects.update_or_create(
        uuid=instance.uuid,
        defaults={'model_type': DeletionLog.MODEL_VIDEO},
    )


#
# Cache invalidation
#
# The models below also reset the cache from their own save()/delete(), but
# those overrides are bypassed by a number of very real code paths: the Django
# admin bulk actions, loaddata, DRF nested writes, cascading deletes and
# anything reaching the related managers (exercise.muscles.add(...)) instead of
# the model. Wiring the signals as well makes the invalidation a property of
# the model rather than of the caller.
#
# reset_exercise_api_cache() only deletes a key and bumps a counter, so calling
# it twice for the same write costs nothing and is always the safe direction.
#


def _reset_cache_for(exercise) -> None:
    """
    Invalidate an exercise, tolerating a half-deleted object graph.

    During a cascading delete the parent row can already be gone by the time
    the children fire their signals. In that case we cannot build the per
    object key, but we still invalidate every collection: better a needless
    rebuild than a stale list.
    """
    try:
        if exercise is None:
            raise ObjectDoesNotExist
        reset_exercise_api_cache(exercise.uuid)
    except ObjectDoesNotExist:
        bump_exercise_generation()


def _reset_cache_for_translation_child(instance) -> None:
    """
    Comments and aliases hang off a translation, which hangs off an exercise.
    """
    try:
        _reset_cache_for(instance.translation.exercise)
    except ObjectDoesNotExist:
        bump_exercise_generation()


@receiver(post_save, sender=Exercise)
@receiver(post_delete, sender=Exercise)
def reset_cache_on_exercise_write(sender, instance: Exercise, **kwargs):
    """
    Covers creating an exercise, which is the case the users notice first
    """
    _reset_cache_for(instance)


@receiver(m2m_changed, sender=Exercise.muscles.through)
@receiver(m2m_changed, sender=Exercise.muscles_secondary.through)
@receiver(m2m_changed, sender=Exercise.equipment.through)
def reset_cache_on_exercise_m2m_change(sender, instance, action, reverse, pk_set, **kwargs):
    """
    Muscles and equipment are part of the serialized payload but are written
    through the related manager, which never calls Exercise.save(). Without
    this receiver, assigning a muscle to an exercise leaves the cached
    representation showing the old list.
    """
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return

    # Forward (exercise.muscles.add(m)): instance is the exercise.
    # Reverse (muscle.exercise_set.add(e)): instance is the muscle and the
    # affected exercises are in pk_set.
    if not reverse:
        _reset_cache_for(instance)
        return

    if pk_set:
        for exercise in Exercise.objects.filter(pk__in=pk_set):
            _reset_cache_for(exercise)
    else:
        # post_clear gives us no pk_set on the reverse side
        bump_exercise_generation()


@receiver(post_save, sender=Translation)
@receiver(post_delete, sender=Translation)
def reset_cache_on_translation_write(sender, instance: Translation, **kwargs):
    _reset_cache_for(getattr(instance, 'exercise', None))


@receiver(post_save, sender=ExerciseImage)
@receiver(post_delete, sender=ExerciseImage)
def reset_cache_on_image_write(sender, instance: ExerciseImage, **kwargs):
    _reset_cache_for(getattr(instance, 'exercise', None))


@receiver(post_save, sender=ExerciseVideo)
@receiver(post_delete, sender=ExerciseVideo)
def reset_cache_on_video_write(sender, instance: ExerciseVideo, **kwargs):
    _reset_cache_for(getattr(instance, 'exercise', None))


@receiver(post_save, sender=ExerciseComment)
@receiver(post_delete, sender=ExerciseComment)
def reset_cache_on_comment_write(sender, instance: ExerciseComment, **kwargs):
    _reset_cache_for_translation_child(instance)


@receiver(post_save, sender=Alias)
@receiver(post_delete, sender=Alias)
def reset_cache_on_alias_write(sender, instance: Alias, **kwargs):
    _reset_cache_for_translation_child(instance)


def _reset_cache_for_exercises(queryset) -> None:
    """
    Invalidate every exercise matched by the queryset.
    """
    uuids = list(queryset.values_list('uuid', flat=True).distinct())
    if uuids:
        reset_exercise_api_cache_many(uuids)
    else:
        bump_exercise_generation()


@receiver(post_save, sender=Muscle)
@receiver(pre_delete, sender=Muscle)
def reset_cache_on_muscle_write(sender, instance: Muscle, **kwargs):
    """
    Muscle names and images are embedded in every exercise that uses them, so
    renaming one invalidates those exercises and not just the muscle endpoint.

    Hooked on pre_delete rather than post_delete: once the row is gone the
    through table has been cascaded away too and the exercises can no longer
    be found.
    """
    _reset_cache_for_exercises(
        Exercise.objects.filter(Q(muscles=instance) | Q(muscles_secondary=instance))
    )


@receiver(post_save, sender=Equipment)
@receiver(pre_delete, sender=Equipment)
def reset_cache_on_equipment_write(sender, instance: Equipment, **kwargs):
    _reset_cache_for_exercises(Exercise.objects.filter(equipment=instance))


@receiver(post_save, sender=ExerciseCategory)
@receiver(pre_delete, sender=ExerciseCategory)
def reset_cache_on_category_write(sender, instance: ExerciseCategory, **kwargs):
    _reset_cache_for_exercises(Exercise.objects.filter(category=instance))
