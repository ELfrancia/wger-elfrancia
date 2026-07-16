# -*- coding: utf-8 -*-
import datetime
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.translation import gettext as _
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
            reps_label = _('reps')
            kg_label = _('kg')
            return HttpResponse(f'''
            <form class="flex items-center gap-2">
                <div class="flex items-center gap-1 bg-[#131313] border border-[#262626] rounded-full px-3 py-1 transition-colors">
                    <input type="number" disabled value="{repetitions}" class="w-10 bg-transparent border-0 p-0 text-center font-bold text-gray-400 focus:ring-0 text-sm">
                    <span class="text-[10px] text-gray-500 uppercase font-bold tracking-wider">{reps_label}</span>
                </div>
                
                <span class="text-xs text-gray-500">@</span>
                
                <div class="flex items-center gap-1 bg-[#131313] border border-[#262626] rounded-full px-3 py-1 transition-colors">
                    <input type="number" disabled value="{weight}" class="w-12 bg-transparent border-0 p-0 text-center font-bold text-gray-400 focus:ring-0 text-sm">
                    <span class="text-[10px] text-gray-500 uppercase font-bold tracking-wider">{kg_label}</span>
                </div>
                
                <button type="button" disabled class="w-8 h-8 rounded-full bg-[#caf300] text-[#131313] flex items-center justify-center font-bold shadow-sm cursor-default">
                    <span class="material-symbols-outlined text-sm font-black">check</span>
                </button>
            </form>
            ''')
        
        return redirect('manager:day:overview', routine_pk=routine_pk, day_pk=day_pk)

    # Calculate initial progress percentage
    total_sets = sum(slot.entries.count() for slot in day.slots.all())
    logged_set_ids = list(session.logs.values_list('slot_entry_id', flat=True))
    completed_sets = len(logged_set_ids)
    progress_percentage = int((completed_sets / total_sets) * 100) if total_sets > 0 else 0

    return render(request, 'workout/log_tailwind.html', {
        'day': day,
        'session': session,
        'logged_set_ids': logged_set_ids,
        'progress_percentage': progress_percentage
    })

