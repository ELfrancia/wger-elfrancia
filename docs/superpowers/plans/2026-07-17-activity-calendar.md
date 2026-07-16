# Calendario Attività nelle Statistiche Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrare un calendario settimanale scorrevole e una scheda di resoconto giornaliera con grafico orario nella pagina delle statistiche (Scheda di Progressi) usando HTMX per un'interazione dinamica.

**Architecture:** Creazione di una rotta dedicata `/weight/activity-details/` che gestisce richieste GET (visualizzazione dati e calendario per una data selezionata) e POST (logging dei dati di passi, calorie, acqua per la data selezionata). Il frontend include questo frammento HTML tramite HTMX e si aggiorna asincronamente.

**Tech Stack:** Django (Python), HTMX (AJAX), Tailwind CSS, Chart.js, SQLite.

---

### Task 1: Aggiungere URL e definire la View in wger/weight/urls.py

**Files:**
- Modify: `wger/weight/urls.py`

- [ ] **Step 1: Modificare il file urls.py per registrare la rotta**

```python
# Modificare wger/weight/urls.py per aggiungere il path per activity-details
# Aggiungere alle importazioni in alto se necessario: views
# Aggiungere all'array urlpatterns:
path(
    'activity-details/',
    views.weight_activity_details,
    name='activity-details',
),
```

- [ ] **Step 2: Commit delle modifiche agli URL**

```bash
git add wger/weight/urls.py
git commit -m "feat(weight): register activity-details url pattern"
```

---

### Task 2: Scrivere il test per la view dei dettagli dell'attività

**Files:**
- Create: `wger/weight/tests/test_activity_details.py`

- [ ] **Step 1: Creare il file di test test_activity_details.py**

```python
# -*- coding: utf-8 -*-
from django.urls import reverse
from django.utils import timezone
from wger.core.tests.base_testcase import WgerTestCase
from wger.core.models import DailyActivity

class ActivityDetailsTestCase(WgerTestCase):
    """
    Test case per l'endpoint dei dettagli dell'attività giornaliera
    """

    def setUp(self):
        super().setUp()
        self.user_login('test')

    def test_get_activity_details_default(self):
        """Testa la GET senza parametri (data odierna)"""
        response = self.client.get(reverse('weight:activity-details'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activity Calendar')

    def test_get_activity_details_specific_date(self):
        """Testa la GET con una data specifica"""
        selected_date = '2026-07-16'
        response = self.client.get(reverse('weight:activity-details'), {'date': selected_date})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, selected_date)

    def test_post_log_activity_steps(self):
        """Testa la POST per loggare i passi su una data specifica"""
        selected_date = '2026-07-16'
        # Log iniziale
        response = self.client.post(
            reverse('weight:activity-details'),
            {
                'date': selected_date,
                'activity_type': 'steps',
                'amount': '1000'
            }
        )
        self.assertEqual(response.status_code, 200)
        activity = DailyActivity.objects.get(user=self.user, date=selected_date)
        self.assertEqual(activity.steps, 1000)
```

- [ ] **Step 2: Eseguire il test per verificare che fallisca**

Run: `uv run python manage.py test wger.weight.tests.test_activity_details`
Expected: FAIL (AttributeError o ImportError perché views.weight_activity_details non è definita)

---

### Task 3: Implementare la view weight_activity_details in wger/weight/views.py

**Files:**
- Modify: `wger/weight/views.py`

- [ ] **Step 1: Implementare la view in views.py**

Aggiungere in fondo a `wger/weight/views.py`:

