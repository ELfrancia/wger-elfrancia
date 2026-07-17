# Custom Exercise Creation & Baserow Synchronization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a form modal on the routine builder page allowing users to create custom exercises, save them locally in the SQLite database, and automatically sync them to a self-hosted Baserow database via a background thread.

**Architecture:** Create a Django view `add_custom_exercise_tailwind` in the manager views. This view handles AJAX requests, creates local `CalisthenicsExercise` and native wger `Exercise` / `Translation` objects, and kicks off an asynchronous HTTP POST call to Baserow. Update `add_exercise_tailwind.html` with the modal form and JS.

**Tech Stack:** Python, Django, Tailwind CSS, JavaScript (Fetch API), Baserow REST API.

---

### Task 1: Create Django View and URLs for Custom Exercises

**Files:**
- Modify: `wger/manager/views/routine.py` (append the view function and helper function)
- Modify: `wger/manager/urls.py` (register the URL route)

- [ ] **Step 1: Write helper function for Baserow sync and the Django view**
  In [wger/manager/views/routine.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/manager/views/routine.py), import `threading` and requests, and add the functions:
  
  ```python
  import threading
  import requests
  import logging
  from django.http import JsonResponse
  from django.views.decorators.http import require_POST
  from wger.exercises.models import CalisthenicsExercise, Exercise, Translation, ExerciseCategory, Muscle, Equipment, ExerciseTag
  from wger.core.models import Language
  from wger.core.models.license import License

  logger = logging.getLogger(__name__)

  def _async_push_to_baserow(name, instructions, skill_family, target_muscle, equipment_name):
      baserow_url = os.environ.get('BASEROW_URL', 'http://localhost:8080').rstrip('/')
      baserow_token = os.environ.get('BASEROW_TOKEN')
      baserow_table_id = os.environ.get('BASEROW_TABLE_ID', '322')

      if not baserow_token:
          logger.warning("Baserow token not configured. Skipping sync.")
          return

      headers = {
          "Authorization": f"Token {baserow_token}",
          "Content-Type": "application/json"
      }
      
      payload = {
          "Name": name,
          "Instructions": instructions,
          "Skill Family": skill_family,
          "Target Muscle": target_muscle,
          "Equipment": equipment_name,
          "Is Published": True,
          "Discipline": "calisthenics",
          "Source Exercise ID": f"custom-{uuid.uuid4().hex[:8]}"
      }

      url = f"{baserow_url}/api/database/rows/table/{baserow_table_id}/?user_field_names=true"
      try:
          response = requests.post(url, headers=headers, json=payload, timeout=10)
          response.raise_for_status()
          logger.info(f"Successfully synced custom exercise '{name}' to Baserow.")
      except Exception as e:
          logger.error(f"Failed to sync custom exercise to Baserow: {e}")


  @login_required
  @require_POST
  def add_custom_exercise_tailwind(request, routine_pk, day_pk):
      name = request.POST.get('name', '').strip()
      instructions = request.POST.get('instructions', '').strip()
      skill_family = request.POST.get('skill_family', 'other').strip()
      target_muscle_name = request.POST.get('target_muscle', '').strip()
      weighted = request.POST.get('weighted') == 'on'

      if not name:
          return JsonResponse({'status': 'error', 'message': 'Name is required'}, status=400)

      # 1. Create CalisthenicsExercise locally
      import uuid
      from django.utils.text import slugify
      source_id = f"custom-{uuid.uuid4().hex[:8]}"
      slug = f"{slugify(name)}-{source_id}"
      equipment_name = 'weighted body weight' if weighted else 'body weight'
      
      instructions_list = [line.strip() for line in instructions.split('\n') if line.strip()]

      cal_exercise = CalisthenicsExercise.objects.create(
          source='custom',
          source_exercise_id=source_id,
          slug=slug,
          name=name,
          instructions=instructions_list,
          target_muscle=target_muscle_name,
          equipment=equipment_name,
          skill_family=skill_family,
          discipline='calisthenics',
          is_published=True
      )

      # 2. Create native Exercise
      category, _ = ExerciseCategory.objects.get_or_create(name='Calisthenics')
      default_license = License.objects.first()
      
      base_exercise = Exercise.objects.create(
          uuid=cal_exercise.id,
          category=category,
          license=default_license
      )

      # 3. Associate equipment
      eq_name = 'Dumbbells' if weighted else 'Body weight'
      equipment, _ = Equipment.objects.get_or_create(name=eq_name)
      base_exercise.equipment.add(equipment)

      # 4. Associate target muscle
      if target_muscle_name:
          muscle, _ = Muscle.objects.get_or_create(
              name=target_muscle_name.capitalize(),
              defaults={'name_en': target_muscle_name, 'is_front': True}
          )
          base_exercise.muscles.add(muscle)

      # 5. Create English Translation
      english_lang = Language.objects.get(short_name='en')
      Translation.objects.create(
          exercise=base_exercise,
          language=english_lang,
          name=name,
          description="\n".join(instructions_list),
          license=default_license
      )

      # 6. Create initial tags
      tags = ['bodyweight', 'calisthenics', 'custom']
      if weighted:
          tags.append('weighted')
      if skill_family != 'other':
          tags.append(skill_family.replace('_', '-'))
      for t in tags:
          ExerciseTag.objects.get_or_create(exercise=cal_exercise, tag=t)

      # 7. Start background thread to push to Baserow
      threading.Thread(
          target=_async_push_to_baserow,
          args=(name, instructions, skill_family, target_muscle_name, equipment_name),
          daemon=True
      ).start()

      # Return response
      return JsonResponse({
          'status': 'success',
          'id': base_exercise.id,
          'name': name,
          'muscles': target_muscle_name,
          'skill_family': skill_family.replace('_', ' ').title()
      })
  ```

