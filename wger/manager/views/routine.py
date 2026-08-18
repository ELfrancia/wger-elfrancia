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
import copy
import datetime
import logging
import os
import threading
from typing import List
import uuid

# Third Party
import requests

# Django
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

# wger
from wger.core.models import Language
from wger.core.models.license import License
from wger.exercises.models import (
    CalisthenicsExercise,
    Exercise,
    Translation,
    ExerciseCategory,
    Muscle,
    Equipment,
    ExerciseTag,
)
from wger.manager.models import (
    AbstractChangeConfig,
    Routine,
    SlotEntry,
)


logger = logging.getLogger(__name__)


@login_required
def copy_routine(request, pk):
    """
    Makes a copy of a routine
    """
    routine = get_object_or_404(Routine, pk=pk)

    if request.user != routine.user and not routine.is_public:
        # Check if the user is a trainer and the routine belongs to a client, only if it does not
        # belong to the user.
        trainer_identity_pk = request.session.get('trainer.identity', None)
        if not trainer_identity_pk or routine.user.pk != trainer_identity_pk:
            return HttpResponseForbidden()

    def copy_config(configs: List[AbstractChangeConfig], slot_entry: SlotEntry):
        for config in configs:
            config_copy = copy.copy(config)
            config_copy.pk = None
            config_copy.slot_entry = slot_entry
            config_copy.save()

    # Process request
    # Copy workout
    routine_copy: Routine = copy.copy(routine)
    routine_copy.pk = None
    routine_copy.created = None
    routine_copy.user = request.user
    routine_copy.is_template = False
    routine_copy.is_public = False

    # Update the start and end date
    routine_copy.start = datetime.date.today()
    routine_copy.end = routine_copy.start + routine.duration

    routine_copy.save()

    # Copy the days
    for day in routine.days.all():
        day_copy = copy.copy(day)
        day_copy.pk = None
        day_copy.routine = routine_copy
        day_copy.save()

        # Copy the slots
        for current_slot in day.slots.all():
            slot_copy = copy.copy(current_slot)
            slot_copy.pk = None
            slot_copy.day = day_copy
            slot_copy.save()

            # Copy the slot entries
            for current_entry in current_slot.entries.all():
                slot_entry_copy = copy.copy(current_entry)
                slot_entry_copy.pk = None
                slot_entry_copy.slot = slot_copy
                slot_entry_copy.save()

                copy_config(current_entry.weightconfig_set.all(), slot_entry_copy)
                copy_config(current_entry.maxweightconfig_set.all(), slot_entry_copy)

                copy_config(current_entry.repetitionsconfig_set.all(), slot_entry_copy)
                copy_config(current_entry.maxrepetitionsconfig_set.all(), slot_entry_copy)

                copy_config(current_entry.rirconfig_set.all(), slot_entry_copy)
                copy_config(current_entry.maxrirconfig_set.all(), slot_entry_copy)

                copy_config(current_entry.restconfig_set.all(), slot_entry_copy)
                copy_config(current_entry.maxrestconfig_set.all(), slot_entry_copy)

                copy_config(current_entry.setsconfig_set.all(), slot_entry_copy)
                copy_config(current_entry.maxsetsconfig_set.all(), slot_entry_copy)

    return HttpResponseRedirect(routine_copy.get_absolute_url())


@login_required
def overview_tailwind(request):
    routines = Routine.objects.filter(user=request.user)
    return render(request, 'routines/overview_tailwind.html', {
        'routines': routines
    })


@login_required
def view_tailwind(request, pk):
    routine = get_object_or_404(Routine, pk=pk)
    if routine.user != request.user and not routine.is_public:
        return HttpResponseForbidden()
    return render(request, 'routines/view_tailwind.html', {
        'routine': routine
    })


# New Tailwind + HTMX views for Onyx
from django.shortcuts import redirect
from django.db import models as django_models
from django.http import HttpResponse
from wger.manager.forms import RoutineForm, DayForm, AddExerciseForm
from wger.manager.models import Day, Slot, SlotEntry, SetsConfig, RepetitionsConfig, WeightConfig


