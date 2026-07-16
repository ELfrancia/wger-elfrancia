# Design Spec: Responsive Set Layout optimization

## 🎯 Goals
1. Optimize the layout of workout sets (Reps, Weight, Notes, and actions) to be mobile-friendly and fit on narrow screens without wrapping or overflowing.
2. Reduce the corner rounding (`rounded-lg` for cards, `rounded-md` for inputs) to reclaim physical space and align with a clean, high-performance UI aesthetic.
3. Keep the overall look consistent with the global Onyx design system (dark mode, `#caf300` accents, `#131313`/`#1c1b1b` backgrounds, and Material Symbols).

---

## 🛠️ Design Details

### 1. Card Container (`.flex-col`)
* **Classes**: `rounded-lg` instead of `rounded-xl`.
* **Border/Background**: Maintain standard `bg-[#131313]/60 border border-[#262626]/80`.

### 2. Main Row (Horizontal Flow)
The reps, weight, save buttons, note toggles, and delete actions will sit in a single row using flexbox.
* **Reps Input**: Wrapped in a container with `bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5`. Text is `font-mono text-base font-extrabold`.
* **Weight Input**: Wrapped in a container with `bg-[#1c1b1b]/50 border border-[#262626]/80 rounded-md px-1.5 py-0.5`. Text is `font-mono text-base font-extrabold text-[#caf300]`.
* **Note Toggle Button**: An icon button `<button type="button" onclick="toggleNoteField(...)">` with a `notes` icon. If a comment exists, the icon is highlighted in `#caf300`.
* **Delete Button**: A close/delete button (`close` icon) aligned on the far right of the row.

### 3. Expandable Notes Section
* **Behavior**: Hidden by default if the note is empty (`{% if not entry.comment %}hidden{% endif %}`).
* **Layout**: A full-width text input with `rounded-md`, styled with `#1c1b1b` background and a small save icon on the right.
* **Scripting**: Inline JS toggle utility (`toggleNoteField`) that switches the `hidden` class on the comment form container.

---

## 📂 Target Files
* `wger/manager/templates/routines/view_tailwind.html`

---

## 🧪 Verification Plan
* Validate layout on simulated mobile screens (width 320px - 375px) in Chrome DevTools or programmatically using desktop tests.
* Ensure HTMX posts (`hx-post`) for saving reps/weight and notes remain fully functional.