```python
from django.views.decorators.http import require_http_methods
import datetime

@login_required
@require_http_methods(["GET", "POST"])
def weight_activity_details(request):
    """
    View che gestisce la visualizzazione del calendario e il logging delle attività giornaliere
    """
    from wger.core.models import DailyActivity
    from wger.manager.models import WorkoutLog
    from django.utils import timezone
    from decimal import Decimal
    import decimal

    # 1. Parsing della data selezionata
    date_str = request.GET.get('date') or request.POST.get('date')
    if date_str:
        try:
            selected_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    # 2. Gestione POST per il logging delle attività per la data selezionata
    activity, _ = DailyActivity.objects.get_or_create(user=request.user, date=selected_date)
    
    if request.method == 'POST':
        activity_type = request.POST.get('activity_type')
        amount = request.POST.get('amount')
        value = request.POST.get('value')

        if activity_type == 'steps':
            try:
                if value is not None and value != '':
                    activity.steps = max(0, int(value))
                elif amount is not None and amount != '':
                    activity.steps = max(0, activity.steps + int(amount))
                activity.save()
            except (ValueError, TypeError):
                pass
        elif activity_type == 'calories':
            try:
                if value is not None and value != '':
                    activity.calories = max(0, int(value))
                elif amount is not None and amount != '':
                    activity.calories = max(0, activity.calories + int(amount))
                activity.save()
            except (ValueError, TypeError):
                pass
        elif activity_type == 'water':
            try:
                if value is not None and value != '':
                    val_str = str(value).replace(',', '.')
                    activity.water = max(Decimal('0.0'), Decimal(val_str))
                elif amount is not None and amount != '':
                    amt_str = str(amount).replace(',', '.')
                    activity.water = max(Decimal('0.0'), activity.water + Decimal(amt_str))
                activity.save()
            except (ValueError, TypeError, decimal.InvalidOperation):
                pass

    # 3. Calcolo dei giorni della settimana (da Lunedì a Domenica)
    # Lunedì è index 0, Domenica è index 6
    weekday_offset = selected_date.weekday()
    monday_of_week = selected_date - datetime.timedelta(days=weekday_offset)
    
    week_days = []
    # Nomi dei giorni in italiano
    day_names = [_('M'), _('T'), _('W'), _('T'), _('F'), _('S'), _('S')]
    
    for i in range(7):
        day_date = monday_of_week + datetime.timedelta(days=i)
        week_days.append({
            'name': day_names[i],
            'number': day_date.day,
            'date_str': day_date.strftime('%Y-%m-%d'),
            'is_selected': day_date == selected_date,
        })

    # Date per navigare alla settimana precedente e successiva
    prev_week_str = (selected_date - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
    next_week_str = (selected_date + datetime.timedelta(days=7)).strftime('%Y-%m-%d')

    # 4. Calcolo metriche di resoconto
    distance_active = float(activity.steps) * 0.00075 # km
    profile = request.user.userprofile

    # Traduzione del nome del mese in italiano per visualizzazione
    months_it = {
        1: 'Gennaio', 2: 'Febbraio', 3: 'Marzo', 4: 'Aprile',
        5: 'Maggio', 6: 'Giugno', 7: 'Luglio', 8: 'Agosto',
        9: 'Settembre', 10: 'Ottobre', 11: 'Novembre', 12: 'Dicembre'
    }
    month_name = months_it.get(selected_date.month, selected_date.strftime('%B'))
    month_year_str = f"{month_name} {selected_date.year}"

    # 5. Distribuzione oraria degli allenamenti (WorkoutLog) per la data selezionata
    # Ottieni i log dell'utente in quella data
    start_of_day = timezone.make_aware(datetime.datetime.combine(selected_date, datetime.time.min))
    end_of_day = timezone.make_aware(datetime.datetime.combine(selected_date, datetime.time.max))
    logs = WorkoutLog.objects.filter(user=request.user, date__range=(start_of_day, end_of_day))
    
    hourly_distribution = [0] * 24
    for log in logs:
        local_log_date = timezone.localtime(log.date)
        hour = local_log_date.hour
        hourly_distribution[hour] += 1

    context = {
        'selected_date_str': selected_date.strftime('%Y-%m-%d'),
        'week_days': week_days,
        'prev_week_str': prev_week_str,
        'next_week_str': next_week_str,
        'month_year_str': month_year_str,
        'activity': activity,
        'profile': profile,
        'distance_active': distance_active,
        'hourly_distribution_json': json.dumps(hourly_distribution),
    }

    return render(request, 'activity_details_fragment.html', context)
```

- [ ] **Step 2: Eseguire il test per verificare che passi**

Run: `uv run python manage.py test wger.weight.tests.test_activity_details`
Expected: PASS (ma fallirà a causa del template mancante)

---

### Task 4: Creare il template activity_details_fragment.html

**Files:**
- Create: `wger/weight/templates/activity_details_fragment.html`

- [ ] **Step 1: Scrivere il contenuto del template activity_details_fragment.html**