@login_required
def add_routine_tailwind(request):
    import datetime
    if request.method == 'POST':
        form = RoutineForm(request.POST)
        if form.is_valid():
            routine = form.save(commit=False)
            routine.user = request.user
            total_weeks = form.cleaned_data.get('total_weeks') or form.cleaned_data.get('duration_weeks') or 4
            routine.total_weeks = total_weeks
            if form.cleaned_data.get('current_week'):
                routine.current_week = form.cleaned_data.get('current_week')
            routine.end = routine.start + datetime.timedelta(weeks=total_weeks)
            routine.save()
            return redirect('manager:routine:view', pk=routine.pk)
        else:
            logger.error(f"Routine form validation failed: {form.errors}")
            print(f"ROUTINE FORM ERRORS: {form.errors}")
    else:
        form = RoutineForm(initial={'start': datetime.date.today(), 'current_week': 1, 'total_weeks': 4, 'duration_weeks': 4})
    
    return render(request, 'routines/add_tailwind.html', {
        'form': form
    })


@login_required
def edit_routine_tailwind(request, pk):
    import datetime
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    initial_duration = routine.total_weeks or max(1, round((routine.end - routine.start).days / 7))
    
    if request.method == 'POST':
        form = RoutineForm(request.POST, instance=routine)
        if form.is_valid():
            routine = form.save(commit=False)
            total_weeks = form.cleaned_data.get('total_weeks') or form.cleaned_data.get('duration_weeks') or initial_duration
            routine.total_weeks = total_weeks
            if form.cleaned_data.get('current_week'):
                routine.current_week = form.cleaned_data.get('current_week')
            routine.end = routine.start + datetime.timedelta(weeks=total_weeks)
            routine.save()
            from wger.manager.helpers import reset_routine_cache
            reset_routine_cache(routine)
            return redirect('manager:routine:view', pk=routine.pk)
    else:
        form = RoutineForm(instance=routine, initial={'duration_weeks': initial_duration, 'total_weeks': initial_duration, 'current_week': routine.current_week})
        
    return render(request, 'routines/edit_tailwind.html', {
        'form': form,
        'routine': routine
    })


@login_required
def update_current_week_tailwind(request, pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    if request.method == 'POST':
        week = request.POST.get('current_week')
        if week and str(week).isdigit():
            week_num = int(week)
            if 1 <= week_num <= (routine.total_weeks or 52):
                routine.current_week = week_num
                routine.save()
                from wger.manager.helpers import reset_routine_cache
                reset_routine_cache(routine)
    
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine.pk)


@login_required
def update_routine_category_tailwind(request, pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    if request.method == 'POST':
        category = request.POST.get('category', '').strip().lower()
        if category:
            routine.category = category
            routine.save()
            from wger.manager.helpers import reset_routine_cache
            reset_routine_cache(routine)
    return redirect('manager:routine:view', pk=routine.pk)


@login_required
def delete_routine_tailwind(request, pk):
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    routine.delete()
    return redirect('manager:routine:overview')


@login_required
def add_day_tailwind(request, routine_pk):
    routine = get_object_or_404(Routine, pk=routine_pk, user=request.user)
    if request.method == 'POST':
        form = DayForm(request.POST)
        if form.is_valid():
            day = form.save(commit=False)
            day.routine = routine
            max_order = routine.days.aggregate(django_models.Max('order'))['order__max']
            day.order = (max_order or 0) + 1
            day.save()
            
            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = routine.get_absolute_url()
                return response
            return redirect('manager:routine:view', pk=routine.pk)
    else:
        form = DayForm()
    return render(request, 'routines/add_day_tailwind.html', {
        'form': form,
        'routine': routine
    })


@login_required
def delete_day_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk, routine__user=request.user)
    day.delete()
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


