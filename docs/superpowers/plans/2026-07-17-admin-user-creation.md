# Admin User Creation with Forced Password Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admin users (superusers) to create new users with details (username, email, first name, last name, temporary password) and force those new users to change their password upon their first login.

**Architecture:**
1. Add a `needs_password_change` boolean field to the `UserProfile` model and generate a database migration.
2. Create an admin-only form (`UserAddForm`) to validate and save new users, fully setting up their `UserProfile` (language, default gym, email addresses).
3. Implement a custom middleware `ForcePasswordChangeMiddleware` to intercept authenticated users whose `needs_password_change` flag is `True` and redirect them to the password change view unless they are already on it or logging out.
4. Update password change and confirmation views to clear the `needs_password_change` flag upon successful password update.
5. Create a `UserCreateView` restricted to superusers, map it to the `/user/add-user` URL, and add an "Add User" button to the sidebar of the user list page.

**Tech Stack:** Python, Django, SQLite, Bootstrap 5, django-crispy-forms.

---

### Task 1: Update UserProfile Model and Create Migration

**Files:**
- Modify: `wger/core/models/profile.py`
- Create: `wger/core/migrations/0029_userprofile_needs_password_change.py` (auto-generated)

- [ ] **Step 1: Add needs_password_change field to UserProfile**
  
  Add the field `needs_password_change` in [wger/core/models/profile.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/models/profile.py) around line 112:
  ```python
      needs_password_change = models.BooleanField(
          verbose_name=_('Needs password change'),
          default=False,
      )
  ```

- [ ] **Step 2: Generate the Django migration**
  
  Run: `.venv\Scripts\python.exe manage.py makemigrations`
  Expected: Generated migration file `wger/core/migrations/0029_userprofile_needs_password_change.py` or similar.

- [ ] **Step 3: Run the migration**
  
  Run: `.venv\Scripts\python.exe manage.py migrate`
  Expected: Migration applied successfully to `database.sqlite`.

- [ ] **Step 4: Commit**
  
  ```bash
  git add wger/core/models/profile.py wger/core/migrations/
  git commit -m "feat(core): add needs_password_change to UserProfile and apply migrations"
  ```

---

### Task 2: Create Admin-only User Creation Form

**Files:**
- Modify: `wger/core/forms.py`

- [ ] **Step 1: Add UserAddForm class**
  
  Add `UserAddForm` at the end of [wger/core/forms.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/forms.py):
  ```python
  class UserAddForm(forms.ModelForm):
      password = forms.CharField(
          label=_('Password'),
          widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
          help_text=_('A temporary password that the user will be forced to change on their first login.'),
      )

      class Meta:
          model = User
          fields = ['username', 'email', 'first_name', 'last_name']

      def __init__(self, *args, **kwargs):
          super().__init__(*args, **kwargs)
          self.helper = FormHelper()
          self.helper.form_class = 'wger-form'
          self.helper.layout = Layout(
              'username',
              'email',
              Row(
                  Column('first_name', css_class='col-6'),
                  Column('last_name', css_class='col-6'),
                  css_class='form-row',
              ),
              'password',
              ButtonHolder(Submit('submit', _('Add User'), css_class='btn-success btn-block')),
          )

      def clean_email(self):
          email = self.cleaned_data.get('email')
          if email and User.objects.filter(email=email).exists():
              raise forms.ValidationError(_('A user with that email already exists.'))
          return email

      def save(self, commit=True):
          user = super().save(commit=False)
          user.set_password(self.cleaned_data['password'])
          if commit:
              user.save()
          return user
  ```

- [ ] **Step 2: Commit**
  
  ```bash
  git add wger/core/forms.py
  git commit -m "feat(core): implement UserAddForm for admin user creation"
  ```

---

### Task 3: Create User Creation View

**Files:**
- Modify: `wger/core/views/user.py`

