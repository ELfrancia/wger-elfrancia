# -*- coding: utf-8 -*-
import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.db import models as django_models
from wger.manager.models import Day, WorkoutSession, WorkoutLog, SlotEntry, SetsConfig, RepetitionsConfig, WeightConfig
from wger.manager.helpers import reset_routine_cache


@login_required
def log_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk)
    if day.routine.user != request.user:
        return HttpResponseForbidden()

    # Track active session ID for this day using django session cookies
    session_key = f'active_session_{day_pk}'
    session = None
    
    # If ?start=true is passed, we explicitly want to start a brand new session
    if request.GET.get('start') == 'true':
        session = WorkoutSession.objects.create(
            user=request.user,
            routine_id=routine_pk,
            day=day,
            date=datetime.date.today(),
            time_start=timezone.localtime(timezone.now()).time()
        )
        request.session[session_key] = str(session.id)
        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    # Otherwise, try to load existing active session
    session_id = request.session.get(session_key)
    if session_id:
        session = WorkoutSession.objects.filter(id=session_id, user=request.user).first()

    # Fallback to the latest session for today, or create one if none exists
    if not session:
        session = WorkoutSession.objects.filter(
            user=request.user,
            routine_id=routine_pk,
            day=day,
            date=datetime.date.today()
        ).order_by('-id').first()
        
        if not session:
            session = WorkoutSession.objects.create(
                user=request.user,
                routine_id=routine_pk,
                day=day,
                date=datetime.date.today(),
                time_start=timezone.localtime(timezone.now()).time()
            )
        request.session[session_key] = str(session.id)

    if session and not session.time_start:
        session.time_start = timezone.localtime(timezone.now()).time()
        session.save()

    if request.method == 'POST':
        action = request.POST.get('action')
        exercise_id = request.POST.get('exercise_id')
        slot_entry_id = request.POST.get('slot_entry_id')

        # Sanitize integer IDs in case of localized formatting
        if exercise_id:
            exercise_id = ''.join(c for c in str(exercise_id) if c.isdigit())
        if slot_entry_id:
            slot_entry_id = ''.join(c for c in str(slot_entry_id) if c.isdigit())

        # Determine target slot first, if possible
        slot = None
        if exercise_id:
            slot = day.slots.filter(entries__exercise_id=exercise_id).distinct().first()

        if action == 'restart_workout':
            session.logs.all().delete()
            session.time_start = timezone.localtime(timezone.now()).time()
            session.time_end = None
            session.save()
            return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

        elif action == 'finish_workout':
            session.time_end = timezone.localtime(timezone.now()).time()
            session.save()
            if session_key in request.session:
                del request.session[session_key]
            return redirect('weight:overview')

        elif action == 'complete_exercise':
            if slot:
                # Get already logged set IDs for this exercise in this session
                logged_set_ids = list(session.logs.filter(exercise_id=exercise_id).values_list('slot_entry_id', flat=True))
                all_set_ids = [entry.id for entry in slot.entries.all()]

                # Check if all sets are already completed
                all_completed = all(sid in logged_set_ids for sid in all_set_ids)

                if all_completed:
                    # Uncheck: Delete all logs for this exercise in this session
                    session.logs.filter(exercise_id=exercise_id).delete()
                else:
                    # Check: Log all remaining/unlogged sets using configured default values
                    for slot_entry in slot.entries.all():
                        if slot_entry.id not in logged_set_ids:
                            reps = slot_entry.reps_config.reps
                            weight = slot_entry.weight_config.weight
                            if reps is None:
                                reps = 10
                            if weight is None:
                                weight = 0
                            WorkoutLog.objects.create(
                                user=request.user,
                                session=session,
                                exercise_id=exercise_id,
                                routine_id=routine_pk,
                                slot_entry_id=slot_entry.id,
                                repetitions=reps,
                                weight=weight,
                                date=timezone.now()
                            )

        elif action == 'delete_set':
            session.logs.filter(slot_entry_id=slot_entry_id).delete()
            if not slot and slot_entry_id:
                slot_entry = SlotEntry.objects.filter(id=slot_entry_id, slot__day=day).first()
                if slot_entry:
                    slot = slot_entry.slot

        elif action == 'add_set':
            if slot:
                from wger.exercises.models import Exercise
                exercise = get_object_or_404(Exercise, id=exercise_id)
                max_order = slot.entries.aggregate(django_models.Max('order'))['order__max']
                slot_entry = SlotEntry.objects.create(
                    slot=slot,
                    exercise=exercise,
                    order=(max_order or 0) + 1
                )
                SetsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=1)
                RepetitionsConfig.objects.create(slot_entry=slot_entry, iteration=1, value=10)
                WeightConfig.objects.create(slot_entry=slot_entry, iteration=1, value=0)
                reset_routine_cache(day.routine)

        elif action == 'delete_set_config':
            slot_entry = get_object_or_404(SlotEntry, id=slot_entry_id, slot__day=day)
            slot = slot_entry.slot
            
            if slot.entries.count() <= 1:
                slot.delete()
                reset_routine_cache(day.routine)
                if request.headers.get('HX-Request'):
                    return HttpResponse("")
                return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)
            else:
                slot_entry.delete()
                reset_routine_cache(day.routine)

        else:
            # Default set logging
            repetitions = request.POST.get('repetitions')
            weight = request.POST.get('weight')
            rir = request.POST.get('rir') or None

            try:
                repetitions = int(repetitions)
            except (TypeError, ValueError):
                repetitions = 0

            try:
                from decimal import Decimal
                weight = Decimal(weight)
            except (TypeError, ValueError):
                from decimal import Decimal
                weight = Decimal('0')

            # Create WorkoutLog entry
            log_entry = WorkoutLog.objects.create(
                user=request.user,
                session=session,
                exercise_id=exercise_id,
                routine_id=routine_pk,
                slot_entry_id=slot_entry_id,
                repetitions=repetitions,
                weight=weight,
                rir=rir,
                date=timezone.now()
            )
            if not slot and slot_entry_id:
                slot_entry = SlotEntry.objects.filter(id=slot_entry_id, slot__day=day).first()
                if slot_entry:
                    slot = slot_entry.slot

        # Common rendering response for HTMX request
        if request.headers.get('HX-Request'):
            session_logged_set_ids = list(session.logs.values_list('slot_entry_id', flat=True))
            logged_set_ids_set = set(session_logged_set_ids)
            completed_exercise_ids = []
            for s in day.slots.all():
                all_set_ids = [entry.id for entry in s.entries.all()]
                if all_set_ids and all(sid in logged_set_ids_set for sid in all_set_ids):
                    if s.obj:
                        completed_exercise_ids.append(s.obj.id)

            return render(request, 'workout/includes/exercise_card.html', {
                'slot': slot,
                'logged_set_ids': session_logged_set_ids,
                'completed_exercise_ids': completed_exercise_ids,
                'day': day,
            })

        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    # Calculate initial progress percentage
    total_sets = sum(slot.entries.count() for slot in day.slots.all())
    logged_set_ids = list(session.logs.values_list('slot_entry_id', flat=True))
    completed_sets = len(logged_set_ids)
    progress_percentage = int((completed_sets / total_sets) * 100) if total_sets > 0 else 0

    elapsed_seconds = 0
    if session.time_start:
        now = timezone.localtime(timezone.now())
        start_datetime = datetime.datetime.combine(session.date, session.time_start)
        if timezone.is_naive(start_datetime):
            start_datetime = timezone.make_aware(start_datetime)
        elapsed = (now - start_datetime).total_seconds()
        elapsed_seconds = max(0, int(elapsed))

    logged_set_ids_set = set(logged_set_ids)
    completed_exercise_ids = []
    for s in day.slots.all():
        all_set_ids = [entry.id for entry in s.entries.all()]
        if all_set_ids and all(sid in logged_set_ids_set for sid in all_set_ids):
            if s.obj:
                completed_exercise_ids.append(s.obj.id)

    return render(request, 'workout/log_tailwind.html', {
        'day': day,
        'session': session,
        'logged_set_ids': logged_set_ids,
        'completed_exercise_ids': completed_exercise_ids,
        'progress_percentage': progress_percentage,
        'elapsed_seconds': elapsed_seconds,
    })