MUSCLE_KEYWORDS = {
    'pectoralis major': ['chest', 'pectorals', 'pectoralis major', 'petto', 'pettorali'],
    'pectorals': ['chest', 'pectorals', 'pectoralis major', 'petto', 'pettorali'],
    'chest': ['chest', 'pectorals', 'pectoralis major', 'petto', 'pettorali'],
    
    'latissimus dorsi': ['lats', 'latissimus dorsi', 'back', 'upper back', 'dorsali', 'schiena'],
    'lats': ['lats', 'latissimus dorsi', 'back', 'upper back', 'dorsali', 'schiena'],
    'upper back': ['lats', 'back', 'upper back', 'dorsali', 'schiena', 'traps', 'rhomboids'],
    'trapezius': ['back', 'traps', 'trapezius', 'trapezi'],
    'traps': ['back', 'traps', 'trapezius', 'trapezi'],
    'rhomboids': ['back', 'rhomboids', 'romboidi'],
    
    'biceps brachii': ['biceps', 'biceps brachii', 'bicipiti', 'braccia', 'arms'],
    'biceps': ['biceps', 'biceps brachii', 'bicipiti', 'braccia', 'arms'],
    'brachialis': ['biceps', 'brachialis', 'bicipiti', 'braccia', 'arms'],
    
    'triceps brachii': ['triceps', 'triceps brachii', 'tricipiti', 'braccia', 'arms'],
    'triceps': ['triceps', 'triceps brachii', 'tricipiti', 'braccia', 'arms'],
    
    'anterior deltoid': ['deltoids', 'shoulders', 'anterior deltoid', 'spalle', 'deltoidi'],
    'deltoids': ['deltoids', 'shoulders', 'deltoidi', 'spalle'],
    'shoulders': ['deltoids', 'shoulders', 'deltoidi', 'spalle'],
    'rear deltoids': ['deltoids', 'shoulders', 'rear deltoids', 'deltoidi posteriori', 'spalle'],
    
    'quadriceps femoris': ['quadriceps', 'quads', 'legs', 'quadriceps femoris', 'gambe', 'quadricipiti'],
    'quadriceps': ['quadriceps', 'quads', 'legs', 'gambe', 'quadricipiti'],
    'quads': ['quadriceps', 'quads', 'legs', 'gambe', 'quadricipiti'],
    'biceps femoris': ['legs', 'hamstrings', 'biceps femoris', 'femorali', 'gambe'],
    'gluteus maximus': ['glutes', 'legs', 'gluteus maximus', 'glutei', 'gambe'],
    'glutes': ['glutes', 'legs', 'glutei', 'gambe'],
    'gastrocnemius': ['calves', 'legs', 'polpacci', 'gambe'],
    'soleus': ['calves', 'legs', 'polpacci', 'gambe'],
    'adductors': ['legs', 'adductors', 'adduttori', 'gambe'],
    
    'rectus abdominis': ['abs', 'core', 'rectus abdominis', 'addominali', 'addome'],
    'obliquus externus abdominis': ['abs', 'core', 'obliques', 'addominali obliqui'],
    'abs': ['abs', 'core', 'addominali', 'addome'],
    'obliques': ['abs', 'core', 'obliques', 'addominali obliqui'],
}

SKILL_KEYWORDS = {
    'push up': ['push up', 'pushup', 'push-up', 'piegamenti', 'flessioni', 'piegamento'],
    'pull up': ['pull up', 'pullup', 'pull-up', 'trazioni', 'trazione', 'sbarra'],
    'dip': ['dip', 'dips', 'parallele', 'dip bar'],
    'handstand': ['handstand', 'verticale', 'verticali', 'hspu', 'handstand pushup'],
    'front lever': ['front lever', 'frontlever', 'lever', 'tirata'],
    'back lever': ['back lever', 'backlever', 'lever'],
    'l sit': ['l sit', 'l-sit', 'lsit', 'v sit', 'core', 'addominali'],
    'planche': ['planche', 'planche lean', 'maltese'],
    'squat': ['squat', 'accosciata', 'gambe', 'pistol squat'],
    'muscle up': ['muscle up', 'muscleup', 'sbarra', 'anelli'],
}