- [ ] **Step 1: Implement UserCreateView**
  
  Add `UserCreateView` in [wger/core/views/user.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/views/user.py) around line 500:
  ```python
  from django.contrib.auth.mixins import UserPassesTestMixin
  from django.views.generic.edit import CreateView
  from django.contrib import messages
  from wger.core.forms import UserAddForm

  class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
      model = User
      form_class = UserAddForm
      template_name = 'form_content.html'
      success_url = reverse_lazy('core:user:list')

      def test_func(self):
          return self.request.user.is_superuser

      def get_context_data(self, **kwargs):
          context = super().get_context_data(**kwargs)
          context['title'] = _('Add User')
          return context

      def form_valid(self, form):
          user = form.save(commit=True)
          
          # Access/create user profile and configure defaults
          from wger.config.models import GymConfig
          from wger.gym.models import GymUserConfig
          from wger.utils.language import load_language
          from django.utils import translation
          from allauth.account.models import EmailAddress

          profile = user.userprofile
          profile.needs_password_change = True
          profile.notification_language = load_language(translation.get_language())
          
          try:
              gym_config = GymConfig.objects.get(pk=1)
              if gym_config.default_gym:
                  profile.gym = gym_config.default_gym
                  profile.save()
                  GymUserConfig.objects.get_or_create(gym=gym_config.default_gym, user=user)
          except GymConfig.DoesNotExist:
              profile.save()

          # Set up primary email address for allauth
          EmailAddress.objects.get_or_create(
              user=user,
              email=user.email,
              defaults={'primary': True, 'verified': True}
          )

          messages.success(self.request, _('User successfully created.'))
          return HttpResponseRedirect(self.get_success_url())
  ```

- [ ] **Step 2: Commit**
  
  ```bash
  git add wger/core/views/user.py
  git commit -m "feat(core): implement UserCreateView restricted to superusers"
  ```

---

### Task 4: Map URL Pattern and Add Admin Button to Template

**Files:**
- Modify: `wger/core/urls.py`
- Modify: `wger/core/templates/user/list.html`

- [ ] **Step 1: Map the Add User View URL**
  
  In [wger/core/urls.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/urls.py) in `patterns_user` list (around line 85):
  ```python
      path(
          'add-user',
          user.UserCreateView.as_view(),
          name='add-user',
      ),
  ```

- [ ] **Step 2: Add option button to user list template**
  
  In [wger/core/templates/user/list.html](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/templates/user/list.html), override the `sidebar` block:
  ```html
  {% block sidebar %}
      {% if request.user.is_superuser %}
      <div class="card mb-3">
          <div class="card-header">
              <span class="{% fa_class 'user-plus' %} me-1"></span>
              {% translate "Admin actions" %}
          </div>
          <div class="card-body">
              <a href="{% url 'core:user:add-user' %}" class="btn btn-success w-100">
                  <span class="{% fa_class 'plus' %} me-1"></span>
                  {% translate "Add User" %}
              </a>
          </div>
      </div>
      {% endif %}
  {% endblock %}
  ```

- [ ] **Step 3: Commit**
  
  ```bash
  git add wger/core/urls.py wger/core/templates/user/list.html
  git commit -m "feat(core): map add-user URL pattern and expose button on user list page"
  ```

---

### Task 5: Implement Forced Password Change Middleware

**Files:**
- Modify: `wger/core/middleware.py`
- Modify: `wger/core/views/user.py`
- Modify: `settings/settings_global.py`

- [ ] **Step 1: Implement ForcePasswordChangeMiddleware**
  
  Add `ForcePasswordChangeMiddleware` in [wger/core/middleware.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/middleware.py) at the end of the file:
  ```python
  class ForcePasswordChangeMiddleware(MiddlewareMixin):
      """
      Middleware to force authenticated users to change their password
      if their UserProfile's needs_password_change flag is True.
      """
      def process_request(self, request):
          if request.user.is_authenticated:
              try:
                  profile = request.user.userprofile
                  if profile.needs_password_change:
                      path_info = remove_language_code(request.path_info)
                      change_pwd_path = remove_language_code(reverse('core:user:change-password'))
                      logout_path = remove_language_code(reverse('core:user:logout'))
                      
                      # Exclude change password, logout, and static/media files
                      if path_info != change_pwd_path and path_info != logout_path:
                          if not request.path.startswith(settings.STATIC_URL) and not request.path.startswith(settings.MEDIA_URL):
                              from django.contrib import messages
                              # Only display message if it is not an AJAX/fetch request
                              if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
                                  messages.warning(request, _('Please change your temporary password before continuing.'))
                              return redirect('core:user:change-password')
              except UserProfile.DoesNotExist:
                  pass
          return None
  ```