- [ ] **Step 2: Map the view route in urls.py**
  In [wger/manager/urls.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/manager/urls.py), add the path under `patterns_routine` around line 96:
  ```python
      path(
          '<int:routine_pk>/day/<int:day_pk>/exercise/add-custom',
          routine.add_custom_exercise_tailwind,
          name='add-custom-exercise',
      ),
  ```

- [ ] **Step 3: Commit the backend views and URLs**
  ```bash
  git add wger/manager/views/routine.py wger/manager/urls.py
  git commit -m "feat: implement backend view and URL route for custom exercise creation"
  ```

---

### Task 2: Implement Frontend Modal UI and JS Logic

**Files:**
- Modify: `wger/manager/templates/routines/add_exercise_tailwind.html`

- [ ] **Step 1: Add "Crea Esercizio" Button and Modal form in HTML template**
  In [wger/manager/templates/routines/add_exercise_tailwind.html](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/manager/templates/routines/add_exercise_tailwind.html), place a button right next to the muscle/skill filters in lines 36-50:
  ```html
  <button type="button" id="open-custom-modal-btn" class="bg-surface-container border border-surface-container-high hover:border-[#caf300] text-primary rounded-2xl px-4 py-3 text-sm font-bold flex items-center gap-1 transition-all">
      <span class="material-symbols-outlined text-sm">add</span> {% translate "Custom" %}
  </button>
  ```
  
  And at the end of the `content` block, add the Modal Backdrop and Content:
  ```html
  <!-- Custom Exercise Modal -->
  <div id="custom-exercise-modal" class="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center hidden opacity-0 transition-opacity duration-300">
      <div class="bg-[#131313] border border-surface-container-high rounded-[28px] w-full max-w-lg p-6 flex flex-col gap-5 shadow-2xl transform scale-95 transition-transform duration-300">
          <div class="flex items-center justify-between border-b border-surface-container-high/40 pb-3">
              <h3 class="text-xl font-extrabold text-primary flex items-center gap-2">
                  <span class="material-symbols-outlined text-[#caf300]">fitness_center</span>
                  {% translate "Create Custom Exercise" %}
              </h3>
              <button type="button" id="close-custom-modal-btn" class="text-on-surface-variant hover:text-primary transition-colors">
                  <span class="material-symbols-outlined">close</span>
              </button>
          </div>
          
          <form id="custom-exercise-form" method="post" action="{% url 'manager:routine:add-custom-exercise' day.routine.pk day.pk %}" class="flex flex-col gap-4">
              {% csrf_token %}
              
              <!-- Name -->
              <div class="flex flex-col gap-1.5">
                  <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{% translate "Name" %}</label>
                  <input type="text" name="name" required placeholder="{% translate 'e.g. Archer Push-up' %}"
                         class="w-full bg-[#1c1b1b] border border-surface-container-high rounded-xl px-4 py-3 text-primary placeholder-on-surface-variant/40 focus:outline-none focus:border-[#caf300] text-sm">
              </div>

              <div class="grid grid-cols-2 gap-4">
                  <!-- Skill Family -->
                  <div class="flex flex-col gap-1.5">
                      <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{% translate "Skill Family" %}</label>
                      <select name="skill_family" class="w-full bg-[#1c1b1b] border border-surface-container-high rounded-xl px-3 py-3 text-primary text-sm focus:outline-none focus:border-[#caf300]">
                          <option value="other">{% translate "Other" %}</option>
                          <option value="push_up">{% translate "Push Up" %}</option>
                          <option value="pull_up">{% translate "Pull Up" %}</option>
                          <option value="dip">{% translate "Dip" %}</option>
                          <option value="handstand">{% translate "Handstand" %}</option>
                          <option value="front_lever">{% translate "Front Lever" %}</option>
                          <option value="back_lever">{% translate "Back Lever" %}</option>
                          <option value="l_sit">{% translate "L Sit" %}</option>
                          <option value="planche">{% translate "Planche" %}</option>
                          <option value="squat">{% translate "Squat" %}</option>
                      </select>
                  </div>
                  
                  <!-- Target Muscle -->
                  <div class="flex flex-col gap-1.5">
                      <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{% translate "Target Muscle" %}</label>
                      <select name="target_muscle" class="w-full bg-[#1c1b1b] border border-surface-container-high rounded-xl px-3 py-3 text-primary text-sm focus:outline-none focus:border-[#caf300]">
                          <option value="">{% translate "None" %}</option>
                          {% for muscle in muscles_list %}
                              <option value="{{ muscle }}">{{ muscle }}</option>
                          {% endfor %}
                      </select>
                  </div>
              </div>

              <!-- Weighted Toggle -->
              <div class="flex items-center justify-between bg-surface-container/30 border border-surface-container-high/60 rounded-xl p-3">
                  <div class="flex flex-col">
                      <span class="text-sm font-bold text-primary">{% translate "Weighted / Zavorrato" %}</span>
                      <span class="text-xs text-on-surface-variant">Check if the exercise requires extra weights or is weighted</span>
                  </div>
                  <label class="relative inline-flex items-center cursor-pointer">
                      <input type="checkbox" name="weighted" class="sr-only peer">
                      <div class="w-11 h-6 bg-[#2a2a2a] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-gray-300 after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#caf300] peer-checked:after:bg-[#131313]"></div>
                  </label>
              </div>

              <!-- Instructions -->
              <div class="flex flex-col gap-1.5">
                  <label class="text-xs font-bold text-on-surface-variant uppercase tracking-wider">{% translate "Instructions" %}</label>
                  <textarea name="instructions" rows="3" placeholder="{% translate 'Step 1...\nStep 2...' %}"
                            class="w-full bg-[#1c1b1b] border border-surface-container-high rounded-xl px-4 py-3 text-primary placeholder-on-surface-variant/40 focus:outline-none focus:border-[#caf300] text-sm resize-none"></textarea>
              </div>

              <!-- Form Buttons -->
              <div class="flex gap-3 mt-2">
                  <button type="submit" class="flex-1 bg-[#caf300] text-[#131313] py-3 rounded-full font-bold hover:opacity-90 transition-opacity">
                      {% translate "Save Exercise" %}
                  </button>
                  <button type="button" id="cancel-custom-modal-btn" class="flex-1 border border-surface-container-high text-primary py-3 rounded-full font-bold hover:bg-surface-container transition-colors">
                      {% translate "Cancel" %}
                  </button>
              </div>
          </form>
      </div>
  </div>
  ```

