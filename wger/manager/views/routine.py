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
from django.contrib.auth.decorators import login_required
from django.http import (
    HttpResponseForbidden,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, render
from django.utils.text import slugify
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
            duration_weeks = form.cleaned_data['duration_weeks']
            routine.end = routine.start + datetime.timedelta(weeks=duration_weeks)
            routine.save()
            return redirect('manager:routine:view', pk=routine.pk)
    else:
        form = RoutineForm(initial={'start': datetime.date.today(), 'duration_weeks': 6})
    
    return render(request, 'routines/add_tailwind.html', {
        'form': form
    })


@login_required
def edit_routine_tailwind(request, pk):
    import datetime
    routine = get_object_or_404(Routine, pk=pk, user=request.user)
    initial_duration = max(1, round((routine.end - routine.start).days / 7))
    
    if request.method == 'POST':
        form = RoutineForm(request.POST, instance=routine)
        if form.is_valid():
            routine = form.save(commit=False)
            duration_weeks = form.cleaned_data['duration_weeks']
            routine.end = routine.start + datetime.timedelta(weeks=duration_weeks)
            routine.save()
            return redirect('manager:routine:view', pk=routine.pk)
    else:
        form = RoutineForm(instance=routine, initial={'duration_weeks': initial_duration})
        
    return render(request, 'routines/edit_tailwind.html', {
        'form': form,
        'routine': routine
    })


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


@login_required
def add_exercise_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk, routine__user=request.user)
    if request.method == 'POST':
        exercise_ids = request.POST.getlist('exercise')
        
        if exercise_ids:
            max_order = day.slots.aggregate(django_models.Max('order'))['order__max']
            slot = Slot.objects.create(
                day=day,
                order=(max_order or 0) + 1
            )
            
            for idx, ex_id in enumerate(exercise_ids):
                from wger.exercises.models import Exercise
                exercise = get_object_or_404(Exercise, id=ex_id)
                
                slot_entry = SlotEntry.objects.create(
                    slot=slot,
                    exercise=exercise,
                    order=idx + 1
                )
                
                SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=10)
                WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)
                
            from wger.manager.helpers import reset_routine_cache
            reset_routine_cache(day.routine)
            
            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = day.routine.get_absolute_url()
                return response
            return redirect('manager:routine:view', pk=day.routine.pk)
    else:
        form = AddExerciseForm()
        
    # Build exercises list with prefetching to avoid N+1 queries
    exercise_qs = form.fields['exercise'].queryset.prefetch_related('muscles', 'translations')
    
    from wger.exercises.models import CalisthenicsExercise
    calisthenics_map = {
        str(cal.id): cal for cal in CalisthenicsExercise.objects.all()
    }
    
    exercises_list = []
    muscles_set = set()
    skills_set = set()
    
    for ex in exercise_qs:
        translation = ex.get_translation()
        name = translation.name if translation else "Unnamed Exercise"
        cal = calisthenics_map.get(str(ex.uuid))
        
        preview_url = None
        skill_family = 'Other'
        if cal:
            preview_url = cal.demo_media_url
            if cal.skill_family:
                skill_family = cal.skill_family.replace('_', ' ').title()
                
        if not preview_url:
            img = ex.exerciseimage_set.first()
            if img:
                preview_url = img.image.url
                
        muscles = [m.name for m in ex.muscles.all()]
        for m in muscles:
            muscles_set.add(m)
        if skill_family:
            skills_set.add(skill_family)
            
        exercises_list.append({
            'id': ex.id,
            'name': name,
            'preview_url': preview_url or '',
            'muscles': ','.join(muscles),
            'muscles_display': ' • '.join(muscles),
            'skill_family': skill_family,
        })
        
    muscles_list = sorted(list(muscles_set))
    skills_list = sorted(list(skills_set))
        
    return render(request, 'routines/add_exercise_tailwind.html', {
        'form': form,
        'day': day,
        'exercises_list': exercises_list,
        'muscles_list': muscles_list,
        'skills_list': skills_list,
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
                
        if target_exercise and reps and weight:
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

    # 1. Create CalisthenicsExercise locally
    source_id = f"custom-{uuid.uuid4().hex[:8]}"
    slug = f"{slugify(name)}-{source_id}"
    equipment_name = 'weighted body weight' if weighted else 'body weight'
    
    instructions_list = [line.strip() for line in instructions.split('\n') if line.strip()]

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
    category, _ = ExerciseCategory.objects.get_or_create(name='Calisthenics')
    default_license = License.objects.first()
    
    base_exercise = Exercise.objects.create(
        uuid=cal_exercise.id,
        category=category,
        license=default_license
    )

    # 3. Associate equipment
    eq_name = 'Dumbbells' if weighted else 'Body weight'
    equipment, _ = Equipment.objects.get_or_create(name=eq_name)
    base_exercise.equipment.add(equipment)

    # 4. Associate target muscle
    if target_muscle_name:
        muscle, _ = Muscle.objects.get_or_create(
            name=target_muscle_name.capitalize(),
            defaults={'name_en': target_muscle_name, 'is_front': True}
        )
        base_exercise.muscles.add(muscle)

    # 5. Create English Translation
    english_lang = Language.objects.get(short_name='en')
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

    # Return response
    return JsonResponse({
        'status': 'success',
        'id': base_exercise.id,
        'name': name,
        'muscles': target_muscle_name,
        'skill_family': skill_family.replace('_', ' ').title()
    })


