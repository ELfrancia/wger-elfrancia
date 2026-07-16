# Workout Rest Timer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a fully functional, interactive countdown rest timer inside the active workout template (`log_tailwind.html`), supporting quick presets, time modifications, audio beeps, and automatic startup on logging a set.

**Architecture:**
1. Replace the static timer HTML container in `wger/manager/templates/workout/log_tailwind.html` with an interactive control layout (play/pause toggle, adjust +/- buttons, and preset buttons).
2. Insert a script block in `wger/manager/templates/workout/log_tailwind.html` that manages the countdown interval, handles state logic, plays synthetic beep via Web Audio API, and hooks into `htmx:afterOnLoad` to automatically trigger the countdown upon logging a set.

**Tech Stack:** HTML, Tailwind CSS, JavaScript, Web Audio API, HTMX.

---

### Task 1: Refactor template layout and add JavaScript Rest Timer logic
**Files:**
- Modify: `wger/manager/templates/workout/log_tailwind.html:19-24`

- [ ] **Step 1: Replace static HTML timer with adjustment controls and presets**
  Update the timer section to allow play/pause, adjust duration, reset, and click quick set durations.
  
  ```html
      <!-- Timer / Rep Counter Core -->
      <div class="flex flex-col items-center justify-center flex-grow w-full px-6 py-8">
          <!-- Interactive Rest Timer -->
          <div class="flex flex-col items-center gap-4 mb-8">
              <!-- Main Timer Row -->
              <div class="flex items-center justify-center gap-4">
                  <!-- Adjust Minus -->
                  <button type="button" onclick="adjustTimer(-10)" class="w-10 h-10 rounded-full bg-white/[0.03] border border-white/[0.08] hover:border-white/30 text-white flex items-center justify-center transition-all">
                      <span class="material-symbols-outlined text-lg">remove</span>
                  </button>
                  
                  <!-- Large Timer Display -->
                  <div id="timer-display" onclick="toggleTimer()" class="font-display text-[76px] sm:text-[96px] leading-none text-[#caf300] font-black tracking-tighter tabular-nums cursor-pointer select-none hover:scale-105 transition-transform duration-200" title="{% translate 'Click to Play/Pause' %}">
                      00:45
                  </div>
                  
                  <!-- Adjust Plus -->
                  <button type="button" onclick="adjustTimer(10)" class="w-10 h-10 rounded-full bg-white/[0.03] border border-white/[0.08] hover:border-white/30 text-white flex items-center justify-center transition-all">
                      <span class="material-symbols-outlined text-lg">add</span>
                  </button>
              </div>
  
              <!-- Quick Presets and Controls -->
              <div class="flex flex-wrap justify-center items-center gap-2">
                  <!-- Play / Pause -->
                  <button id="btn-timer-play" type="button" onclick="toggleTimer()" class="px-4 py-1.5 rounded-full bg-[#caf300]/10 border border-[#caf300]/20 hover:border-[#caf300] text-[#caf300] text-xs font-bold uppercase tracking-wider flex items-center gap-1 transition-all">
                      <span class="material-symbols-outlined text-sm" id="icon-timer-play">play_arrow</span>
                      <span id="text-timer-play">{% translate "Start" %}</span>
                  </button>
                  
                  <!-- Reset -->
                  <button type="button" onclick="resetTimer()" class="px-4 py-1.5 rounded-full bg-white/[0.03] border border-white/[0.08] hover:border-white/20 text-neutral-400 hover:text-white text-xs font-bold uppercase tracking-wider flex items-center gap-1 transition-all">
                      <span class="material-symbols-outlined text-sm">replay</span>
                      {% translate "Reset" %}
                  </button>
  
                  <!-- Presets divider -->
                  <div class="h-4 w-px bg-white/[0.08] mx-1"></div>
  
                  <!-- Presets -->
                  <button type="button" onclick="setTimerPreset(30)" class="px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] hover:bg-white/[0.06] text-neutral-400 hover:text-white text-xs font-semibold">30s</button>
                  <button type="button" onclick="setTimerPreset(60)" class="px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] hover:bg-white/[0.06] text-neutral-400 hover:text-white text-xs font-semibold">1:00</button>
                  <button type="button" onclick="setTimerPreset(90)" class="px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] hover:bg-white/[0.06] text-neutral-400 hover:text-white text-xs font-semibold">1:30</button>
                  <button type="button" onclick="setTimerPreset(120)" class="px-3 py-1 rounded-full bg-white/[0.03] border border-white/[0.05] hover:bg-white/[0.06] text-neutral-400 hover:text-white text-xs font-semibold">2:00</button>
              </div>
          </div>
  ```