- [ ] **Step 2: Add Javascript modal triggers and AJAX handling**
  In the `extra_body` block or around script section at bottom of [add_exercise_tailwind.html](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/manager/templates/routines/add_exercise_tailwind.html), add JS logic:
  
  ```javascript
  document.addEventListener('DOMContentLoaded', function() {
      const modal = document.getElementById('custom-exercise-modal');
      const openBtn = document.getElementById('open-custom-modal-btn');
      const closeBtn = document.getElementById('close-custom-modal-btn');
      const cancelBtn = document.getElementById('cancel-custom-modal-btn');
      const form = document.getElementById('custom-exercise-form');
      const exerciseListContainer = document.querySelector('.exercise-item').parentElement;

      function openModal() {
          modal.classList.remove('hidden');
          setTimeout(() => {
              modal.classList.remove('opacity-0');
              modal.querySelector('div').classList.remove('scale-95');
          }, 10);
      }

      function closeModal() {
          modal.classList.add('opacity-0');
          modal.querySelector('div').classList.add('scale-95');
          setTimeout(() => {
              modal.classList.add('hidden');
              form.reset();
          }, 300);
      }

      openBtn.addEventListener('click', openModal);
      closeBtn.addEventListener('click', closeModal);
      cancelBtn.addEventListener('click', closeModal);

      // Handle Ajax submit
      form.addEventListener('submit', function(e) {
          e.preventDefault();
          const formData = new FormData(form);

          fetch(form.action, {
              method: 'POST',
              body: formData,
              headers: {
                  'X-Requested-With': 'XMLHttpRequest'
              }
          })
          .then(response => {
              if (!response.ok) {
                  throw new Error('Network response was not ok');
              }
              return response.json();
          })
          .then(data => {
              if (data.status === 'success') {
                  // Create new HTML element in list
                  const newItem = document.createElement('div');
                  newItem.className = "exercise-item flex items-center justify-between p-3 rounded-2xl border border-transparent hover:border-surface-container-highest hover:bg-surface-container-low transition-all cursor-pointer select-none";
                  newItem.setAttribute('data-id', data.id);
                  newItem.setAttribute('data-name', data.name);
                  newItem.setAttribute('data-muscles', data.muscles);
                  newItem.setAttribute('data-skill', data.skill_family);
                  
                  newItem.innerHTML = `
                      <div class="flex items-center gap-3">
                          <div class="w-12 h-12 rounded-full overflow-hidden flex-shrink-0 bg-[#0e0e0e] border border-surface-container-high flex items-center justify-center">
                              <span class="material-symbols-outlined text-on-surface-variant text-lg">fitness_center</span>
                          </div>
                          <div class="flex flex-col">
                              <span class="text-sm font-bold text-primary">${data.name}</span>
                              <span class="text-xs text-on-surface-variant">
                                  ${data.muscles || 'No muscle info'}
                                  ${data.skill_family && data.skill_family !== 'Other' ? ' • ' + data.skill_family : ''}
                              </span>
                          </div>
                      </div>
                      <div class="selected-indicator text-primary-fixed opacity-0 transition-opacity">
                          <span class="material-symbols-outlined text-xl" style="font-variation-settings: 'FILL' 1;">check_circle</span>
                      </div>
                  `;

                  // Insert at top of list
                  exerciseListContainer.insertBefore(newItem, exerciseListContainer.firstChild);

                  // Setup click handler for the new item so it works like others
                  newItem.addEventListener('click', function() {
                      // Deselect all
                      document.querySelectorAll('.exercise-item').forEach(el => {
                          el.classList.remove('border-primary-fixed', 'bg-surface-container-low');
                          el.querySelector('.selected-indicator').classList.add('opacity-0');
                      });
                      
                      // Select this
                      newItem.classList.add('border-primary-fixed', 'bg-surface-container-low');
                      newItem.querySelector('.selected-indicator').classList.remove('opacity-0');
                      
                      // Update form select/value (wger implementation sets hidden inputs or selects)
                      // In the current add_exercise_tailwind.html:
                      const input = document.getElementById('id_exercise') || document.querySelector('select[name="exercise"]');
                      if (input) {
                          // Add option if not present, then select it
                          let option = Array.from(input.options).find(o => o.value == data.id);
                          if (!option) {
                              option = new Option(data.name, data.id);
                              input.add(option);
                          }
                          input.value = data.id;
                      }
                      
                      // Enable submit button
                      const submitBtn = document.getElementById('submit-btn');
                      if (submitBtn) {
                          submitBtn.disabled = false;
                          submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
                      }
                  });

                  // Trigger click to automatically select
                  newItem.click();
                  
                  closeModal();
              }
          })
          .catch(error => {
              console.error('Error:', error);
              alert('Error creating custom exercise. Please try again.');
          });
      });
  });
  ```

