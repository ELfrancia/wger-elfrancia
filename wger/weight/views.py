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
import csv
import json
import logging
from datetime import timedelta

# Django
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Max, Count, Avg
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

# Third Party
from formtools.preview import FormPreview

# wger
from wger.exercises.models import Exercise
from wger.manager.models import WorkoutSession, WorkoutLog
from wger.weight import helpers
from wger.weight.models import WeightEntry


logger = logging.getLogger(__name__)


@login_required
def export_csv(request):
    """
    Exports the saved weight data as a CSV file
    """

    # Prepare the response headers
    response = HttpResponse(content_type='text/csv')

    # Convert all weight data to CSV
    writer = csv.writer(response)

    weights = WeightEntry.objects.filter(user=request.user)
    writer.writerow([_('Date'), _('Weight')])

    for entry in weights:
        writer.writerow([entry.date, entry.weight])

    # Send the data to the browser
    response['Content-Disposition'] = 'attachment; filename=Weightdata.csv'
    response['Content-Length'] = len(response.content)
    return response


class WeightCsvImportFormPreview(FormPreview):
    preview_template = 'import_csv_preview.html'
    form_template = 'import_csv_form.html'

    def get_context(self, request, form):
        """
        Context for template rendering.
        """

        return {
            'form': form,
            'stage_field': self.unused_name('stage'),
            'state': self.state,
        }

    def process_preview(self, request, form, context):
        context['weight_list'], context['error_list'] = helpers.parse_weight_csv(
            request, form.cleaned_data
        )
        return context

    def done(self, request, cleaned_data):
        weight_list, error_list = helpers.parse_weight_csv(request, cleaned_data)
        WeightEntry.objects.bulk_create(weight_list)
        return HttpResponseRedirect(reverse('weight:overview'))


