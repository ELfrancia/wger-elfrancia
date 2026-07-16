# wger Tailwind + HTMX Monolithic UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the wger selfhosted Django application frontend into a lightweight, high-performance Tailwind + HTMX monolithic interface using the Onyx design assets, optimizing for Docker hosting on Proxmox.

**Architecture:** We will replace Django's React-based and Bootstrap-based views with native Django TemplateViews that render Tailwind layouts and use HTMX for dynamic asynchronous updates. We will bundle Tailwind via CDN for easy container deployment, or configure a lightweight static asset compilation script inside the Docker image.

**Tech Stack:** Django, Python, Tailwind CSS, HTMX, SQLite/PostgreSQL, Docker.

---

### Task 1: Create Tailwind Base Templates & Navigation

**Files:**
- Create: `wger/core/templates/template_tailwind.html`
- Create: `wger/core/templates/navigation_tailwind.html`

- [ ] **Step 1: Write base template with Tailwind & Google Material Symbols**
  Create [template_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/templates/template_tailwind.html) to define the shared HTML head, viewport parameters, and background/surface dark mode color tokens.
  ```html
  {% load static wger_extras %}
  <!DOCTYPE html>
  <html class="dark" lang="en">
  <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"/>
      <meta name="theme-color" content="#131313"/>
      <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=block" rel="stylesheet"/>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
      <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
      <script src="{% static 'node/htmx.org/dist/htmx.min.js' %}"></script>
      <script>
        tailwind.config = {
          darkMode: "class",
          theme: {
            extend: {
              colors: {
                "background": "#131313",
                "surface": "#131313",
                "surface-container": "#201f1f",
                "surface-container-low": "#1c1b1b",
                "surface-container-high": "#2a2a2a",
                "primary": "#ffffff",
                "primary-fixed": "#caf300",
                "on-surface-variant": "#c5c9ac",
                "error": "#ffb4ab"
              },
              borderRadius: {
                "DEFAULT": "1rem",
                "lg": "2rem",
                "xl": "3rem"
              }
            }
          }
        }
      </script>
      <title>{% block title %}Onyx Tracker{% endblock %}</title>
      {% block header %}{% endblock %}
  </head>
  <body class="bg-[#131313] text-[#e5e2e1] font-sans antialiased pb-24">
      {% include 'navigation_tailwind.html' %}
      <main class="max-w-3xl mx-auto px-4 mt-4">
          {% block content %}{% endblock %}
      </main>
      {% block extra_body %}{% endblock %}
  </body>
  </html>
  ```

- [ ] **Step 2: Create Tailwind-based navigation components**
  Create [navigation_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/templates/navigation_tailwind.html) implementing the top bar header (with the brand name and notifications icon) and the bottom tab bar navigation for mobile devices.
  ```html
  {% load static %}
  <!-- Top Header -->
  <header class="w-full sticky top-0 z-50 bg-[#131313]/95 backdrop-blur-sm flex justify-between items-center px-4 py-4">
      <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-full overflow-hidden border border-surface-container-high bg-surface-container">
              <span class="material-symbols-outlined text-primary-fixed text-2xl flex items-center justify-center h-full">person</span>
          </div>
          <h1 class="text-lg font-extrabold uppercase tracking-tight text-primary">ONYX ATHLETIC</h1>
      </div>
      <button class="min-w-[44px] min-h-[44px] flex items-center justify-center hover:opacity-80 transition-opacity">
          <span class="material-symbols-outlined text-primary text-2xl">notifications</span>
      </button>
  </header>

  <!-- Bottom Navigation Bar (Mobile) -->
  <nav class="fixed bottom-0 left-0 w-full z-50 bg-[#131313] border-t border-surface-container-high flex justify-around items-center h-20 pb-safe px-2">
      <a class="flex flex-col items-center justify-center text-primary-fixed min-w-[64px] min-h-[64px]" href="{% url 'core:dashboard' %}">
          <span class="material-symbols-outlined mb-1" style="font-variation-settings: 'FILL' 1;">home</span>
          <span class="text-[9px] uppercase tracking-widest font-bold">Home</span>
      </a>
      <a class="flex flex-col items-center justify-center text-on-surface-variant min-w-[64px] min-h-[64px]" href="{% url 'manager:routine:overview' %}">
          <span class="material-symbols-outlined mb-1">fitness_center</span>
          <span class="text-[9px] uppercase tracking-widest font-bold">Routines</span>
      </a>
      <a class="flex flex-col items-center justify-center text-on-surface-variant min-w-[64px] min-h-[64px]" href="{% url 'exercise:overview' %}">
          <span class="material-symbols-outlined mb-1">search</span>
          <span class="text-[9px] uppercase tracking-widest font-bold">Browse</span>
      </a>
      <a class="flex flex-col items-center justify-center text-on-surface-variant min-w-[64px] min-h-[64px]" href="{% url 'core:user:overview' user.pk %}">
          <span class="material-symbols-outlined mb-1">person</span>
          <span class="text-[9px] uppercase tracking-widest font-bold">Profile</span>
      </a>
  </nav>
  ```

