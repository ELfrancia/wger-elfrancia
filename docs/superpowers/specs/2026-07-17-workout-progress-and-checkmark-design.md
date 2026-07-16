# Design Spec: Workout Progress Bar & Non-Illuminated Checkmarks

## 🎯 Goals
1. Maintain the input fields (reps and weight) visible even after a set is marked as completed, but make them disabled and grayed out.
2. Display non-illuminated checkmark buttons (dark/gray background) for uncompleted sets, and bright lime-green (`#caf300`) checkmarks for completed sets.
3. Calculate and display a real-time workout completion progress bar at the top of the active workout page.
4. Dynamically update the progress bar percentage client-side upon checking a set.

---

## 🛠️ Design Details

### 1. Template Changes (`log_tailwind.html`)
* **Set Rows**: Add a class `set-row` to each set item wrapper to easily query them in JS.
* **Progress Bar Area**:
  * Set dynamic width using style `width: {{ progress_percentage }}%;`.
  * Add a progress text label (e.g. `45%`).
* **Forms & Buttons**:
  * For uncompleted sets: Render the input fields inside the form as before, with a check button:
    `bg-[#1c1b1b] border border-[#262626] text-gray-500 hover:text-white`
  * For completed sets: Render disabled input fields and an illuminated check button:
    `bg-[#caf300] text-[#131313]`

### 2. View Changes (`workout.py`)
* Return a complete disabled form snippet on successful HTMX POST request instead of a single checkmark button.
* Calculate the initial completed percentage and pass `progress_percentage` in context.

### 3. JavaScript Changes (`log_tailwind.html`)
* Implement `updateProgressBar()` to count completed sets (disabled check buttons) and total sets, then update the progress bar width and text.
* Call `updateProgressBar()` on page load and inside `htmx:afterOnLoad` listener.

---

## 📂 Target Files
* `wger/manager/views/workout.py`
* `wger/manager/templates/workout/log_tailwind.html`
