# Activity Calendar Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate a premium horizontal Activity Calendar (matching the screenshot) at the top of the Statistics/Progress page, allowing the user to browse daily workout summaries with instant HTMX loading.

**Architecture:**
1. Update `weight_overview_tailwind` in `wger/weight/views.py` to parse `selected_date`, calculate the 7 days of the active week, determine which days have completed workouts, fetch the workout logs and sessions for the selected day, and group logs by exercise.
2. If the request is an HTMX request, return only the calendar and workout summary HTML fragment (`weight/calendar_fragment.html`). Otherwise, render the full page containing the fragment.
3. Create the fragment template `wger/weight/templates/weight/calendar_fragment.html` implementing the horizontal scrollbar UI, navigation buttons, selected active days, and workout session summary.
4. Mount the calendar fragment at the top of `wger/weight/templates/overview_tailwind.html`.

**Tech Stack:** Django, Python, HTML, Tailwind CSS, HTMX.

---

### Task 1: Create Calendar Fragment Template
**Files:**
- Create: `wger/weight/templates/weight/calendar_fragment.html`

- [ ] **Step 1: Write HTML markup for calendar fragment**
  Add the weekly navigation calendar structure, selecting days, and session logs grouping logic.
  
  ```html
  {% load i18n %}
  
  <div id="activity-calendar-container" class="flex flex-col gap-4 w-full">
      <!-- Activity Calendar Card -->
      <div class="bg-[#161616]/70 backdrop-blur-lg border border-white/[0.06] rounded-[2rem] p-5 shadow-md">
          <h3 class="text-white font-bold text-base tracking-tight text-center mb-4">{% translate "Calendario Attività" %}</h3>
          
          <!-- Days Grid -->
          <div class="grid grid-cols-7 gap-1.5 w-full">
              {% for day in week_days %}
                  <button hx-get="{% url 'weight:overview' %}?selected_date={{ day.date|date:'Y-m-d' }}" 
                          hx-target="#activity-calendar-container" 
                          hx-swap="outerHTML"
                          class="flex flex-col items-center justify-center py-2.5 px-1 rounded-xl transition-all duration-300 {% if day.is_selected %}bg-[#caf300] text-[#131313] font-black shadow-[0_0_12px_rgba(202,243,0,0.3)]{% else %}bg-[#1c1c1e] hover:bg-[#252528] text-neutral-400 hover:text-white border border-white/[0.02]{% endif %}">
                      <span class="text-[9px] font-bold uppercase tracking-wider mb-0.5">{{ day.day_name }}</span>
                      <span class="text-xs font-black">{{ day.day_num }}</span>
                      {% if day.has_workout and not day.is_selected %}
                          <div class="w-1.5 h-1.5 bg-[#caf300] rounded-full mt-0.5"></div>
                      {% endif %}
                  </button>
              {% endfor %}
          </div>
  
          <!-- Month Navigation Row -->
          <div class="flex items-center justify-between mt-4 px-2 text-xs font-bold text-neutral-400">
              <button hx-get="{% url 'weight:overview' %}?selected_date={{ prev_week_date|date:'Y-m-d' }}" 
                      hx-target="#activity-calendar-container" 
                      hx-swap="outerHTML"
                      class="hover:text-white flex items-center justify-center p-1 transition-colors">
                  <span class="material-symbols-outlined text-[16px]">arrow_back_ios</span>
              </button>
              <span class="text-white uppercase tracking-wider font-extrabold text-[10px]">{{ current_month_name }}</span>
              <button hx-get="{% url 'weight:overview' %}?selected_date={{ next_week_date|date:'Y-m-d' }}" 
                      hx-target="#activity-calendar-container" 
                      hx-swap="outerHTML"
                      class="hover:text-white flex items-center justify-center p-1 transition-colors">
                  <span class="material-symbols-outlined text-[16px]">arrow_forward_ios</span>
              </button>
          </div>
      </div>
  
      <!-- Workout Summary Card -->
      <div class="bg-[#161616]/70 backdrop-blur-lg border border-white/[0.06] rounded-[2rem] p-5 shadow-md">
          <div class="flex items-center justify-between mb-4">
              <h3 class="text-white font-bold text-sm tracking-tight">{% translate "Resoconto Allenamenti" %}</h3>
              <span class="text-[10px] text-neutral-500 font-bold font-mono">{{ selected_date_display }}</span>
          </div>
  
          {% if selected_sessions %}
              <div class="space-y-4">
                  {% for session in selected_sessions %}
                      <div class="p-4 bg-[#1c1c1e]/60 border border-white/[0.03] rounded-2xl">
                          <div class="flex items-center justify-between border-b border-white/[0.05] pb-2.5 mb-3">
                              <div class="flex items-center gap-2.5">
                                  <div class="w-8 h-8 rounded-full bg-[#caf300]/10 border border-[#caf300]/20 flex items-center justify-center text-[#caf300]">
                                      <span class="material-symbols-outlined text-base">fitness_center</span>
                                  </div>
                                  <div>
                                      <h4 class="text-xs font-bold text-white leading-none">
                                          {% if session.routine %}
                                              {{ session.routine.name }}
                                          {% elif session.day %}
                                              {{ session.day.name }}
                                          {% else %}
                                              {% translate "Allenamento" %}
                                          {% endif %}
                                      </h4>
                                      {% if session.time_start %}
                                          <span class="text-[9px] text-neutral-500 mt-1 block">
                                              {{ session.time_start|time:"H:i" }} - {{ session.time_end|time:"H:i" }}
                                          </span>
                                      {% endif %}
                                  </div>
                              </div>
  
                              {% if session.impression %}
                                  <span class="px-2.5 py-0.5 rounded-full text-[9px] font-black uppercase tracking-wider
                                      {% if session.impression == '3' %}
                                          bg-emerald-950/40 border border-emerald-500/20 text-emerald-400
                                      {% elif session.impression == '2' %}
                                          bg-amber-950/40 border border-amber-500/20 text-amber-400
                                      {% else %}
                                          bg-red-950/40 border border-red-500/20 text-red-400
                                      {% endif %}">
                                      {% if session.impression == '3' %}
                                          {% translate "Good" %}
                                      {% elif session.impression == '2' %}
                                          {% translate "Neutral" %}
                                      {% else %}
                                          {% translate "Bad" %}
                                      {% endif %}
                                  </span>
                              {% endif %}
                          </div>
  
                          <!-- Exercises Logged in this Session -->
                          <div class="space-y-3">
                              {% for ex_data in session_exercises %}
                                  {% if ex_data.session_id == session.id %}
                                      <div>
                                          <h5 class="text-xs font-bold text-white mb-1.5 flex items-center gap-1.5">
                                              <span class="w-1.5 h-1.5 rounded-full bg-[#caf300]"></span>
                                              {{ ex_data.exercise_name }}
                                          </h5>
                                          <div class="flex flex-wrap gap-1.5 pl-3">
                                              {% for log in ex_data.logs %}
                                                  <span class="bg-[#131313]/60 border border-white/[0.03] rounded px-2 py-0.5 text-[10px] text-neutral-300 font-mono">
                                                      Set {{ forloop.counter }}: {{ log.repetitions|floatformat:0 }} reps &times; {{ log.weight|floatformat:1 }} kg
                                                  </span>
                                              {% endfor %}
                                          </div>
                                      </div>
                                  {% endif %}
                              {% endfor %}
                          </div>
  
                          {% if session.notes %}
                              <div class="mt-3.5 pt-2.5 border-t border-white/[0.05] flex gap-2 items-start text-[10px] text-neutral-400 italic">
                                  <span class="material-symbols-outlined text-[12px] mt-0.5">notes</span>
                                  <p class="flex-1">{{ session.notes }}</p>
                              </div>
                          {% endif %}
                      </div>
                  {% endfor %}
              </div>
          {% else %}
              <!-- Empty Placeholder -->
              <div class="flex flex-col items-center justify-center py-8 text-center gap-3 border border-dashed border-white/[0.06] rounded-2xl bg-transparent">
                  <div class="w-10 h-10 rounded-full bg-neutral-900 border border-white/[0.04] flex items-center justify-center text-neutral-600">
                      <span class="material-symbols-outlined text-lg">calendar_today</span>
                  </div>
                  <div>
                      <h4 class="text-xs font-bold text-white">{% translate "Nessun allenamento registrato" %}</h4>
                      <p class="text-[10px] text-neutral-500 mt-1 max-w-[200px]">{% translate "Nessun workout registrato per questa data." %}</p>
                  </div>
              </div>
          {% endif %}
      </div>
  </div>
  ```