```html
{% load i18n %}

<div id="activity-details-container" class="flex flex-col gap-5 w-full">
    <!-- 1. Activity Calendar Section -->
    <div class="bg-[#161618]/90 border border-white/[0.05] rounded-[28px] p-5 flex flex-col gap-4 shadow-xl">
        <h3 class="text-white font-bold text-center text-sm tracking-wide">{% translate "Activity Calendar" %}</h3>
        
        <!-- Days of the week row -->
        <div class="grid grid-cols-7 gap-2 text-center">
            {% for day in week_days %}
                <button hx-get="{% url 'weight:activity-details' %}?date={{ day.date_str }}"
                        hx-target="#activity-details-container"
                        hx-swap="outerHTML"
                        class="flex flex-col items-center py-2.5 rounded-2xl transition-all duration-200 {% if day.is_selected %}bg-[#caf300] text-[#121214] font-bold shadow-md scale-105{% else %}bg-neutral-800/40 text-neutral-400 hover:bg-neutral-800 hover:text-white{% endif %}">
                    <span class="text-[10px] uppercase font-bold tracking-wider mb-1">{{ day.name }}</span>
                    <span class="text-sm font-extrabold">{{ day.number }}</span>
                </button>
            {% endfor %}
        </div>

        <!-- Month Navigation -->
        <div class="flex items-center justify-between text-neutral-400 text-xs px-2 mt-1">
            <button hx-get="{% url 'weight:activity-details' %}?date={{ prev_week_str }}"
                    hx-target="#activity-details-container"
                    hx-swap="outerHTML"
                    class="p-1 hover:text-white transition-colors">
                <span class="material-symbols-outlined text-sm">chevron_left</span>
            </button>
            <span class="font-bold uppercase tracking-wider text-[11px] text-white/90">{{ month_year_str }}</span>
            <button hx-get="{% url 'weight:activity-details' %}?date={{ next_week_str }}"
                    hx-target="#activity-details-container"
                    hx-swap="outerHTML"
                    class="p-1 hover:text-white transition-colors">
                <span class="material-symbols-outlined text-sm">chevron_right</span>
            </button>
        </div>
    </div>

    <!-- 2. Concentric Progress Rings and Logs Card -->
    <div class="bg-[#161618]/90 border border-white/[0.05] rounded-[28px] p-6 flex flex-col gap-6 shadow-xl relative overflow-hidden">
        <div class="flex items-center justify-between">
            <h3 class="text-white font-bold text-base tracking-tight">{% translate "Resoconto Giornaliero" %}</h3>
            <span class="text-xs text-neutral-500 font-bold">{{ selected_date_str }}</span>
        </div>

        <div class="flex flex-col md:flex-row items-center justify-between gap-6">
            <!-- Left side inputs list -->
            <div class="flex flex-col gap-4 w-full md:w-1/2">
                <!-- Steps -->
                <div class="flex flex-col border-b border-white/[0.05] pb-3">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-[#caf300]" style="font-variation-settings: 'FILL' 1;">directions_walk</span>
                            <span class="text-xs font-bold text-neutral-400 uppercase tracking-widest">{% translate "Passi" %}</span>
                        </div>
                        <div class="text-right">
                            <span class="text-base font-black text-[#caf300]">{{ activity.steps|default:"0" }}</span>
                            <span class="text-xs text-neutral-500">/ {{ profile.steps_goal|default:"16000" }}</span>
                        </div>
                    </div>
                    <div class="flex items-center justify-between mt-2 gap-2">
                        <div class="flex gap-1">
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "steps", "amount": 1000, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +1k
                            </button>
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "steps", "amount": 5000, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +5k
                            </button>
                        </div>
                        <form hx-post="{% url 'weight:activity-details' %}" hx-target="#activity-details-container" hx-swap="outerHTML" class="flex items-center gap-1">
                            <input type="hidden" name="date" value="{{ selected_date_str }}">
                            <input type="hidden" name="activity_type" value="steps">
                            <input type="number" name="amount" placeholder="+Passi" class="w-16 bg-[#131313] border border-white/[0.08] text-white text-[10px] rounded-full px-2 py-0.5 focus:outline-none focus:border-[#caf300] placeholder-neutral-700 text-center">
                            <button type="submit" class="bg-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full transition-all duration-200">{% translate "Aggiungi" %}</button>
                        </form>
                    </div>
                </div>

                <!-- Calories -->
                <div class="flex flex-col border-b border-white/[0.05] pb-3">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-[#caf300]/85" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
                            <span class="text-xs font-bold text-neutral-400 uppercase tracking-widest">{% translate "Calorie" %}</span>
                        </div>
                        <div class="text-right">
                            <span class="text-base font-black text-[#caf300]/85">{{ activity.calories|default:"0" }}</span>
                            <span class="text-xs text-neutral-500">/ {{ profile.calories_goal|default:"680" }} Cal</span>
                        </div>
                    </div>
                    <div class="flex items-center justify-between mt-2 gap-2">
                        <div class="flex gap-1">
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "calories", "amount": 100, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +100
                            </button>
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "calories", "amount": 250, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +250
                            </button>
                        </div>
                        <form hx-post="{% url 'weight:activity-details' %}" hx-target="#activity-details-container" hx-swap="outerHTML" class="flex items-center gap-1">
                            <input type="hidden" name="date" value="{{ selected_date_str }}">
                            <input type="hidden" name="activity_type" value="calories">
                            <input type="number" name="amount" placeholder="+Cal" class="w-16 bg-[#131313] border border-white/[0.08] text-white text-[10px] rounded-full px-2 py-0.5 focus:outline-none focus:border-[#caf300] placeholder-neutral-700 text-center">
                            <button type="submit" class="bg-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full transition-all duration-200">{% translate "Aggiungi" %}</button>
                        </form>
                    </div>
                </div>

                <!-- Water -->
                <div class="flex flex-col pb-1">
                    <div class="flex items-center justify-between">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-[#caf300]/70" style="font-variation-settings: 'FILL' 1;">local_drink</span>
                            <span class="text-xs font-bold text-neutral-400 uppercase tracking-widest">{% translate "Acqua" %}</span>
                        </div>
                        <div class="text-right">
                            <span class="text-base font-black text-[#caf300]/70">{{ activity.water|default:"0.0" }}</span>
                            <span class="text-xs text-neutral-500">/ {{ profile.water_goal|default:"2.5" }} L</span>
                        </div>
                    </div>
                    <div class="flex items-center justify-between mt-2 gap-2">
                        <div class="flex gap-1">
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "water", "amount": 0.25, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +0.25L
                            </button>
                            <button hx-post="{% url 'weight:activity-details' %}" hx-vals='{"activity_type": "water", "amount": 0.5, "date": "{{ selected_date_str }}"}' hx-target="#activity-details-container" hx-swap="outerHTML" class="bg-white/[0.03] border border-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-[#eaeaea] text-[10px] font-bold px-2 py-0.5 rounded-full transition-all duration-200">
                                +0.5L
                            </button>
                        </div>
                        <form hx-post="{% url 'weight:activity-details' %}" hx-target="#activity-details-container" hx-swap="outerHTML" class="flex items-center gap-1">
                            <input type="hidden" name="date" value="{{ selected_date_str }}">
                            <input type="hidden" name="activity_type" value="water">
                            <input type="number" step="0.05" name="amount" placeholder="+L" class="w-16 bg-[#131313] border border-white/[0.08] text-white text-[10px] rounded-full px-2 py-0.5 focus:outline-none focus:border-[#caf300] placeholder-neutral-700 text-center">
                            <button type="submit" class="bg-white/[0.05] hover:bg-[#caf300] hover:text-[#131313] text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full transition-all duration-200">{% translate "Aggiungi" %}</button>
                        </form>
                    </div>
                </div>
            </div>

            <!-- SVG Concentric rings -->
            <div class="relative w-44 h-44 flex items-center justify-center bg-black/10 border border-white/[0.02] rounded-full p-2">
                <svg class="w-full h-full transform -rotate-90" viewBox="0 0 110 110">
                    <circle cx="55" cy="55" r="45" stroke="#1f1f1f" stroke-width="8" fill="transparent" />
                    <circle cx="55" cy="55" r="34" stroke="#1f1f1f" stroke-width="8" fill="transparent" />
                    <circle cx="55" cy="55" r="23" stroke="#1f1f1f" stroke-width="8" fill="transparent" />
                    
                    <circle id="ring-detail-steps" cx="55" cy="55" r="45" stroke="#caf300" stroke-width="8" fill="transparent" 
                            stroke-dasharray="282.74" stroke-dashoffset="282.74" stroke-linecap="round" class="transition-all duration-1000 ease-out" />
                    <circle id="ring-detail-calories" cx="55" cy="55" r="34" stroke="#9fbd00" stroke-width="8" fill="transparent" 
                            stroke-dasharray="213.63" stroke-dashoffset="213.63" stroke-linecap="round" class="transition-all duration-1000 ease-out" />
                    <circle id="ring-detail-water" cx="55" cy="55" r="23" stroke="#748b00" stroke-width="8" fill="transparent" 
                            stroke-dasharray="144.51" stroke-dashoffset="144.51" stroke-linecap="round" class="transition-all duration-1000 ease-out" />
                </svg>
            </div>
        </div>

        <!-- 3. Details list (Distance and Calorie output) -->
        <div class="flex flex-col gap-2 mt-4 pt-4 border-t border-white/[0.05] text-xs font-bold text-neutral-400">
            <div class="flex justify-between items-center">
                <span>{% translate "Distance while active" %}</span>
                <span class="text-white text-sm font-extrabold">{{ distance_active|floatformat:2 }} km</span>
            </div>
            <div class="flex justify-between items-center mt-1">
                <span>{% translate "Total burnt calories" %}</span>
                <span class="text-white text-sm font-extrabold">{{ activity.calories|default:"0" }} Cal</span>
            </div>
        </div>

        <!-- 4. Hourly Activity Chart -->
        <div class="mt-4 pt-4 border-t border-white/[0.05] flex flex-col gap-4">
            <h4 class="text-white font-bold text-xs tracking-wide">{% translate "Attività Oraria (Allenamenti)" %}</h4>
            <div class="relative w-full h-[150px]">
                <canvas id="hourlyActivityChart"></canvas>
            </div>
        </div>
    </div>

    <!-- JS script to initialize rings and Chart.js -->
    <script>
        (function() {
            function parseValue(valStr) {
                if (!valStr) return 0;
                const clean = valStr.toString().replace(/\s/g, '').replace(',', '.');
                return parseFloat(clean) || 0;
            }

            const stepsVal = parseValue("{{ activity.steps|default:'0' }}");
            const stepsGoal = parseValue("{{ profile.steps_goal|default:'16000' }}") || 16000;
            const stepsPct = Math.min(stepsVal / stepsGoal, 1);
            const ringSteps = document.getElementById('ring-detail-steps');
            if (ringSteps) ringSteps.setAttribute('stroke-dashoffset', 282.74 - (stepsPct * 282.74));

            const calVal = parseValue("{{ activity.calories|default:'0' }}");
            const calGoal = parseValue("{{ profile.calories_goal|default:'680' }}") || 680;
            const calPct = Math.min(calVal / calGoal, 1);
            const ringCalories = document.getElementById('ring-detail-calories');
            if (ringCalories) ringCalories.setAttribute('stroke-dashoffset', 213.63 - (calPct * 213.63));

            const waterVal = parseValue("{{ activity.water|default:'0.0' }}");
            const waterGoal = parseValue("{{ profile.water_goal|default:'2.5' }}") || 2.5;
            const waterPct = Math.min(waterVal / waterGoal, 1);
            const ringWater = document.getElementById('ring-detail-water');
            if (ringWater) ringWater.setAttribute('stroke-dashoffset', 144.51 - (waterPct * 144.51));

            // Chart.js Hourly Graph
            const hourlyCanvas = document.getElementById('hourlyActivityChart');
            if (hourlyCanvas) {
                const hourlyData = JSON.parse('{{ hourly_distribution_json|escapejs }}');
                const ctx = hourlyCanvas.getContext('2d');
                
                // Genera le etichette per le 24 ore
                const labels = [];
                for(let i=0; i<24; i++) {
                    labels.push(i + 'h');
                }

                new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Serie completate',
                            data: hourlyData,
                            backgroundColor: '#caf300',
                            borderColor: 'transparent',
                            borderRadius: 2,
                            barPercentage: 0.75,
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                backgroundColor: '#161616',
                                titleColor: '#ffffff',
                                bodyColor: '#ffffff',
                                borderColor: '#2a2a2a',
                                borderWidth: 1,
                                padding: 8,
                                displayColors: false
                            }
                        },
                        scales: {
                            x: {
                                grid: { display: false },
                                ticks: {
                                    color: '#888888',
                                    font: { size: 8 },
                                    autoSkip: true,
                                    maxTicksLimit: 6
                                }
                            },
                            y: {
                                grid: { color: '#222222' },
                                ticks: {
                                    color: '#888888',
                                    font: { size: 8 },
                                    stepSize: 1,
                                    precision: 0
                                }
                            }
                        }
                    }
                });
            }
        })();
    </script>
</div>
```

- [ ] **Step 2: Eseguire il test per verificare che passi**

Run: `uv run python manage.py test wger.weight.tests.test_activity_details`
Expected: PASS

---

### Task 5: Integrare il frammento nella pagina principale delle statistiche

**Files:**
- Modify: `wger/weight/templates/overview_tailwind.html`

- [ ] **Step 1: Aggiungere il container del frammento in overview_tailwind.html**

Nel file `wger/weight/templates/overview_tailwind.html`, inserire all'inizio del blocco `content` (subito prima di `<div id="view-section-dati" ...>` o sotto il titolo/sottotitolo):

```html
<!-- Inserire intorno alla riga 50 prima del div "view-section-dati" -->
<!-- Activity Details / Calendar / Concentric Rings Fragment -->
<div class="mb-2">
    <div id="activity-details-container" 
         hx-get="{% url 'weight:activity-details' %}" 
         hx-trigger="load" 
         hx-swap="outerHTML">
    </div>
</div>
```

- [ ] **Step 2: Eseguire i test di regressione per l'intera suite weight**

Run: `uv run python manage.py test wger.weight.tests`
Expected: PASS
