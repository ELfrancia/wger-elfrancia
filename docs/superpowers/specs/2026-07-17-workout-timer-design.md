# Design Spec: Workout Rest Timer

## 🎯 Goals
1. Make the countdown timer on the active workout page (`log_tailwind.html`) fully interactive and functional.
2. Allow custom adjustment of rest time (adding/subtracting time, setting presets like 30s, 60s, 90s, 120s).
3. Play a clean synth sound via Web Audio API when countdown reaches `00:00` and visually flash the timer.
4. Auto-trigger the countdown timer immediately when a user logs a set successfully (via HTMX event interception).

---

## 🛠️ Design Details

### 1. Interactive Timer UI Layout
Replace the hardcoded `00:45` container in `wger/manager/templates/workout/log_tailwind.html` with:
* **Adjustment Controls**: A minus button `-10s` on the left, a plus button `+10s` on the right of the central display.
* **Large Digital Display**: Clickable element which acts as a Play/Pause toggle.
* **Control Row**:
  * **Play/Pause Button**: Shows a Play or Pause icon based on the timer's current state.
  * **Reset Button**: Restores the timer to the active default/preset time.
  * **Preset Quick-Pills**: Small pill-shaped buttons for `30s`, `1:00`, `1:30`, and `2:00` to quickly assign a rest target.

### 2. JavaScript Logic
An inline JavaScript script module will manage the timer state:
* `timerDuration` (default: 45 seconds, customizable).
* `timeLeft` (tracks current countdown).
* `timerInterval` (interval reference).
* `isPaused` (tracks execution state).
* **Autostart trigger**: Catch the custom `htmx:afterOnLoad` event. If a set log form is successfully posted, automatically reset and start the rest countdown.
* **Beep sound synthesizer**: Use standard browser Web Audio API to play a premium high-pitched chime/beep on completion.

---

## 📂 Target Files
* `wger/manager/templates/workout/log_tailwind.html`