@login_required
def add_exercise_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk, routine__user=request.user)
    from_workout = (request.GET.get('from') == 'workout') or (request.POST.get('from') == 'workout')

    if request.method == 'POST':
        exercise_ids = request.POST.getlist('exercise')
        is_superset = request.POST.get('is_superset') == 'true'
        
        if exercise_ids:
            from wger.exercises.models import Exercise
            if is_superset and len(exercise_ids) > 1:
                max_order = day.slots.aggregate(django_models.Max('order'))['order__max']
                slot = Slot.objects.create(
                    day=day,
                    order=(max_order or 0) + 1
                )
                
                for idx, ex_id in enumerate(exercise_ids):
                    exercise = get_object_or_404(Exercise, id=ex_id)
                    
                    slot_entry = SlotEntry.objects.create(
                        slot=slot,
                        exercise=exercise,
                        order=idx + 1
                    )
                    
                    SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                    RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=10)
                    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)
            else:
                for ex_id in exercise_ids:
                    max_order = day.slots.aggregate(django_models.Max('order'))['order__max']
                    slot = Slot.objects.create(
                        day=day,
                        order=(max_order or 0) + 1
                    )
                    exercise = get_object_or_404(Exercise, id=ex_id)
                    
                    slot_entry = SlotEntry.objects.create(
                        slot=slot,
                        exercise=exercise,
                        order=1
                    )
                    
                    SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                    RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=10)
                    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)
                
            from wger.manager.helpers import reset_routine_cache
            reset_routine_cache(day.routine)
            
            if from_workout:
                from django.urls import reverse
                redirect_url = reverse('manager:day:overview', kwargs={'routine_pk': day.routine.pk, 'day_pk': day.pk})
            else:
                redirect_url = day.routine.get_absolute_url()

            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = redirect_url
                return response

            if from_workout:
                return redirect('manager:day:overview', routine_pk=day.routine.pk, day_pk=day.pk)
            return redirect('manager:routine:view', pk=day.routine.pk)
    else:
        form = AddExerciseForm()
        
    from wger.manager.services.exercise_catalog import get_cached_exercise_catalog
    catalog_dto = get_cached_exercise_catalog(language_code=getattr(request, 'LANGUAGE_CODE', 'it'))
    
    exercises_list = catalog_dto['items']
    muscles_list = catalog_dto['muscles']
    equipment_list = catalog_dto['equipment']
    categories_list = catalog_dto['categories']
    skills_list = ['Push Up', 'Pull Up', 'Dip', 'Handstand', 'Front Lever', 'Back Lever', 'Planche', 'Muscle Up', 'Squat', 'Other']
    
    exercise_counts = {
        'all': len(exercises_list),
        'gym': sum(not ex.get('is_calisthenics', False) for ex in exercises_list),
        'calisthenics': sum(ex.get('is_calisthenics', False) for ex in exercises_list),
    }

    import json
    from django.core.serializers.json import DjangoJSONEncoder
    catalog_json = json.dumps(catalog_dto, cls=DjangoJSONEncoder, ensure_ascii=False)
        
    return render(request, 'routines/add_exercise_tailwind.html', {
        'form': form,
        'day': day,
        'exercises_list': exercises_list,
        'catalog_dto': catalog_dto,
        'catalog_json': catalog_json,
        'muscles_list': muscles_list,
        'skills_list': skills_list,
        'equipment_list': equipment_list,
        'categories_list': categories_list,
        'exercise_counts': exercise_counts,
        'from_workout': from_workout,
    })


@login_required
def delete_exercise_tailwind(request, routine_pk, day_pk, slot_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    slot.delete()
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


@login_required
def add_set_tailwind(request, routine_pk, day_pk, slot_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    if request.method == 'POST':
        reps = request.POST.get('reps')
        weight = request.POST.get('weight')
        comment = request.POST.get('comment', '').strip()
        exercise_id = request.POST.get('exercise_id')
        
        target_exercise = None
        if exercise_id:
            from wger.exercises.models import Exercise
            target_exercise = get_object_or_404(Exercise, id=exercise_id)
        else:
            first_entry = slot.entries.first()
            if first_entry:
                target_exercise = first_entry.exercise
                
        if weight is None or str(weight).strip() == '':
            weight = 0

        if target_exercise and reps:
            max_order = slot.entries.aggregate(django_models.Max('order'))['order__max']
            slot_entry = SlotEntry.objects.create(
                slot=slot,
                exercise=target_exercise,
                order=(max_order or 0) + 1,
                comment=comment
            )
            SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
            RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=reps)
            WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=weight)
            
            from wger.manager.helpers import reset_routine_cache
            reset_routine_cache(slot.day.routine)
            
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


