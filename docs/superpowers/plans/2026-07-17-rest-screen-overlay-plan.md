# Rest Screen Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a full-screen overlay mode for the rest timer inside the active workout template (`log_tailwind.html`), hiding the exercise list and showing ONLY the timer, adjustments, and a back button. When the timer hits 0, turn the screen yellow-green, show "TEMPO SCADUTO" in bold black, and sound the beep.

---

### Task 1: Update HTML Template structure with Overlay Modal
**Files:**
- Modify: `wger/manager/templates/workout/log_tailwind.html`

- [ ] **Step 1: Define the Full-Screen Overlay layout**
  Add the following overlay structure inside `log_tailwind.html` (e.g. right before the main container, or as the first element inside `{% block content %}`):
  
  ```html
  <!-- Full-Screen Rest Timer Overlay -->
  <div id="rest-timer-overlay" class="fixed inset-0 z-50 bg-[#131313] flex flex-col items-center justify-between py-16 px-6 transition-all duration-300 hidden">
      <!-- Top header label -->
      <div class="text-center">
          <span id="overlay-header-label" class="text-[10px] text-gray-500 uppercase tracking-widest font-black">{% translate "Tempo di recupero" %}</span>
      </div>
  
      <!-- Central timer display -->
      <div class="flex flex-col items-center justify-center flex-grow w-full">
          <div id="overlay-timer-display" class="font-display text-[90px] sm:text-[120px] leading-none text-[#caf300] font-black tracking-tighter tabular-nums mb-2 select-none">
              00:45
          </div>
          <div id="overlay-status-label" class="text-2xl font-black text-black tracking-widest uppercase hidden">
              {% translate "Tempo Scaduto" %}
          </div>
      </div>
  
      <!-- Adjustment controls and Presets (only shown when resting) -->
      <div id="overlay-controls-container" class="flex flex-col items-center gap-6 w-full max-w-sm mb-12">
          <!-- Adjust +/- Buttons -->
          <div class="flex items-center justify-center gap-6">
              <button type="button" onclick="adjustTimer(-10)" class="w-12 h-12 rounded-full bg-white/[0.03] border border-white/[0.08] hover:border-white/30 text-white flex items-center justify-center transition-all">
                  <span class="material-symbols-outlined text-xl">remove</span>
              </button>
              <button type="button" onclick="adjustTimer(10)" class="w-12 h-12 rounded-full bg-white/[0.03] border border-white/[0.08] hover:border-white/30 text-white flex items-center justify-center transition-all">
                  <span class="material-symbols-outlined text-xl">add</span>
              </button>
          </div>
  
          <!-- Presets -->
          <div class="flex flex-wrap justify-center gap-2">
              <button type="button" onclick="setTimerPreset(30)" class="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.1] text-neutral-300 hover:text-white text-xs font-semibold">30s</button>
              <button type="button" onclick="setTimerPreset(60)" class="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.1] text-neutral-300 hover:text-white text-xs font-semibold">1:00</button>
              <button type="button" onclick="setTimerPreset(90)" class="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.1] text-neutral-300 hover:text-white text-xs font-semibold">1:30</button>
              <button type="button" onclick="setTimerPreset(120)" class="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.1] text-neutral-300 hover:text-white text-xs font-semibold">2:00</button>
          </div>
      </div>
  
      <!-- Action Footer Button -->
      <div class="w-full max-w-xs text-center">
          <button id="overlay-back-btn" type="button" onclick="closeOverlay()" class="w-full border border-white/20 hover:border-white/50 text-white hover:bg-white/5 min-h-[50px] py-3 rounded-full flex items-center justify-center font-bold text-xs tracking-widest uppercase transition-all duration-300">
              {% translate "Torna al Workout" %}
          </button>
      </div>
  </div>
  ```

---

### Task 2: Refactor Rest Timer JavaScript Logic
**Files:**
- Modify: `wger/manager/templates/workout/log_tailwind.html` (the `<script>` block in `extra_body`).

- [ ] **Step 1: Update timer display sync, overlay rendering, and color change states**
  Update the script inside `log_tailwind.html` to:
  * Open the full-screen overlay when the timer starts.
  * Turn the overlay bg to `#caf300` (yellow-green), change texts to black, hide adjustments, and show "TEMPO SCADUTO" when `timeLeft === 0`.
  * Restore states when presets are selected or timer is reset/started/closed.
