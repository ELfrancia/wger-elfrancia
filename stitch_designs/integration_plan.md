# UI Integration Plan - Onyx Athletic Tracker Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the premium Onyx Athletic Tracker Tailwind-based UI designs into the selfhosted wger Django project, replacing or wrapping the existing Bootstrap 5 templates.

**Architecture:** We will create a new base template `template_tailwind.html`, setup a Tailwind compiler/builder in `package.json`, and gradually override the default Bootstrap views (Dashboard, Routine Detail, Active Workout) with the new HTML structures, mapping Django models (`UserStatistics`, `Routine`, `Session`, `Log`) into the template contexts.

**Tech Stack:** Django, Python, Tailwind CSS, HTML5, HTMX, Google Material Symbols.

---

### Task 1: Setup Tailwind CSS & Base Templates

**Files:**
- Create: `wger/core/templates/template_tailwind.html`
- Modify: `package.json`

- [ ] **Step 1: Create the new Tailwind-based base template**
  Create [template_tailwind.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/templates/template_tailwind.html) matching the font styles and design system configurations from the Stitch screens. Include Inter, Material Symbols Outlined, and Tailwind compiler.
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

- [ ] **Step 2: Install and configure local Tailwind compiler in package.json**
  Update [package.json](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/package.json) to build production Tailwind CSS if selfhosting in an offline/restricted environment, mapping classes to `wger/**/*.html`.

---

### Task 2: Home Dashboard Integration

**Files:**
- Modify: `wger/core/views/user.py`
- Modify: `wger/core/templates/user/dashboard.html`

- [ ] **Step 1: Map Django view context for dashboard statistics**
  Ensure the dashboard view queries `UserStatistics` for the current user and passes it to the context:
  ```python
  # In wger/core/views/user.py
  stats, _ = UserStatistics.objects.get_or_create(user=request.user)
  context['stats'] = stats
  ```

- [ ] **Step 2: Replace dashboard template structure with Stitch design**
  Apply layout from [home_dashboard.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/stitch_designs/home_dashboard.html) inside [dashboard.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/core/templates/user/dashboard.html):
  *   Greeting: `Good morning, {{ user.first_name|default:user.username }}`
  *   Bento stats: Map `{{ stats.total_workouts }}` and streaks.
  *   Last Session: Query `last_session = Session.objects.filter(user=user).latest('date')` and display its title and category.

---

### Task 3: Workout Routine Detail View

**Files:**
- Modify: `wger/manager/views/routine.py`
- Modify: `wger/manager/templates/routine/view.html`

- [ ] **Step 1: Load routine, days, and slot entries in view**
  Ensure the routine view passes the list of days and nested exercises.

- [ ] **Step 2: Replace template with Stitch Workout Detail layout**
  Update [view.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/manager/templates/routine/view.html) using the layout in [workout_detail.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/stitch_designs/workout_detail.html):
  *   Loop through days: `{% for day in routine.day_set.all %}`
  *   Loop through exercise slots: `{% for slot in day.slot_set.all %}`
  *   Display muscle badges and equipment targets for each exercise.

---

### Task 4: Active Workout Logging (HTMX Interactive)

**Files:**
- Modify: `wger/manager/templates/workout/log.html`

- [ ] **Step 1: Integrate Active Workout UI**
  Integrate the dynamic set tracker from [active_workout.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/stitch_designs/active_workout.html) into [log.html](file:///C:/Users/franc/Desktop/codex/Workout_app/wger-elfrancia/wger/manager/templates/workout/log.html).
- [ ] **Step 2: Configure HTMX inline actions**
  Use `hx-post` and `hx-swap` on checkmark buttons to submit a completed set (creating a `SlotEntry` log row) without doing full-page reloads.