- [ ] **Step 2: Update WgerPasswordChangeView and WgerPasswordResetConfirmView to clear the flag**
  
  In [wger/core/views/user.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/views/user.py):
  
  Add `form_valid` method to `WgerPasswordChangeView` (around line 721):
  ```python
      def form_valid(self, form):
          response = super().form_valid(form)
          profile = self.request.user.userprofile
          if profile.needs_password_change:
              profile.needs_password_change = False
              profile.save()
          return response
  ```
  
  Add `form_valid` method to `WgerPasswordResetConfirmView` (around line 767):
  ```python
      def form_valid(self, form):
          user = form.save()
          try:
              profile = user.userprofile
              if profile.needs_password_change:
                  profile.needs_password_change = False
                  profile.save()
          except UserProfile.DoesNotExist:
              pass
          return super().form_valid(form)
  ```

- [ ] **Step 3: Register Middleware in Settings**
  
  In [settings/settings_global.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/settings/settings_global.py) inside `MIDDLEWARE = [...]` list:
  ```python
      'django.contrib.auth.middleware.AuthenticationMiddleware',
      'wger.core.middleware.AuthProxyHeaderMiddleware',
      'wger.core.middleware.ForcePasswordChangeMiddleware', # Add this line
  ```

- [ ] **Step 4: Commit**
  
  ```bash
  git add wger/core/middleware.py wger/core/views/user.py settings/settings_global.py
  git commit -m "feat(core): implement ForcePasswordChangeMiddleware and clear flag upon password change"
  ```

---

### Task 6: Write Unit Tests and Verify

**Files:**
- Create: `wger/core/tests/test_admin_user_creation.py`

- [ ] **Step 1: Create test file**
  
  Create file [wger/core/tests/test_admin_user_creation.py](file:///C:/Users/franc/Desktop/Codex/Workout_app/wger-elfrancia/wger/core/tests/test_admin_user_creation.py) with tests:
  ```python
  from django.contrib.auth.models import User
  from django.urls import reverse
  from wger.core.tests.base_testcase import WgerTestCase

  class AdminUserCreationTestCase(WgerTestCase):
      def setUp(self):
          super().setUp()
          # We have self.admin (superuser) and other member users from WgerTestCase
          # Let's ensure admin is logged in
          
      def test_user_creation_restricted_to_superuser(self):
          # Log in as normal user (e.g. member1)
          self.user_login('member1')
          response = self.client.get(reverse('core:user:add-user'))
          self.assertEqual(response.status_code, 403)
          self.user_logout()

          # Log in as superuser (admin)
          self.user_login('admin')
          response = self.client.get(reverse('core:user:add-user'))
          self.assertEqual(response.status_code, 200)

      def test_user_creation_success_sets_flag(self):
          self.user_login('admin')
          post_data = {
              'username': 'newuser123',
              'email': 'newuser123@example.com',
              'first_name': 'New',
              'last_name': 'User',
              'password': 'TemporaryPassword123!',
          }
          response = self.client.post(reverse('core:user:add-user'), post_data)
          self.assertRedirects(response, reverse('core:user:list'))
          
          # Verify user exists and flag is set
          new_user = User.objects.get(username='newuser123')
          self.assertTrue(new_user.userprofile.needs_password_change)
          self.user_logout()

      def test_forced_password_change_middleware(self):
          # Create user with needs_password_change=True
          user = User.objects.create_user(
              username='tempuser',
              email='temp@example.com',
              password='TempPassword123'
          )
          user.userprofile.needs_password_change = True
          user.userprofile.save()

          # Login as tempuser
          self.client.login(username='tempuser', password='TempPassword123')
          
          # Access dashboard - should redirect to change-password
          response = self.client.get(reverse('core:dashboard'))
          self.assertRedirects(response, reverse('core:user:change-password'))
          
          # Access change password page - should load successfully (no redirect loop)
          response = self.client.get(reverse('core:user:change-password'))
          self.assertEqual(response.status_code, 200)
          
          # Change password
          change_data = {
              'old_password': 'TempPassword123',
              'new_password1': 'NewSecurePassword123!',
              'new_password2': 'NewSecurePassword123!',
          }
          response = self.client.post(reverse('core:user:change-password'), change_data)
          self.assertRedirects(response, reverse('core:user:preferences'))
          
          # Verify flag is cleared
          user.refresh_from_db()
          self.assertFalse(user.userprofile.needs_password_change)
  ```

- [ ] **Step 2: Run the test suite**
  
  Run: `.venv\Scripts\python.exe manage.py test wger.core.tests.test_admin_user_creation`
  Expected: All tests pass.

- [ ] **Step 3: Commit**
  
  ```bash
  git add wger/core/tests/test_admin_user_creation.py
  git commit -m "test(core): add integration and middleware tests for forced password change"
  ```
