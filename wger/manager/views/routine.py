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
import decimal
from decimal import Decimal, DecimalException
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
    replace_slot_id = request.GET.get('replace_slot') or request.POST.get('replace_slot')

    if request.method == 'POST':
        exercise_ids = request.POST.getlist('exercise')
        is_superset = request.POST.get('is_superset') == 'true'

        # Replace/swap the exercise of an existing slot (used during an active workout)
        if replace_slot_id and exercise_ids:
            from django.urls import reverse
            from wger.exercises.models import Exercise
            from wger.manager.models import WorkoutLog
            from wger.manager.helpers import reset_routine_cache

            slot = get_object_or_404(Slot, pk=replace_slot_id, day=day)
            new_exercise = get_object_or_404(Exercise, id=exercise_ids[0])

            # Drop any sets already logged for this slot in a non-finished session
            WorkoutLog.objects.filter(
                slot_entry__slot=slot,
                session__user=request.user,
            ).exclude(session__status='finished').delete()

            slot.entries.update(exercise=new_exercise)
            reset_routine_cache(day.routine)

            redirect_url = reverse(
                'manager:day:overview',
                kwargs={'routine_pk': day.routine.pk, 'day_pk': day.pk},
            )
            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = redirect_url
                return response
            return HttpResponseRedirect(redirect_url)

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
                    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=Decimal('0'))
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
                    WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=Decimal('0'))
                
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
        'replace_slot_id': replace_slot_id,
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
            weight_val = Decimal('0')
        else:
            try:
                clean_w = str(weight).strip().replace(',', '.')
                weight_val = Decimal(clean_w)
            except (decimal.DecimalException, ValueError, TypeError):
                weight_val = Decimal('0')

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
            WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=weight_val)
            
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
            clean_w = str(weight).strip().replace(',', '.')
            if clean_w == '':
                weight_val = Decimal('0')
            else:
                try:
                    weight_val = Decimal(clean_w)
                except (decimal.DecimalException, ValueError, TypeError):
                    weight_val = Decimal('0')

            weight_config, created = WeightConfig.objects.get_or_create(
                slot_entry=entry,
                iteration=1,
                defaults={'value': weight_val}
            )
            if not created:
                weight_config.value = weight_val
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
def add_custom_exercise_tailwind(request, routine_pk, day_pk):
    if request.method != 'POST':
        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    name = request.POST.get('name', '').strip()
    instructions = request.POST.get('instructions', '').strip()
    skill_family = request.POST.get('skill_family', 'other').strip()
    target_muscle_name = request.POST.get('target_muscle', '').strip()
    weighted = request.POST.get('weighted') == 'on'

    if not name:
        return JsonResponse({'status': 'error', 'message': 'Name is required'}, status=400)

    try:
        # Determine category & discipline based on weighted / skill_family
        if weighted and skill_family == 'other':
            category_name = 'Palestra'
            discipline_name = 'gym'
            is_calisthenics = False
            equipment_name = 'free weight'
            eq_name = 'Dumbbells'
        else:
            category_name = 'Calisthenics'
            discipline_name = 'calisthenics'
            is_calisthenics = True
            equipment_name = 'weighted body weight' if weighted else 'body weight'
            eq_name = 'Weighted' if weighted else 'Body weight'

        instructions_list = [line.strip() for line in instructions.split('\n') if line.strip()]

        existing_trans = Translation.objects.filter(name__iexact=name).first()
        existing_cal = CalisthenicsExercise.objects.filter(name__iexact=name).first()

        if existing_trans and existing_trans.exercise:
            base_exercise = existing_trans.exercise
        elif existing_cal:
            base_exercise = Exercise.objects.filter(uuid=existing_cal.id).first()
        else:
            base_exercise = None

        default_license = License.objects.first()
        if not default_license:
            default_license = License.objects.create(
                short_name='CC-BY-SA 4.0',
                full_name='Creative Commons Attribution Share Alike 4.0'
            )

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
                discipline=discipline_name,
                is_published=True
            )

            # 2. Create native Exercise
            category, _created = ExerciseCategory.objects.get_or_create(name=category_name)
            
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

            # 5. Create Translation for BOTH 'it' (Italian) and 'en' (English)
            lang_it = Language.objects.filter(short_name='it').first()
            if not lang_it:
                lang_it = Language.objects.create(short_name='it', full_name='Italiano')

            lang_en = Language.objects.filter(short_name='en').first()
            if not lang_en:
                lang_en = Language.objects.create(short_name='en', full_name='English')

            for lang in [lang_it, lang_en]:
                Translation.objects.update_or_create(
                    exercise=base_exercise,
                    language=lang,
                    defaults={
                        'name': name,
                        'description': "\n".join(instructions_list),
                        'license': default_license
                    }
                )

            # 6. Create initial tags
            tags = ['custom']
            if is_calisthenics:
                tags.extend(['bodyweight', 'calisthenics'])
            else:
                tags.extend(['gym', 'weights'])
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
        else:
            # Ensure both translations exist for existing base exercise
            lang_it = Language.objects.filter(short_name='it').first()
            if not lang_it:
                lang_it = Language.objects.create(short_name='it', full_name='Italiano')

            lang_en = Language.objects.filter(short_name='en').first()
            if not lang_en:
                lang_en = Language.objects.create(short_name='en', full_name='English')

            for lang in [lang_it, lang_en]:
                Translation.objects.get_or_create(
                    exercise=base_exercise,
                    language=lang,
                    defaults={
                        'name': name,
                        'description': "\n".join(instructions_list),
                        'license': default_license
                    }
                )

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
        WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=Decimal('0'))

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
                'category': category_name,
                'is_calisthenics': is_calisthenics,
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


