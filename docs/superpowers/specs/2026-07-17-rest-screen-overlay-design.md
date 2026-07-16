# Design Spec: Full-Screen Rest Overlay with "Tempo Scaduto" Alarm

## 🎯 Goals
1. Provide a dedicated full-screen overlay for the workout rest timer that hides the active exercises list when active.
2. Only display the big timer, adjustment controls, and a "Go Back / Skip Rest" button during the rest period.
3. Once the countdown hits `00:00`, change the entire screen background to yellow-green (`#caf300`), display a prominent "TEMPO SCADUTO" message in bold black, play the alarm chime, and show a "Back to Workout" button.

---

## 🛠️ Design Details

### 1. Full-Screen Overlay structure (`id="rest-overlay"`)
* **Styling**: `fixed inset-0 z-50 bg-[#131313] flex flex-col items-center justify-between py-16 px-6 transition-all duration-300 hidden`.
* **State Transition**:
  * **Resting state**: Dark background (`bg-[#131313]`), text in `#caf300` / white.
  * **Expired state (`timeLeft === 0`)**: Yellow-green background (`bg-[#caf300]`), all text and buttons in black (`text-[#131313]` / `bg-[#131313]`).

### 2. Inner Elements
* **Header**: Small, clean text "REST TIMER" or "TEMPO DI RIPOSO".
* **Central Display**:
  * Giant timer numbers (e.g. `00:45` in `text-[#caf300]` or `text-black` if expired).
  * Big title `TEMPO SCADUTO` (visible only when expired, in bold black).
* **Control Adjustment Buttons**:
  * `-10s` and `+10s` buttons (hidden when expired).
  * Quick preset pills: `30s`, `1:00`, `1:30`, `2:00` (hidden when expired).
* **Footer Button**:
  * When resting: "Skip Rest / Torna al Workout" (`border border-white/20 hover:border-white/50 text-white`).
  * When expired: "Prossimo Set" (`bg-black text-white hover:bg-neutral-900 shadow-lg px-8 py-3.5`).

---

## 📂 Target Files
* `wger/manager/templates/workout/log_tailwind.html`