@login_required
def delete_set_tailwind(request, routine_pk, day_pk, slot_pk, entry_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    entry = get_object_or_404(SlotEntry, pk=entry_pk, slot=slot)
    
    if slot.entries.count() <= 1:
        slot.delete()
    else:
        entry.delete()
        
    from wger.manager.helpers import reset_routine_cache
    reset_routine_cache(slot.day.routine)
    
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


@login_required
def update_set_tailwind(request, routine_pk, day_pk, slot_pk, entry_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    entry = get_object_or_404(SlotEntry, pk=entry_pk, slot=slot)
    if request.method == 'POST':
        reps = request.POST.get('reps')
        weight = request.POST.get('weight')
        
        if reps is not None:
            rep_config, created = RepetitionsConfig.objects.get_or_create(
                slot_entry=entry,
                iteration=1,
                defaults={'value': reps}
            )
            if not created:
                rep_config.value = reps
                rep_config.save()
                
        if weight is not None:
            if str(weight).strip() == '':
                weight = 0
            weight_config, created = WeightConfig.objects.get_or_create(
                slot_entry=entry,
                iteration=1,
                defaults={'value': weight}
            )
            if not created:
                weight_config.value = weight
                weight_config.save()
                
        from wger.manager.helpers import reset_routine_cache
        reset_routine_cache(slot.day.routine)
        
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


@login_required
def update_set_notes_tailwind(request, routine_pk, day_pk, slot_pk, entry_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    entry = get_object_or_404(SlotEntry, pk=entry_pk, slot=slot)
    if request.method == 'POST':
        comment = request.POST.get('comment', '').strip()
        entry.comment = comment
        entry.save()
        
        from wger.manager.helpers import reset_routine_cache
        reset_routine_cache(slot.day.routine)
        
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


@login_required
def update_notes_tailwind(request, routine_pk, day_pk, slot_pk):
    slot = get_object_or_404(Slot, pk=slot_pk, day_id=day_pk, day__routine_id=routine_pk, day__routine__user=request.user)
    if request.method == 'POST':
        notes = request.POST.get('notes', '').strip()
        slot.comment = notes
        slot.save()
        
        from wger.manager.helpers import reset_routine_cache
        reset_routine_cache(slot.day.routine)
        
    if request.headers.get('HX-Request'):
        response = HttpResponse()
        response['HX-Redirect'] = slot.day.routine.get_absolute_url()
        return response
    return redirect('manager:routine:view', pk=routine_pk)


def _async_push_to_baserow(name, instructions, skill_family, target_muscle, equipment_name):
    baserow_url = os.environ.get('BASEROW_URL', 'http://localhost:8080').rstrip('/')
    baserow_token = os.environ.get('BASEROW_TOKEN')
    baserow_table_id = os.environ.get('BASEROW_TABLE_ID', '322')

    if not baserow_token:
        logger.warning("Baserow token not configured. Skipping sync.")
        return

    headers = {
        "Authorization": f"Token {baserow_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "Name": name,
        "Instructions": instructions,
        "Skill Family": skill_family,
        "Target Muscle": target_muscle,
        "Equipment": equipment_name,
        "Is Published": True,
        "Discipline": "calisthenics",
        "Source Exercise ID": f"custom-{uuid.uuid4().hex[:8]}"
    }

    url = f"{baserow_url}/api/database/rows/table/{baserow_table_id}/?user_field_names=true"
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Successfully synced custom exercise '{name}' to Baserow.")
    except Exception as e:
        logger.error(f"Failed to sync custom exercise to Baserow: {e}")


@login_required
@require_POST
def add_custom_exercise_tailwind(request, routine_pk, day_pk):
    name = request.POST.get('name', '').strip()
    instructions = request.POST.get('instructions', '').strip()
    skill_family = request.POST.get('skill_family', 'other').strip()
    target_muscle_name = request.POST.get('target_muscle', '').strip()
    weighted = request.POST.get('weighted') == 'on'

    if not name:
        return JsonResponse({'status': 'error', 'message': 'Name is required'}, status=400)

    try:
        # 1. Create CalisthenicsExercise locally
        source_id = f"custom-{uuid.uuid4().hex[:8]}"
        slug = f"{slugify(name)}-{source_id}"
        equipment_name = 'weighted body weight' if weighted else 'body weight'
        eq_name = 'Dumbbells' if weighted else 'Body weight'
        instructions_list = [line.strip() for line in instructions.split('\n') if line.strip()]

        existing_trans = Translation.objects.filter(name__iexact=name).first()
        existing_cal = CalisthenicsExercise.objects.filter(name__iexact=name).first()

        if existing_trans and existing_trans.exercise:
            base_exercise = existing_trans.exercise
        elif existing_cal:
            base_exercise = Exercise.objects.filter(uuid=existing_cal.id).first()
        else:
            base_exercise = None

        if not base_exercise:
            # 1. Create CalisthenicsExercise locally
            source_id = f"custom-{uuid.uuid4().hex[:8]}"
            slug = f"{slugify(name)}-{source_id}"

            cal_exercise = CalisthenicsExercise.objects.create(
                source='custom',
                source_exercise_id=source_id,
                slug=slug,
                name=name,
                instructions=instructions_list,
                target_muscle=target_muscle_name,
                equipment=equipment_name,
                skill_family=skill_family,
                discipline='calisthenics',
                is_published=True
            )

            # 2. Create native Exercise
            category, _created = ExerciseCategory.objects.get_or_create(name='Calisthenics')
            default_license = License.objects.first()
            if not default_license:
                default_license = License.objects.create(
                    short_name='CC-BY-SA 4.0',
                    full_name='Creative Commons Attribution Share Alike 4.0'
                )
            
            base_exercise = Exercise.objects.create(
                uuid=cal_exercise.id,
                category=category,
                license=default_license
            )

            # 3. Associate equipment
            equipment, _created = Equipment.objects.get_or_create(name=eq_name)
            base_exercise.equipment.add(equipment)

            # 4. Associate target muscle
            if target_muscle_name:
                muscle, _created = Muscle.objects.get_or_create(
                    name=target_muscle_name.capitalize(),
                    defaults={'name_en': target_muscle_name, 'is_front': True}
                )
                base_exercise.muscles.add(muscle)

            # 5. Create English Translation
            english_lang = Language.objects.filter(short_name='en').first()
            if not english_lang:
                english_lang = Language.objects.first()
            if not english_lang:
                english_lang = Language.objects.create(short_name='en', full_name='English')

            Translation.objects.create(
                exercise=base_exercise,
                language=english_lang,
                name=name,
                description="\n".join(instructions_list),
                license=default_license
            )

            # 6. Create initial tags
            tags = ['bodyweight', 'calisthenics', 'custom']
            if weighted:
                tags.append('weighted')
            if skill_family != 'other':
                tags.append(skill_family.replace('_', '-'))
            for t in tags:
                ExerciseTag.objects.get_or_create(exercise=cal_exercise, tag=t)

            # 7. Start background thread to push to Baserow
            threading.Thread(
                target=_async_push_to_baserow,
                args=(name, instructions, skill_family, target_muscle_name, equipment_name),
                daemon=True
            ).start()

        # 8. Add exercise to the routine day
        day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk, routine__user=request.user)
        max_order = day.slots.aggregate(django_models.Max('order'))['order__max']
        slot = Slot.objects.create(
            day=day,
            order=(max_order or 0) + 1,
        )
        slot_entry = SlotEntry.objects.create(
            slot=slot,
            exercise=base_exercise,
            order=1,
        )
        SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
        RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=10)
        WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)

        from wger.manager.helpers import reset_routine_cache
        reset_routine_cache(day.routine)

        # Invalidate catalog cache so newly added exercise appears on refresh
        from wger.manager.services.exercise_catalog import bump_catalog_version
        bump_catalog_version()

        from_workout = request.POST.get('from') == 'workout' or 'from=workout' in request.META.get('HTTP_REFERER', '')
        if from_workout:
            redirect_url = reverse('manager:day:overview', kwargs={'routine_pk': day.routine.pk, 'day_pk': day.pk})
        else:
            redirect_url = reverse('manager:routine:view', kwargs={'pk': day.routine.pk})

        is_json_request = (
            'application/json' in request.headers.get('Accept', '')
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or request.content_type == 'application/json'
            or request.POST.get('format') == 'json'
        )

        if is_json_request:
            return JsonResponse({
                'status': 'success',
                'id': base_exercise.id,
                'name': name,
                'muscles': target_muscle_name,
                'equipment': eq_name,
                'category': 'Calisthenics',
                'is_calisthenics': True,
                'skill_family': skill_family,
                'redirect_url': redirect_url,
            })

        if request.headers.get('HX-Request'):
            from django.http import HttpResponse
            response = HttpResponse()
            response['HX-Redirect'] = redirect_url
            return response

        messages.success(request, _("Esercizio custom creato con successo!"))
        response = redirect(redirect_url)
        response['HX-Redirect'] = redirect_url
        return response
    except Exception as e:
        logger.error(f"Error creating custom exercise: {e}", exc_info=True)
        if 'application/json' in request.headers.get('Accept', '') or request.content_type == 'application/json':
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
        messages.error(request, _(f"Errore durante la creazione dell'esercizio: {e}"))
        return redirect(reverse('manager:routine:view', kwargs={'pk': routine_pk}))