@login_required
def exercise_history_stats(request, exercise_pk):
    """
    Personal history for a single exercise for the current user.

    Returns aggregate records, a chronological progression series (one point per
    session/day) and the list of the most recent sessions with their sets.
    Consumed by the "STORICO" tab of the exercise detail overlay
    (wger/core/templates/template_tailwind.html).
    """
    from wger.manager.models import WorkoutLog

    exercise = get_object_or_404(Exercise, pk=exercise_pk)

    logs = list(
        WorkoutLog.objects
        .filter(user=request.user, exercise_id=exercise_pk)
        .select_related('session')
        .order_by('date')
    )

    def _f(value):
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError, DecimalException):
            return None

    translation = exercise.get_translation()
    payload = {
        'exercise_id': exercise.pk,
        'name': translation.name if translation else str(exercise),
        'stats': None,
        'chart': [],
        'sessions': [],
    }

    if not logs:
        return JsonResponse(payload)

    # ---- Group by session (fallback: calendar day) -------------------------
    groups = {}
    order = []
    for log in logs:
        key = log.session_id or ('d', log.date.date())
        if key not in groups:
            groups[key] = {
                'session_id': str(log.session_id) if log.session_id else None,
                'date': log.date.date().isoformat(),
                'sets': [],
            }
            order.append(key)
        weight = _f(log.weight)
        reps = _f(log.repetitions)
        groups[key]['sets'].append({
            'weight': weight,
            'reps': reps,
            'rir': _f(log.rir),
        })

    def _epley(weight, reps):
        if weight is None or reps is None or reps <= 0:
            return None
        return weight * (1 + reps / 30.0)

    chart = []
    for key in order:
        g = groups[key]
        weights = [s['weight'] for s in g['sets'] if s['weight'] is not None]
        volume = sum(
            (s['weight'] or 0) * (s['reps'] or 0)
            for s in g['sets']
            if s['weight'] is not None and s['reps'] is not None
        )
        one_rms = [
            v for v in (_epley(s['weight'], s['reps']) for s in g['sets'])
            if v is not None
        ]
        chart.append({
            'date': g['date'],
            'top_weight': round(max(weights), 2) if weights else None,
            'est_1rm': round(max(one_rms), 1) if one_rms else None,
            'volume': round(volume, 1),
        })

    # ---- Aggregate records -----------------------------------------------
    all_weights = [_f(l.weight) for l in logs if l.weight is not None]
    all_reps = [_f(l.repetitions) for l in logs if l.repetitions is not None]
    total_volume = sum(
        (_f(l.weight) or 0) * (_f(l.repetitions) or 0)
        for l in logs
        if l.weight is not None and l.repetitions is not None
    )

    max_weight = max(all_weights) if all_weights else None
    max_weight_date = None
    if max_weight is not None:
        max_weight_date = next(
            (l.date.date().isoformat() for l in logs if _f(l.weight) == max_weight),
            None,
        )

    best_est_1rm = None
    best_set_label = None
    best_set_score = -1
    for l in logs:
        w = _f(l.weight)
        r = _f(l.repetitions)
        one_rm = _epley(w, r)
        if one_rm is not None and one_rm > (best_est_1rm or 0):
            best_est_1rm = one_rm
        # "best set": highest estimated 1RM, else highest weight, else most reps
        score = one_rm if one_rm is not None else (w if w is not None else (r or 0) / 1000.0)
        if score > best_set_score:
            best_set_score = score
            if w is not None and r is not None:
                best_set_label = f'{w:g} kg × {r:g}'
            elif w is not None:
                best_set_label = f'{w:g} kg'
            elif r is not None:
                best_set_label = f'{r:g} rep'

    payload['stats'] = {
        'max_weight': round(max_weight, 2) if max_weight is not None else None,
        'max_weight_date': max_weight_date,
        'est_1rm': round(best_est_1rm, 1) if best_est_1rm is not None else None,
        'max_reps': round(max(all_reps), 0) if all_reps else None,
        'best_set_label': best_set_label,
        'total_volume': round(total_volume, 1),
        'total_sets': len(logs),
        'sessions_count': len(order),
        'last_performed': logs[-1].date.date().isoformat(),
        'is_bodyweight': not all_weights,
    }
    payload['chart'] = chart
    payload['sessions'] = [groups[key] for key in reversed(order)][:40]

    # ---- Progressive-overload suggestion for the next session -------------
    last_group = groups[order[-1]]
    last_best = None
    for s in last_group['sets']:
        w = s['weight'] if s['weight'] is not None else -1
        r = s['reps'] if s['reps'] is not None else -1
        key_val = (w, r)
        if last_best is None or key_val > last_best[0]:
            last_best = (key_val, s)

    suggestion = None
    if last_best is not None:
        w = last_best[1]['weight']
        r = last_best[1]['reps']
        recent_top = [c['top_weight'] for c in chart[-3:] if c['top_weight'] is not None]
        stagnating = len(recent_top) == 3 and recent_top[0] >= recent_top[-1]

        if payload['stats']['is_bodyweight'] or w is None:
            reps = int(r) if r else 8
            suggestion = {'type': 'reps', 'text': f'Prossima volta: {reps + 1} rep'}
        else:
            inc = 2.5 if w >= 40 else 1.25
            if r is not None and r >= 12:
                suggestion = {'type': 'weight',
                              'text': f'Prossima volta: {w + inc:g} kg × 8'}
            elif stagnating and r is not None and r <= 5:
                suggestion = {'type': 'deload',
                              'text': f'Fermo da 3 sessioni: prova {round(w * 0.9):g} kg × {int(r) + 3} e risali'}
            elif r is not None and r >= 8:
                suggestion = {'type': 'reps',
                              'text': f'Prossima volta: {w:g} kg × {int(r) + 1}'}
            else:
                suggestion = {'type': 'weight',
                              'text': f'Prossima volta: {w + inc:g} kg × {int(r) if r else 5}'}
    payload['suggestion'] = suggestion

    return JsonResponse(payload)

