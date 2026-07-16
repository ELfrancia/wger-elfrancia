# Responsive Set Layout Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign workout sets (reps, weight, note, and actions) to be compact, responsive on mobile devices, and less rounded, using Tailwind CSS and lightweight JavaScript toggling.

**Architecture:** 
1. Modify standard exercise sets and superset exercise entries in the Django templates to render horizontal rows on all viewports.
2. Incorporate note toggle buttons that dynamically reveal/hide notes inputs on demand via a lightweight JavaScript function.
3. Apply styling variables to reduce the border-radius (`rounded-lg` for cards, `rounded-md` for inputs) to reclaim horizontal spacing.

**Tech Stack:** Django templates, HTML, Tailwind CSS, JavaScript, HTMX (for actions).

---

### Task 1: Add Toggle JavaScript Function to Template
**Files:**
- Modify: `wger/manager/templates/routines/view_tailwind.html:321-338`

- [ ] **Step 1: Implement toggleNoteField javascript function**
  Add the helper function inside the `extra_body` block scripts to handle showing/hiding comment containers and auto-focusing the note input.
  
  ```javascript
  function toggleNoteField(containerId) {
      const container = document.getElementById(containerId);
      if (container) {
          if (container.classList.contains('hidden')) {
              container.classList.remove('hidden');
              const input = container.querySelector('input[name="comment"]');
              if (input) input.focus();
          } else {
              container.classList.add('hidden');
          }
      }
  }
  ```

- [ ] **Step 2: Commit javascript script addition**
  ```bash
  git commit -m "feat: add toggleNoteField script helper to view_tailwind"
  ```

---

### Task 2: Refactor Standard Exercise Sets Layout
**Files:**
- Modify: `wger/manager/templates/routines/view_tailwind.html:208-258`