- [ ] **Step 2: Add script tag inside extra_body block**
  Add the complete JavaScript module to control the countdown timer, synthesise audio beeps, and catch set logging.
  Modify: `wger/manager/templates/workout/log_tailwind.html:92-93` (at the bottom of the file).
  
  ```html
  {% block extra_body %}
  <script>
      let defaultDuration = 45; // seconds
      let timerDuration = defaultDuration;
      let timeLeft = timerDuration;
      let timerInterval = null;
      let isRunning = false;
  
      const timerDisplay = document.getElementById('timer-display');
      const btnPlay = document.getElementById('btn-timer-play');
      const iconPlay = document.getElementById('icon-timer-play');
      const textPlay = document.getElementById('text-timer-play');
  
      function formatTime(seconds) {
          const m = Math.floor(seconds / 60).toString().padStart(2, '0');
          const s = (seconds % 60).toString().padStart(2, '0');
          return `${m}:${s}`;
      }
  
      function updateDisplay() {
          if (timerDisplay) {
              timerDisplay.innerText = formatTime(timeLeft);
              if (timeLeft <= 0) {
                  timerDisplay.classList.add('text-red-500', 'animate-pulse');
                  timerDisplay.classList.remove('text-[#caf300]');
              } else {
                  timerDisplay.classList.remove('text-red-500', 'animate-pulse');
                  timerDisplay.classList.add('text-[#caf300]');
              }
          }
      }
  
      function startCountdown() {
          if (timerInterval) clearInterval(timerInterval);
          isRunning = true;
          if (textPlay) textPlay.innerText = "{% translate 'Pause' %}";
          if (iconPlay) iconPlay.innerText = "pause";
          if (btnPlay) {
              btnPlay.classList.add('bg-amber-500/10', 'border-amber-500/20', 'text-amber-500');
              btnPlay.classList.remove('bg-[#caf300]/10', 'border-[#caf300]/20', 'text-[#caf300]');
          }
  
          timerInterval = setInterval(() => {
              if (timeLeft > 0) {
                  timeLeft--;
                  updateDisplay();
                  if (timeLeft === 0) {
                      playBeep();
                  }
              } else {
                  clearInterval(timerInterval);
                  isRunning = false;
                  resetTimerControls();
              }
          }, 1000);
      }
  
      function pauseCountdown() {
          if (timerInterval) clearInterval(timerInterval);
          isRunning = false;
          resetTimerControls();
      }
  
      function resetTimerControls() {
          if (textPlay) textPlay.innerText = "{% translate 'Start' %}";
          if (iconPlay) iconPlay.innerText = "play_arrow";
          if (btnPlay) {
              btnPlay.classList.remove('bg-amber-500/10', 'border-amber-500/20', 'text-amber-500');
              btnPlay.classList.add('bg-[#caf300]/10', 'border-[#caf300]/20', 'text-[#caf300]');
          }
      }
  
      function toggleTimer() {
          if (isRunning) {
              pauseCountdown();
          } else {
              if (timeLeft <= 0) {
                  timeLeft = timerDuration;
              }
              startCountdown();
          }
      }
  
      function resetTimer() {
          pauseCountdown();
          timeLeft = timerDuration;
          updateDisplay();
      }
  
      function adjustTimer(amount) {
          timeLeft = Math.max(0, timeLeft + amount);
          updateDisplay();
      }
  
      function setTimerPreset(seconds) {
          pauseCountdown();
          timerDuration = seconds;
          timeLeft = seconds;
          updateDisplay();
      }
  
      function playBeep() {
          try {
              const ctx = new (window.AudioContext || window.webkitAudioContext)();
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.connect(gain);
              gain.connect(ctx.destination);
              osc.type = 'sine';
              osc.frequency.setValueAtTime(880, ctx.currentTime);
              gain.gain.setValueAtTime(0.1, ctx.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
              osc.start(ctx.currentTime);
              osc.stop(ctx.currentTime + 0.3);
          } catch (e) {
              console.error("Web Audio API not supported or blocked: ", e);
          }
      }
  
      // Auto-trigger timer when a set is logged via HTMX
      document.body.addEventListener('htmx:afterOnLoad', function(evt) {
          if (evt.detail.xhr && evt.detail.xhr.status === 200) {
              // Reset and start countdown automatically!
              timeLeft = timerDuration;
              updateDisplay();
              startCountdown();
          }
      });
  
      // Initial render
      updateDisplay();
  </script>
  {% endblock %}
  ```

- [ ] **Step 3: Commit rest timer implementation**
  ```bash
  git add wger/manager/templates/workout/log_tailwind.html
  git commit -m "feat: implement interactive rest timer on active workout screen"
  ```

---

### Task 2: Verify rest timer UI and controls
**Files:**
- Test: Manual browser checks.

- [ ] **Step 1: Check server status**
  Run: `docker compose ps`
  Expected: Web app is running.

- [ ] **Step 2: Check template contains new timer functions**
  Run: `Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000/en/routine/view`
  Expected: StatusCode is 200 (or redirects appropriately), template compiles cleanly.