@login_required
def weight_overview_tailwind(request):
    """
    Overview page for workout progress, weights, and top exercises, styled in Tailwind
    """
    from datetime import date, datetime
    from django.utils.formats import date_format

    range_param = request.GET.get('range', 'monthly')
    
    now = timezone.now()
    if range_param == 'weekly':
        start_date = now - timedelta(days=7)
    elif range_param == 'yearly':
        start_date = now - timedelta(days=365)
    else:
        range_param = 'monthly'
        start_date = now - timedelta(days=30)
        
    # Extract selected_date from GET request, defaulting to today.
    selected_date_str = request.GET.get('selected_date')
    if selected_date_str:
        try:
            selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = now.date()
    else:
        selected_date = now.date()

    # Calculate Monday of the active week.
    monday_of_week = selected_date - timedelta(days=selected_date.weekday())

    # Gather week_days metadata
    week_start = monday_of_week
    week_end = monday_of_week + timedelta(days=6)
    week_sessions_dates = set(
        WorkoutSession.objects.filter(
            user=request.user,
            date__range=[week_start, week_end]
        ).values_list('date', flat=True)
    )

    week_days = []
    for i in range(7):
        day_date = monday_of_week + timedelta(days=i)
        week_days.append({
            'date': day_date,
            'day_num': day_date.day,
            'day_name': date_format(day_date, 'D'),
            'is_selected': day_date == selected_date,
            'has_workout': day_date in week_sessions_dates,
        })

    # Get prev_week_date and next_week_date dates.
    prev_week_date = selected_date - timedelta(days=7)
    next_week_date = selected_date + timedelta(days=7)

    # Get current_month_name and selected_date_display.
    current_month_name = date_format(selected_date, 'F Y')
    selected_date_display = date_format(selected_date, 'd F Y')

    # Retrieve all completed WorkoutSessions and WorkoutLogs for that selected date
    selected_sessions = WorkoutSession.objects.filter(user=request.user, date=selected_date)
    logs_for_date = WorkoutLog.objects.filter(user=request.user, session__in=selected_sessions).select_related('exercise')

    # Group logs by exercise name under session_exercises
    grouped = {}
    for log in logs_for_date:
        key = (log.session_id, log.exercise_id)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(log)

    session_exercises = []
    for (session_id, exercise_id), logs in grouped.items():
        first_log = logs[0]
        exercise = first_log.exercise
        translation = exercise.get_translation() if exercise else None
        exercise_name = translation.name if translation else (exercise.name if exercise else f"Exercise {exercise_id}")
        
        session_exercises.append({
            'session_id': session_id,
            'exercise_name': exercise_name,
            'logs': logs
        })

    # Query WorkoutSession
    sessions = WorkoutSession.objects.filter(user=request.user, date__gte=start_date.date())
    workouts_completed = sessions.count()
    
    # Query WorkoutLog
    logs = WorkoutLog.objects.filter(user=request.user, date__gte=start_date)
    
    # Total repetitions: logs.aggregate(total=Sum('repetitions'))['total'] or 0
    total_repetitions = logs.aggregate(total=Sum('repetitions'))['total'] or 0
    if isinstance(total_repetitions, float) or hasattr(total_repetitions, 'quantize'):
        total_repetitions = float(total_repetitions)
        if total_repetitions.is_integer():
            total_repetitions = int(total_repetitions)
            
    # Total volume: Sum of repetitions * weight
    total_volume = logs.annotate(vol=F('repetitions') * F('weight')).aggregate(total=Sum('vol'))['total'] or 0
    if isinstance(total_volume, float) or hasattr(total_volume, 'quantize'):
        total_volume = float(total_volume)
        if total_volume.is_integer():
            total_volume = int(total_volume)
            
    # Query WeightEntry
    weight_entries = WeightEntry.objects.filter(user=request.user, date__gte=start_date).order_by('date')
    
    starting_weight = None
    ending_weight = None
    weight_change = 0.0
    avg_weight = 0.0
    
    if weight_entries.exists():
        first_entry = weight_entries.first()
        last_entry = weight_entries.last()
        starting_weight = first_entry.weight
        ending_weight = last_entry.weight
        if starting_weight is not None and ending_weight is not None:
            weight_change = ending_weight - starting_weight
        avg_weight = weight_entries.aggregate(avg=Avg('weight'))['avg'] or 0.0
        
        # Format weights to clean representations
        if starting_weight is not None:
            starting_weight = float(starting_weight)
        if ending_weight is not None:
            ending_weight = float(ending_weight)
        weight_change = float(weight_change)
        avg_weight = float(avg_weight)

    # Query Exercise stats for the period
    exercise_stats_query = (
        logs
        .values('exercise')
        .annotate(
            sets_completed=Count('id'),
            total_repetitions=Sum('repetitions'),
            total_volume=Sum(F('repetitions') * F('weight')),
            max_weight=Max('weight')
        )
        .order_by('-total_volume')
    )
    
    exercise_stats = []
    for stat in exercise_stats_query:
        exercise_id = stat['exercise']
        if not exercise_id:
            continue
        try:
            exercise = Exercise.objects.get(pk=exercise_id)
            translation = exercise.get_translation()
            name = translation.name if translation else f"Exercise {exercise_id}"
        except Exercise.DoesNotExist:
            name = f"Exercise {exercise_id}"
            
        t_vol = stat['total_volume'] or 0
        if isinstance(t_vol, float) or hasattr(t_vol, 'quantize'):
            t_vol = float(t_vol)
            if t_vol.is_integer():
                t_vol = int(t_vol)
                
        t_reps = stat['total_repetitions'] or 0
        if isinstance(t_reps, float) or hasattr(t_reps, 'quantize'):
            t_reps = float(t_reps)
            if t_reps.is_integer():
                t_reps = int(t_reps)
                
        m_weight = stat['max_weight'] or 0
        if isinstance(m_weight, float) or hasattr(m_weight, 'quantize'):
            m_weight = float(m_weight)
            if m_weight.is_integer():
                m_weight = int(m_weight)
                
        sets_comp = stat['sets_completed'] or 0
        
        exercise_stats.append({
            'name': name,
            'sets_completed': sets_comp,
            'total_repetitions': t_reps,
            'total_volume': t_vol,
            'max_weight': m_weight,
        })
        
    exercise_stats = sorted(exercise_stats, key=lambda x: x['total_volume'], reverse=True)[:10]
    
    # Calculate volume percentage for progress bars
    max_volume_stat = max([x['total_volume'] for x in exercise_stats]) if exercise_stats else 0
    for stat in exercise_stats:
        if max_volume_stat > 0:
            stat['volume_percentage'] = int((stat['total_volume'] / max_volume_stat) * 100)
        else:
            stat['volume_percentage'] = 0

    # Fetch weight trend data
    weight_data = [
        {
            'date': entry.date.strftime('%Y-%m-%d'),
            'weight': float(entry.weight)
        }
        for entry in weight_entries
    ]

    # Calculate daily training volume and session count
    from django.db.models.functions import TruncDate
    
    daily_volume_query = (
        logs
        .annotate(log_date=TruncDate('date'))
        .values('log_date')
        .annotate(volume=Sum(F('repetitions') * F('weight')))
        .order_by('log_date')
    )
    
    daily_sessions_query = (
        sessions
        .values('date')
        .annotate(count=Count('id'))
        .order_by('date')
    )
    
    # Generate all dates in the range to fill in missing days
    curr = start_date.date()
    end = now.date()
    num_days = (end - curr).days
    date_list = [curr + timedelta(days=i) for i in range(num_days + 1)]
    
    volume_by_date = {}
    for entry in daily_volume_query:
        if entry['log_date']:
            d_val = entry['log_date']
            d_str = d_val.strftime('%Y-%m-%d') if hasattr(d_val, 'strftime') else str(d_val)
            volume_by_date[d_str] = float(entry['volume'] or 0.0)
            
    sessions_by_date = {}
    for entry in daily_sessions_query:
        if entry['date']:
            d_val = entry['date']
            d_str = d_val.strftime('%Y-%m-%d') if hasattr(d_val, 'strftime') else str(d_val)
            sessions_by_date[d_str] = entry['count']
            
    activity_data = []
    for d in date_list:
        d_str = d.strftime('%Y-%m-%d')
        activity_data.append({
            'date': d_str,
            'volume': volume_by_date.get(d_str, 0.0),
            'sessions': sessions_by_date.get(d_str, 0)
        })

    # Serialize to JSON strings
    weight_data_json = json.dumps(weight_data)
    activity_data_json = json.dumps(activity_data)

    context = {
        'range': range_param,
        'workouts_completed': workouts_completed,
        'total_repetitions': total_repetitions,
        'total_volume': total_volume,
        'starting_weight': starting_weight,
        'ending_weight': ending_weight,
        'weight_change': weight_change,
        'avg_weight': avg_weight,
        'exercise_stats': exercise_stats,
        'weight_data_json': weight_data_json,
        'activity_data_json': activity_data_json,
        
        # New Activity Calendar context
        'selected_date': selected_date,
        'selected_date_display': selected_date_display,
        'current_month_name': current_month_name,
        'week_days': week_days,
        'prev_week_date': prev_week_date,
        'next_week_date': next_week_date,
        'selected_sessions': selected_sessions,
        'session_exercises': session_exercises,
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'weight/calendar_fragment.html', context)
    return render(request, 'overview_tailwind.html', context)
