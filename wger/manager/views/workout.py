# -*- coding: utf-8 -*-
import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from wger.manager.models import Day, WorkoutSession, WorkoutLog, SlotEntry


@login_required
def log_tailwind(request, routine_pk, day_pk):
    day = get_object_or_404(Day, pk=day_pk, routine_id=routine_pk)
    if day.routine.user != request.user:
        return HttpResponseForbidden()

    # Get or create today's workout session for this routine/day
    session, created = WorkoutSession.objects.get_or_create(
        user=request.user,
        routine_id=routine_pk,
        day=day,
        date=datetime.date.today()
    )

    if request.method == 'POST':
        exercise_id = request.POST.get('exercise_id')
        slot_entry_id = request.POST.get('slot_entry_id')
        repetitions = request.POST.get('repetitions')
        weight = request.POST.get('weight')
        rir = request.POST.get('rir') or None

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

        # If it's an HTMX request, we can return a success fragment (e.g. green checkmark)
        if request.headers.get('HX-Request'):
            return HttpResponse(
                '<div class="w-8 h-8 rounded-full bg-primary-fixed text-[#131313] flex items-center justify-center font-bold">✓</div>'
            )
        
        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    # Fetch logs for the current session to mark completed sets
    logged_set_ids = list(session.logs.values_list('slot_entry_id', flat=True))

    return render(request, 'workout/log_tailwind.html', {
        'day': day,
        'session': session,
        'logged_set_ids': logged_set_ids
    })