---

### Task 2: Dashboard URL & Django View Customization

**Files:**
- Modify: `wger/core/urls.py`
- Modify: `wger/core/views/user.py`
- Create: `wger/core/templates/user/dashboard_tailwind.html`

- [ ] **Step 1: Redirect routing from ReactView to native view**
  In [wger/core/urls.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/urls.py#L192), replace the react dashboard view with a native template view:
  ```python
  # Change:
  # path('dashboard', ReactView.as_view(login_required=True), name='dashboard'),
  # To:
  path('dashboard', user.dashboard_tailwind, name='dashboard'),
  ```

- [ ] **Step 2: Create dashboard view logic querying UserStatistics**
  In [wger/core/views/user.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/views/user.py), implement the `dashboard_tailwind` function view:
  ```python
  from django.contrib.auth.decorators import login_required
  from django.shortcuts import render
  from wger.trophies.models import UserStatistics
  from wger.manager.models import WorkoutSession

  @login_required
  def dashboard_tailwind(request):
      stats, _ = UserStatistics.objects.get_or_create(user=request.user)
      latest_session = WorkoutSession.objects.filter(user=request.user).order_by('-date').first()
      return render(request, 'user/dashboard_tailwind.html', {
          'stats': stats,
          'latest_session': latest_session
      })
  ```

- [ ] **Step 3: Write dashboard template HTML with Onyx bento grid**
  Create [dashboard_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/templates/user/dashboard_tailwind.html) mapping database stats dynamically:
  ```html
  {% extends 'template_tailwind.html' %}
  {% block title %}Onyx Dashboard{% endblock %}
  {% block content %}
  <section class="mt-2">
      <h2 class="text-2xl font-extrabold tracking-tight text-primary">Good morning, {{ user.first_name|default:user.username }}</h2>
      <p class="text-on-surface-variant font-medium mt-1">Ready to crush your goals today?</p>
  </section>

  <!-- Bento Grid -->
  <section class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
      <div class="bg-surface-container-low border border-surface-container-high rounded-[24px] p-4 flex items-center justify-between">
          <div class="flex items-center gap-3">
              <span class="material-symbols-outlined text-primary-fixed" style="font-variation-settings: 'FILL' 1;">fitness_center</span>
              <div>
                  <div class="text-xs text-on-surface-variant uppercase font-bold tracking-wider">Total Workouts</div>
                  <div class="text-xl font-extrabold text-primary">{{ stats.total_workouts|default:0 }}</div>
              </div>
          </div>
      </div>
      <div class="bg-surface-container-low border border-surface-container-high rounded-[24px] p-4 flex items-center justify-between">
          <div class="flex items-center gap-3">
              <span class="material-symbols-outlined text-error" style="font-variation-settings: 'FILL' 1;">local_fire_department</span>
              <div>
                  <div class="text-xs text-on-surface-variant uppercase font-bold tracking-wider">Current Streak</div>
                  <div class="text-xl font-extrabold text-primary">{{ stats.current_streak|default:0 }} days</div>
              </div>
          </div>
      </div>
  </section>

  <!-- Last Workout Session -->
  <section class="mt-6">
      <h3 class="text-lg font-bold text-primary mb-4">Last Session</h3>
      <div class="bg-surface-container-low border border-surface-container-high rounded-[24px] p-5">
          {% if latest_session %}
              <div class="text-xs text-primary-fixed uppercase font-bold mb-1">Session Logged</div>
              <h4 class="text-lg font-bold text-primary">{{ latest_session.notes|default:"Workout Logged" }}</h4>
              <div class="text-sm text-on-surface-variant mt-1">Date: {{ latest_session.date }}</div>
          {% else %}
              <div class="text-on-surface-variant">No workouts logged yet. Start training today!</div>
          {% endif %}
      </div>
  </section>
  {% endblock %}
  ```

---

### Task 3: Browse Routines & Custom Routine Detail View

**Files:**
- Modify: `wger/manager/urls.py`
- Modify: `wger/manager/views/routine.py`
- Create: `wger/manager/templates/routine/view_tailwind.html`

- [ ] **Step 1: Map Routine Detail URL to custom template**
  Update the routing configuration in [wger/manager/urls.py](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/manager/urls.py) to point the detail view to the new Tailwind template.

- [ ] **Step 2: Implement Routine View using Onyx card grid**
  Create [view_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/manager/templates/routine/view_tailwind.html) mapping days and exercise slots:
  ```html
  {% extends 'template_tailwind.html' %}
  {% block content %}
  <section class="mb-6">
      <span class="text-xs text-primary-fixed uppercase font-bold tracking-wider">Routine Details</span>
      <h2 class="text-2xl font-extrabold text-primary mt-1">{{ routine.name }}</h2>
      <p class="text-on-surface-variant text-sm mt-1">{{ routine.description|default:"No description available." }}</p>
  </section>

  <section class="flex flex-col gap-6">
      {% for day in routine.day_set.all %}
          <div class="bg-surface-container-low border border-surface-container-high rounded-[24px] p-5">
              <h3 class="text-lg font-bold text-primary mb-3">{{ day.name }}</h3>
              <div class="flex flex-col gap-3">
                  {% for slot in day.slot_set.all %}
                      <div class="flex items-center justify-between border-t border-surface-container-high pt-3 first:border-0 first:pt-0">
                          <div>
                              <div class="font-bold text-primary">{{ slot.obj.name }}</div>
                              <div class="text-xs text-on-surface-variant">
                                  {% for slot_entry in slot.slotentry_set.all %}
                                      {{ slot_entry.reps_config.reps }} reps x {{ slot_entry.weight_config.weight }}kg
                                  {% empty %}
                                      No sets configured
                                  {% endfor %}
                              </div>
                          </div>
                      </div>
                  {% endfor %}
              </div>
          </div>
      {% endfor %}
  </section>
  {% endblock %}
  ```

---

### Task 4: Inline Workout Set Logging (HTMX Implementation)

**Files:**
- Create: `wger/manager/templates/workout/log_tailwind.html`
- Modify: `wger/manager/views/workout.py`

- [ ] **Step 1: Create active workout logging panel**
  Create [log_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/manager/templates/workout/log_tailwind.html) with HTMX submission forms.
  Use inline inputs for sets and repetitions and checkmark buttons targetting `hx-post` for silent background logging.

- [ ] **Step 2: Setup dynamic backend POST listener for inline logs**
  Modify view files to handle partial HTMX fragments returning HTTP 200 on checkmark triggers.