- [ ] **Step 1: Replace HTML markup for single-exercise sets**
  Update the loop container for standard sets (`{% for entry in slot.entries.all %}`) to use `rounded-lg`, place all main control parameters on a single flex row, add the note expand button, and set the notes container as a toggled section underneath.
  
  ```html
  {% for entry in slot.entries.all %}
      <div class="flex flex-col gap-2 p-2 bg-[#131313]/60 border border-[#262626]/80 rounded-lg hover:border-gray-800 transition-colors">
          <!-- Main Row -->
          <div class="flex items-center justify-between gap-2 flex-wrap sm:flex-nowrap w-full">
              <!-- Set Reps and Weight Edit Form -->
              <form hx-post="{% url 'manager:routine:update-set' routine.pk day.pk slot.pk entry.pk %}" class="flex items-center gap-1.5 flex-wrap sm:flex-nowrap">
                  {% csrf_token %}
                  <span class="text-[10px] font-bold text-gray-500 uppercase tracking-widest min-w-[36px]">Set {{ entry.set_index }}</span>
                  
                  <div class="flex items-center gap-1">
                      <!-- Reps Input -->
                      <div class="flex items-center bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5 focus-within:border-[#caf300] transition-colors">
                          <input type="number" name="reps" value="{{ entry.reps_config.reps }}" required min="1" max="100"
                                 class="w-9 bg-transparent text-center font-mono text-sm font-extrabold text-white border-0 p-0 focus:ring-0 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none">
                          <span class="text-[9px] text-gray-500 font-semibold select-none ml-0.5">reps</span>
                      </div>
                      
                      <span class="text-gray-600 text-xs font-bold select-none">×</span>
                      
                      <!-- Weight Input -->
                      <div class="flex items-center bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5 focus-within:border-[#caf300] transition-colors">
                          <input type="number" name="weight" value="{{ entry.weight_config.weight }}" required min="0" step="0.1"
                                 class="w-12 bg-transparent text-center font-mono text-sm font-extrabold text-[#caf300] border-0 p-0 focus:ring-0 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none">
                          <span class="text-[9px] text-[#caf300] font-bold select-none ml-0.5">KG</span>
                      </div>
                  </div>

                  <!-- Save Button -->
                  <button type="submit" class="w-6 h-6 rounded bg-[#caf300]/10 border border-[#caf300]/20 hover:border-[#caf300] text-[#caf300] hover:text-white flex items-center justify-center transition-all duration-300" title="{% translate 'Save set' %}">
                      <span class="material-symbols-outlined text-[14px]">save</span>
                  </button>
              </form>

              <!-- Action Buttons (Note toggle + Delete) -->
              <div class="flex items-center gap-1.5">
                  <!-- Note Toggle Button -->
                  <button type="button" onclick="toggleNoteField('note-container-{{ entry.pk }}')" 
                          class="w-6 h-6 rounded flex items-center justify-center border transition-all duration-300 {% if entry.comment %}border-[#caf300]/40 text-[#caf300] bg-[#caf300]/5 hover:bg-[#caf300]/10{% else %}border-[#262626] text-gray-500 hover:text-white bg-[#1c1b1b]/60{% endif %}"
                          id="note-toggle-{{ entry.pk }}" title="{% translate 'Add/Edit note' %}">
                      <span class="material-symbols-outlined text-[14px]">notes</span>
                  </button>

                  <!-- Delete Button -->
                  <form hx-post="{% url 'manager:routine:delete-set' routine.pk day.pk slot.pk entry.pk %}" hx-confirm="{% translate 'Remove this set?' %}" class="inline">
                      {% csrf_token %}
                      <button type="submit" class="w-6 h-6 rounded bg-[#1c1b1b]/60 border border-[#262626] hover:border-red-500/40 hover:text-red-400 flex items-center justify-center text-gray-500 transition-all duration-300" title="{% translate 'Delete set' %}">
                          <span class="material-symbols-outlined text-[14px]">close</span>
                      </button>
                  </form>
              </div>
          </div>

          <!-- Expandable Note Container -->
          <div id="note-container-{{ entry.pk }}" class="{% if not entry.comment %}hidden{% endif %} mt-1 border-t border-[#262626]/20 pt-1.5">
              <form hx-post="{% url 'manager:routine:update-set-notes' routine.pk day.pk slot.pk entry.pk %}" class="relative flex items-center w-full">
                  {% csrf_token %}
                  <span class="material-symbols-outlined text-gray-500 absolute left-2.5 text-xs pointer-events-none">notes</span>
                  <input type="text" name="comment" value="{{ entry.comment }}" placeholder="{% translate 'Add set note...' %}"
                         class="w-full bg-[#1c1b1b]/40 border border-[#262626] rounded-md pl-7 pr-7 py-1 text-[11px] text-gray-300 placeholder-gray-600 focus:bg-[#131313] focus:border-[#caf300] focus:outline-none transition-all duration-300">
                  <button type="submit" class="absolute right-2 text-gray-500 hover:text-[#caf300] flex items-center">
                      <span class="material-symbols-outlined text-[12px]">save</span>
                  </button>
              </form>
          </div>
      </div>
  {% empty %}
      <span class="text-xs text-gray-500">{% translate "No sets configured" %}</span>
  {% endfor %}
  ```

- [ ] **Step 2: Commit standard exercises styles refactor**
  ```bash
  git commit -m "style: apply responsive, compact set layout to standard exercises"
  ```

---

### Task 3: Refactor Superset Exercises Sets Layout
**Files:**
- Modify: `wger/manager/templates/routines/view_tailwind.html:112-154`

