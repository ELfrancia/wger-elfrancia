# Workout Progress and Checkmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement non-illuminated checkmark buttons for active workout sets, and show a dynamic workout completion progress bar that auto-updates when a set is completed. Keep input fields visible but disabled when marked completed.

---

### Task 1: Refactor workout logging view in python backend
**Files:**
- Modify: `wger/manager/views/workout.py`

- [ ] **Step 1: Calculate dynamic progress percentage on load**
  Update `log_tailwind` to calculate the total count of sets (`SlotEntry` objects) for the active day, and the count of completed sets (`session.logs.count()`). Pass `progress_percentage` in the render context.
  
- [ ] **Step 2: Update HTMX POST response**
  Import `gettext as _` from `django.utils.translation` and return the complete disabled form layout (with disabled reps, weight, and bright lime-green checkmark) for HTMX POST requests.

---

### Task 2: Refactor active workout template layout and JS
**Files:**
- Modify: `wger/manager/templates/workout/log_tailwind.html`

- [ ] **Step 1: Add set-row classes and update progress bar markup**
  Add class `set-row` to the wrapper div of each set item. Update progress bar container width to set `width: {{ progress_percentage }}%;` initially, and add a text label `id="workout-progress-text"` showing `{{ progress_percentage }}%`.

- [ ] **Step 2: Update row buttons styling**
  Render the reps and weight inputs as disabled if `slot_entry.id in logged_set_ids`.
  Render the checkmark button with a dark/non-illuminated state by default, and a bright lime-green disabled checkmark state if completed.

- [ ] **Step 3: Update JavaScript with updateProgressBar logic**
  Add a JS function `updateProgressBar()` to count total and completed sets client-side and dynamically adjust the progress bar width and text. Call this function on load and in the HTMX post-load event.