- [ ] **Step 2: Commit template creation**
  ```bash
  git add wger/weight/templates/weight/calendar_fragment.html
  git commit -m "feat: create calendar_fragment.html template for activity calendar"
  ```

---

### Task 2: Refactor weight_overview_tailwind View
**Files:**
- Modify: `wger/weight/views.py:100-299`

- [ ] **Step 1: Update python logic to handle dates and sessions**
  Update the view function to query session details, calendar week days, and return the fragment when request header has `HX-Request`.
  
  ```python
  @login_required
  def weight_overview_tailwind(request):
      """
      Overview page for workout progress, weights, and top exercises, styled in Tailwind
      """
      range_param = request.GET.get('range', 'monthly')
      
      now = timezone.now()
      if range_param == 'weekly':
          start_date = now - timedelta(days=7)
      elif range_param == 'yearly':
          start_date = now - timedelta(days=365)
      else:
          range_param = 'monthly'
          start_date = now - timedelta(days=30)
          
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
  
      # --- ACTIVITY CALENDAR LOGIC ---
      selected_date_str = request.GET.get('selected_date')
      if selected_date_str:
          try:
              selected_date = datetime.datetime.strptime(selected_date_str, '%Y-%m-%d').date()
          except ValueError:
              selected_date = now.date()
      else:
          selected_date = now.date()
  
      start_of_week = selected_date - timedelta(days=selected_date.weekday())
      week_days = []
      day_initials_it = ['L', 'M', 'M', 'G', 'V', 'S', 'D']
      for i in range(7):
          day_date = start_of_week + timedelta(days=i)
          has_workout = WorkoutSession.objects.filter(user=request.user, date=day_date).exists()
          week_days.append({
              'date': day_date,
              'day_num': day_date.day,
              'day_name': day_initials_it[day_date.weekday()],
              'is_selected': day_date == selected_date,
              'has_workout': has_workout,
          })
          
      prev_week_date = selected_date - timedelta(days=7)
      next_week_date = selected_date + timedelta(days=7)
      
      months_it = {
          1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
          5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
          9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
      }
      current_month_name = f"{months_it[selected_date.month]} {selected_date.year}"
      selected_date_display = f"{selected_date.day} {months_it[selected_date.month]} {selected_date.year}"
  
      selected_sessions = WorkoutSession.objects.filter(user=request.user, date=selected_date)
      selected_logs = WorkoutLog.objects.filter(user=request.user, date__date=selected_date)
      
      session_exercises = []
      for session in selected_sessions:
          session_logs = selected_logs.filter(session=session)
          exercise_ids = session_logs.values_list('exercise', flat=True).distinct()
          for ex_id in exercise_ids:
              try:
                  exercise = Exercise.objects.get(pk=ex_id)
                  trans = exercise.get_translation()
                  ex_name = trans.name if trans else f"Exercise {ex_id}"
              except Exercise.DoesNotExist:
                  ex_name = f"Exercise {ex_id}"
                  
              ex_logs = session_logs.filter(exercise_id=ex_id).order_by('date')
              session_exercises.append({
                  'session_id': session.id,
                  'exercise_name': ex_name,
                  'logs': ex_logs
              })
  
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
          
          # Calendar variables
          'week_days': week_days,
          'prev_week_date': prev_week_date,
          'next_week_date': next_week_date,
          'current_month_name': current_month_name,
          'selected_date_display': selected_date_display,
          'selected_sessions': selected_sessions,
          'session_exercises': session_exercises,
      }
      
      if request.headers.get('HX-Request'):
          return render(request, 'weight/calendar_fragment.html', context)
          
      return render(request, 'overview_tailwind.html', context)
  ```

- [ ] **Step 2: Commit views refactor**
  ```bash
  git commit -m "feat: handle selected date and HTMX fragment in weight overview view"
  ```

---

### Task 3: Embed Calendar Fragment in overview_tailwind Template
**Files:**
- Modify: `wger/weight/templates/overview_tailwind.html:50-53`

- [ ] **Step 1: Include calendar fragment in target template**
  Mount the fragment inside `view-section-dati` right above the stats cards grid.
  
  ```html
      <!-- Dati View (Numeric View) -->
      <div id="view-section-dati" class="space-y-6 transition-all duration-300">
          
          <!-- Activity Calendar and Workout Summary -->
          {% include 'weight/calendar_fragment.html' %}
  ```

- [ ] **Step 2: Commit layout incorporation**
  ```bash
  git commit -m "feat: embed activity calendar fragment in overview_tailwind page"
  ```

---

### Task 4: Verify Integration
**Files:**
- Test: Manual browser checks.

- [ ] **Step 1: Check server status**
  Run: `docker compose ps`
  Expected: Web app is running.

- [ ] **Step 2: Retrieve page via curl to verify compile/load**
  Run: `Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000/weight/overview`
  Expected: StatusCode is 200, HTML contains the "activity-calendar-container" element.
```