- [ ] **Step 1: Replace HTML markup for superset sets**
  Update the loop container for superset entries (`{% if entry.exercise_id == exercise.id %}`) to align with the styling variables and HTML structure implemented in Task 2.
  
  ```html
  <div class="flex flex-col gap-2 p-2 bg-[#131313]/60 border border-[#262626]/80 rounded-lg hover:border-gray-800 transition-colors">
      <!-- Main Row -->
      <div class="flex items-center justify-between gap-2 flex-wrap sm:flex-nowrap w-full">
          <!-- Set Reps and Weight Edit Form -->
          <form hx-post="{% url 'manager:routine:update-set' routine.pk day.pk slot.pk entry.pk %}" class="flex items-center gap-1.5 flex-wrap sm:flex-nowrap">
              {% csrf_token %}
              <span class="text-[10px] font-bold text-gray-500 uppercase tracking-widest min-w-[36px]">Set {{ entry.set_index }}</span>
              
              <div class="flex items-center gap-1">
                  <!-- Reps Input -->
                  <div class="flex items-center bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5 focus-within:border-[#caf300] transition-colors">
                      <input type="number" name="reps" value="{{ entry.reps_config.reps }}" required min="1" max="100"
                             class="w-9 bg-transparent text-center font-mono text-sm font-extrabold text-white border-0 p-0 focus:ring-0 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none">
                      <span class="text-[9px] text-gray-500 font-semibold select-none ml-0.5">reps</span>
                  </div>
                  
                  <span class="text-gray-600 text-xs font-bold select-none">×</span>
                  
                  <!-- Weight Input -->
                  <div class="flex items-center bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5 focus-within:border-[#caf300] transition-colors">
                      <input type="number" name="weight" value="{{ entry.weight_config.weight }}" required min="0" step="0.1"
                             class="w-12 bg-transparent text-center font-mono text-sm font-extrabold text-[#caf300] border-0 p-0 focus:ring-0 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none">
                      <span class="text-[9px] text-[#caf300] font-bold select-none ml-0.5">KG</span>
                  </div>
              </div>

              <!-- Save Button -->
              <button type="submit" class="w-6 h-6 rounded bg-[#caf300]/10 border border-[#caf300]/20 hover:border-[#caf300] text-[#caf300] hover:text-white flex items-center justify-center transition-all duration-300" title="{% translate 'Save set' %}">
                  <span class="material-symbols-outlined text-[14px]">save</span>
              </button>
          </form>

          <!-- Action Buttons (Note toggle + Delete) -->
          <div class="flex items-center gap-1.5">
              <!-- Note Toggle Button -->
              <button type="button" onclick="toggleNoteField('note-container-{{ entry.pk }}')" 
                      class="w-6 h-6 rounded flex items-center justify-center border transition-all duration-300 {% if entry.comment %}border-[#caf300]/40 text-[#caf300] bg-[#caf300]/5 hover:bg-[#caf300]/10{% else %}border-[#262626] text-gray-500 hover:text-white bg-[#1c1b1b]/60{% endif %}"
                      id="note-toggle-{{ entry.pk }}" title="{% translate 'Add/Edit note' %}">
                  <span class="material-symbols-outlined text-[14px]">notes</span>
              </button>

              <!-- Delete Button -->
              <form hx-post="{% url 'manager:routine:delete-set' routine.pk day.pk slot.pk entry.pk %}" hx-confirm="{% translate 'Remove this set?' %}" class="inline">
                  {% csrf_token %}
                  <button type="submit" class="w-6 h-6 rounded bg-[#1c1b1b]/60 border border-[#262626] hover:border-red-500/40 hover:text-red-400 flex items-center justify-center text-gray-500 transition-all duration-300" title="{% translate 'Delete set' %}">
                      <span class="material-symbols-outlined text-[14px]">close</span>
                  </button>
              </form>
          </div>
      </div>

      <!-- Expandable Note Container -->
      <div id="note-container-{{ entry.pk }}" class="{% if not entry.comment %}hidden{% endif %} mt-1 border-t border-[#262626]/20 pt-1.5">
          <form hx-post="{% url 'manager:routine:update-set-notes' routine.pk day.pk slot.pk entry.pk %}" class="relative flex items-center w-full">
              {% csrf_token %}
              <span class="material-symbols-outlined text-gray-500 absolute left-2.5 text-xs pointer-events-none">notes</span>
              <input type="text" name="comment" value="{{ entry.comment }}" placeholder="{% translate 'Add set note...' %}"
                     class="w-full bg-[#1c1b1b]/40 border border-[#262626] rounded-md pl-7 pr-7 py-1 text-[11px] text-gray-300 placeholder-gray-600 focus:bg-[#131313] focus:border-[#caf300] focus:outline-none transition-all duration-300">
              <button type="submit" class="absolute right-2 text-gray-500 hover:text-[#caf300] flex items-center">
                  <span class="material-symbols-outlined text-[12px]">save</span>
              </button>
          </form>
      </div>
  </div>
  ```

- [ ] **Step 2: Commit superset exercises styles refactor**
  ```bash
  git commit -m "style: apply responsive, compact set layout to superset exercises"
  ```

---

### Task 4: Verify Layout and Functionality
**Files:**
- Test: Manual browser checks.

- [ ] **Step 1: Check server execution inside Docker**
  Verify the Django container is running without issues and accepts incoming connections.
  Run: `docker compose ps`
  Expected: Containers are Up and healthy.

- [ ] **Step 2: Check template structure and basic render**
  Request the template view on the loopback IP:
  Run: `Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000`
  Expected: StatusCode is 200, output renders with the new structures.
```