- [ ] **Step 3: Commit frontend changes**
  ```bash
  git add wger/manager/templates/routines/add_exercise_tailwind.html
  git commit -m "feat: add Custom Exercise Modal UI and frontend AJAX submission logic"
  ```

---

### Task 3: Write Verification Tests for Custom Exercises

**Files:**
- Create: `wger/exercises/tests/test_custom_exercise.py`

- [ ] **Step 1: Write test case simulating custom exercise AJAX creation**
  Create the test file [wger/exercises/tests/test_custom_exercise.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/exercises/tests/test_custom_exercise.py):
  ```python
  from django.test import TestCase, Client
  from django.urls import reverse
  from django.contrib.auth.models import User
  from wger.exercises.models import CalisthenicsExercise, Exercise, Translation
  from wger.manager.models import Routine, Day

  class CustomExerciseTestCase(TestCase):
      def setUp(self):
          self.client = Client()
          self.user = User.objects.create_user(username='testuser', password='password123')
          self.client.login(username='testuser', password='password123')
          
          # Setup dummy routine and day
          self.routine = Routine.objects.create(
              name="Test Routine",
              user=self.user,
              start="2026-07-17",
              end="2026-08-28"
          )
          self.day = Day.objects.create(
              routine=self.routine,
              name="Day 1",
              order=1
          )

      def test_create_custom_exercise_ajax(self):
          url = reverse('manager:routine:add-custom-exercise', kwargs={
              'routine_pk': self.routine.pk,
              'day_pk': self.day.pk
          })
          
          response = self.client.post(url, {
              'name': 'Custom Handstand Push-up',
              'instructions': 'Get in handstand.\nLower yourself.\nPush up.',
              'skill_family': 'handstand',
              'target_muscle': 'shoulders',
              'weighted': 'on'
          }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
          
          self.assertEqual(response.status_code, 200)
          data = response.json()
          self.assertEqual(data['status'], 'success')
          self.assertEqual(data['name'], 'Custom Handstand Push-up')
          
          # Check database creation
          self.assertEqual(CalisthenicsExercise.objects.filter(name='Custom Handstand Push-up').count(), 1)
          cal_ex = CalisthenicsExercise.objects.get(name='Custom Handstand Push-up')
          self.assertEqual(cal_ex.source, 'custom')
          self.assertEqual(cal_ex.equipment, 'weighted body weight')
          
          # Check native wger structures
          self.assertEqual(Exercise.objects.filter(uuid=cal_ex.id).count(), 1)
          self.assertEqual(Translation.objects.filter(name='Custom Handstand Push-up').count(), 1)
  ```

- [ ] **Step 2: Run the test to verify correctness**
  Run:
  ```bash
  .venv\Scripts\python manage.py test wger.exercises.tests.test_custom_exercise --settings=settings.ci
  ```
  Expected: 1 test ran, OK.

- [ ] **Step 3: Commit test changes**
  ```bash
  git add wger/exercises/tests/test_custom_exercise.py
  git commit -m "test: add verification tests for custom exercise creation"
  ```
