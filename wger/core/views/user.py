# -*- coding: utf-8 -*-

# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

# Standard Library
import logging
import re
from urllib.parse import quote

# Django
from django import forms
from django.conf import settings
from django.db import IntegrityError
from django.contrib import messages
from django.contrib.auth import (
    login as django_login,
    logout as django_logout,
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.mixins import (
    LoginRequiredMixin,
    PermissionRequiredMixin,
    UserPassesTestMixin,
)
from django.contrib.auth.models import User
from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
)
from django.http import (
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseRedirect,
)
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.template.context_processors import csrf
from django.urls import (
    reverse,
    reverse_lazy,
)
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import (
    gettext as _,
    gettext_lazy,
)
from django.views import generic
from django.views.decorators.http import require_POST
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    UpdateView,
)

# Third Party
from allauth.account.mixins import RedirectAuthenticatedUserMixin
from allauth.account.views import (
    LoginView as AllauthLoginView,
    SignupView as AllauthSignupView,
)
from allauth.mfa.utils import is_mfa_enabled
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    ButtonHolder,
    Column,
    Layout,
    Row,
    Submit,
)
from rest_framework.authtoken.models import Token

# wger
from wger.core.forms import (
    PasswordConfirmationForm,
    PasswordResetFormCaptcha,
    UsernameConfirmationForm,
    UserPersonalInformationForm,
    UserPreferencesForm,
    UserAddForm,
)
from wger.gym.helpers import is_same_gym
from wger.gym.models import (
    AdminUserNote,
    Contract,
)
from wger.manager.models import (
    Routine,
    WorkoutLog,
    WorkoutSession,
)
from wger.nutrition.models import NutritionPlan
from wger.utils.api_token import (
    blacklist_jwt_refresh_tokens,
    count_active_jwt_refresh_tokens,
    create_token,
)
from wger.utils.generic_views import (
    WgerFormMixin,
    WgerMultiplePermissionRequiredMixin,
)
from wger.utils.headless_long_lived import (
    list_long_lived_sessions,
    mint_long_lived_refresh_token,
    revoke_all_long_lived_sessions,
    revoke_long_lived_session,
)
from wger.weight.models import WeightEntry
from wger.core.models import UserProfile


logger = logging.getLogger(__name__)


# Session key used to carry a freshly minted refresh token across the
# post-redirect step on the api-key page. The token is shown once and then
# immediately popped.
_NEW_REFRESH_TOKEN_SESSION_KEY = '_wger_new_long_lived_refresh_token'


# Custom URL scheme registered by the flutter app in Info.plist, AndroidManifest.xml, etc.
_APP_AUTH_SCHEME = 'wger'
_APP_AUTH_HOST = 'app-auth'

# Hard cap on the echoed ?state= value. The app generates 256 bits of
# entropy (~43 base64url chars); anything wildly larger is junk we refuse
# to reflect into the redirect URL.
_APP_AUTH_STATE_MAX_LEN = 128
_APP_AUTH_STATE_ALLOWED = re.compile(r'\A[A-Za-z0-9_\-]+\Z')


@login_required()
def delete(request, user_pk=None):
    """
    Delete a user account and all his data, requires password confirmation first

    If no user_pk is present, the user visiting the URL will be deleted, otherwise
    a gym administrator is deleting a different user
    """

    if user_pk:
        user = get_object_or_404(User, pk=user_pk)

        # Forbidden if the user has not enough rights, doesn't belong to the
        # gym or is an admin as well. General admins can delete all users.
        if not request.user.has_perm('gym.manage_gyms') and (
            not request.user.has_perm('gym.manage_gym')
            or not is_same_gym(request.user, user)
            or user.has_perm('gym.manage_gym')
            or user.has_perm('gym.gym_trainer')
            or user.has_perm('gym.manage_gyms')
        ):
            return HttpResponseForbidden()
    else:
        user = request.user

    # Accounts without a usable password (e.g. social logins) can't confirm with
    # a password, so they confirm by typing the username instead.
    data = request.POST or None
    if request.user.has_usable_password():
        form = PasswordConfirmationForm(user=request.user, data=data)
    else:
        form = UsernameConfirmationForm(
            user=request.user, confirm_username=user.username, data=data
        )

    if request.method == 'POST' and form.is_valid():
        user.delete()
        messages.success(request, _('Account "{0}" was successfully deleted').format(user.username))

        if not user_pk:
            django_logout(request)
            return HttpResponseRedirect(reverse('software:features'))
        else:
            gym_pk = request.user.userprofile.gym_id
            if gym_pk is None:
                return HttpResponseRedirect(reverse('core:dashboard'))
            return HttpResponseRedirect(reverse('gym:gym:user-list', kwargs={'pk': gym_pk}))
    form.helper.form_action = request.path
    context = {'form': form, 'user_delete': user}

    return render(request, 'user/delete_account.html', context)


@login_required()
@require_POST
def trainer_login(request, user_pk):
    """
    Allows a trainer to 'log in' as the selected user.

    POST-only: rebinding the session is a state change and must go through
    Django's CSRF protection, which only applies to unsafe HTTP methods.
    """
    user = get_object_or_404(User, pk=user_pk)
    orig_user_pk = request.user.pk
    trainer_identity_pk = request.session.get('trainer.identity')

    # If the request user is not a trainer themselves they may only act within
    # an established trainer session and only ever to switch back to that
    # original trainer.
    if not request.user.has_perm('gym.gym_trainer'):
        if not trainer_identity_pk:
            return HttpResponseForbidden()
        original_trainer = get_object_or_404(User, pk=trainer_identity_pk)
        if not original_trainer.has_perm('gym.gym_trainer'):
            return HttpResponseForbidden()
        if user.pk != trainer_identity_pk:
            return HttpResponseForbidden()

    # Direct trainer-login: target must not itself be a privileged account.
    if request.user.has_perm('gym.gym_trainer') and (
        user.has_perm('gym.gym_trainer')
        or user.has_perm('gym.manage_gym')
        or user.has_perm('gym.manage_gyms')
    ):
        return HttpResponseForbidden()

    # Changing is only allowed between the same gym
    if not is_same_gym(request.user, user):
        return HttpResponseNotFound(
            f'There are no users in gym "{request.user.userprofile.gym}" with user ID "{user_pk}".'
        )

    # Check if we're switching back to our original account
    own = False
    if (
        user.has_perm('gym.gym_trainer')
        or user.has_perm('gym.manage_gym')
        or user.has_perm('gym.manage_gyms')
    ):
        own = True

    # Note: when logging without authenticating, it is necessary to set the
    # authentication backend
    if own:
        del request.session['trainer.identity']
    django_login(request, user, 'django.contrib.auth.backends.ModelBackend')

    if not own:
        request.session['trainer.identity'] = orig_user_pk
        next_url = request.POST.get('next') or request.GET.get('next')
        if next_url and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return HttpResponseRedirect(next_url)
        return HttpResponseRedirect(reverse('core:index'))
    else:
        return HttpResponseRedirect(
            reverse('gym:gym:user-list', kwargs={'pk': user.userprofile.gym_id})
        )


def logout(request):
    """
    Logout the user. For temporary users, delete them.
    """
    user = request.user
    is_temp = False
    user_id = None
    if user and user.is_authenticated:
        user_id = getattr(user, 'id', None)
        try:
            is_temp = getattr(user.userprofile, 'is_temporary', False)
        except Exception:
            is_temp = False

    django_logout(request)

    if is_temp and user_id is not None:
        try:
            from django.contrib.auth.models import User
            User.objects.filter(id=user_id).delete()
        except Exception:
            pass

    return HttpResponseRedirect(reverse('core:user:login'))


class WgerSignupView(AllauthSignupView):
    """
    allauth's signup view, with two wger carve-outs: registration disabled
    globally redirects to the features page (instead of allauth's "signup
    closed" page), and temporary (guest) users may still reach the
    registration page so they can create a real account.

    The wger-specific profile setup (notification language, default gym) lives
    in WgerAccountAdapter.save_user().
    """

    def dispatch(self, request, *args, **kwargs):
        if not settings.WGER_SETTINGS['ALLOW_REGISTRATION']:
            return HttpResponseRedirect(reverse('software:features'))
        if request.user.is_authenticated and request.user.userprofile.is_temporary:
            # Skip RedirectAuthenticatedUserMixin's "already logged in" redirect
            return super(RedirectAuthenticatedUserMixin, self).dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)


@login_required
def preferences(request):
    """
    An overview of all user preferences
    """
    context = {}
    context.update(csrf(request))

    if request.method == 'POST':
        form = UserPreferencesForm(data=request.POST, instance=request.user.userprofile)
        form.user = request.user

        if form.is_valid():
            form.save()
            messages.success(request, _('Settings successfully updated'))
            return HttpResponseRedirect(reverse('core:user:preferences'))

        messages.error(request, _('Please correct the errors below.'))
    else:
        data = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
        }
        form = UserPreferencesForm(initial=data, instance=request.user.userprofile)

    context['form'] = form
    context['email_verified'] = request.user.userprofile.is_verified
    context['mfa_enabled'] = is_mfa_enabled(request.user)
    context['has_usable_password'] = request.user.has_usable_password()

    return render(request, 'user/preferences.html', context)


class UserActivationConfirmMixin:
    """
    GET renders a confirmation form; only POST applies the activation state
    change. (De)activating a user is a state change and must go through
    Django's CSRF protection, which only applies to unsafe HTTP methods
    (e.g. POST), not GET.
    """

    confirm_title = ''
    success_message = ''
    new_is_active = None

    def get(self, request, pk):
        edit_user = get_object_or_404(User, pk=pk)
        form = forms.Form()
        form.helper = FormHelper()
        form.helper.form_method = 'post'
        form.helper.form_action = request.path
        form.helper.layout = Layout(
            ButtonHolder(Submit('submit', self.confirm_title, css_class='btn-warning btn-block'))
        )
        return render(
            request,
            'confirm.html',
            {
                'title': self.confirm_title,
                'confirm_message': str(edit_user),
                'form': form,
            },
        )

    def post(self, request, pk):
        edit_user = get_object_or_404(User, pk=pk)
        edit_user.is_active = self.new_is_active
        edit_user.save()
        messages.success(request, self.success_message)
        return HttpResponseRedirect(reverse('core:user:overview', kwargs={'pk': pk}))


class UserDeactivateView(
    LoginRequiredMixin,
    WgerMultiplePermissionRequiredMixin,
    UserActivationConfirmMixin,
    generic.View,
):
    """
    Deactivates a user
    """

    model = User
    permission_required = ('gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')
    confirm_title = gettext_lazy('Deactivate this user?')
    success_message = gettext_lazy('The user was successfully deactivated')
    new_is_active = False

    def dispatch(self, request, *args, **kwargs):
        """
        Only managers and trainers for this gym can access the members
        """
        edit_user = get_object_or_404(User, pk=self.kwargs['pk'])

        if not request.user.is_authenticated:
            return HttpResponseForbidden()

        if (
            request.user.has_perm('gym.manage_gym') or request.user.has_perm('gym.gym_trainer')
        ) and not is_same_gym(request.user, edit_user):
            return HttpResponseForbidden()

        # A user with only the trainer permission must not be able to (de)activate
        # other gym staff (managers, fellow trainers, general managers). Group
        # membership is checked directly so the rule still applies when the
        # target account is currently deactivated (``has_perm`` returns ``False``
        # for inactive users).
        if (
            request.user.has_perm('gym.gym_trainer')
            and not request.user.has_perm('gym.manage_gym')
            and not request.user.has_perm('gym.manage_gyms')
            and edit_user.groups.filter(
                name__in=('gym_trainer', 'gym_manager', 'general_gym_manager')
            ).exists()
        ):
            return HttpResponseForbidden()

        return super(UserDeactivateView, self).dispatch(request, *args, **kwargs)


class UserActivateView(
    LoginRequiredMixin,
    WgerMultiplePermissionRequiredMixin,
    UserActivationConfirmMixin,
    generic.View,
):
    """
    Activates a previously deactivated user
    """

    model = User
    permission_required = ('gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')
    confirm_title = gettext_lazy('Activate this user?')
    success_message = gettext_lazy('The user was successfully activated')
    new_is_active = True

    def dispatch(self, request, *args, **kwargs):
        """
        Only managers and trainers for this gym can access the members
        """
        edit_user = get_object_or_404(User, pk=self.kwargs['pk'])

        if not request.user.is_authenticated:
            return HttpResponseForbidden()

        if (
            request.user.has_perm('gym.manage_gym') or request.user.has_perm('gym.gym_trainer')
        ) and not is_same_gym(request.user, edit_user):
            return HttpResponseForbidden()

        # A user with only the trainer permission must not be able to
        # (de)activate other gym staff (managers, fellow trainers,
        # general managers). Group membership is checked directly so the
        # rule still applies when the target account is currently
        # deactivated (``has_perm`` returns ``False`` for inactive users).
        if (
            request.user.has_perm('gym.gym_trainer')
            and not request.user.has_perm('gym.manage_gym')
            and not request.user.has_perm('gym.manage_gyms')
            and edit_user.groups.filter(
                name__in=('gym_trainer', 'gym_manager', 'general_gym_manager')
            ).exists()
        ):
            return HttpResponseForbidden()

        return super(UserActivateView, self).dispatch(request, *args, **kwargs)


class UserEditView(
    WgerFormMixin,
    LoginRequiredMixin,
    WgerMultiplePermissionRequiredMixin,
    UpdateView,
):
    """
    View to update the personal information of an user by an admin
    """

    model = User
    title = gettext_lazy('Edit user')
    permission_required = ('gym.manage_gym', 'gym.manage_gyms')
    form_class = UserPersonalInformationForm

    def dispatch(self, request, *args, **kwargs):
        """
        Check permissions

        - Managers can edit members of their own gym
        - General managers can edit every member
        """
        user = request.user
        if not user.is_authenticated:
            return HttpResponseForbidden()

        if (
            user.has_perm('gym.manage_gym')
            and not user.has_perm('gym.manage_gyms')
            and not is_same_gym(user, self.get_object())
        ):
            return HttpResponseForbidden()

        return super(UserEditView, self).dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('core:user:overview', kwargs={'pk': self.kwargs['pk']})

    def get_context_data(self, **kwargs):
        """
        Send some additional data to the template
        """
        context = super(UserEditView, self).get_context_data(**kwargs)
        context['title'] = _('Edit {0}'.format(self.object))
        return context


@login_required
def api_key(request):
    """
    Allows the user to generate an API key for the REST API
    """

    context = {}
    context.update(csrf(request))

    try:
        token = Token.objects.get(user=request.user)
    except Token.DoesNotExist:
        token = None

    if request.method == 'POST' and request.POST.get('new_key'):
        token = create_token(request.user, request.POST.get('new_key'))

        # Redirect so a refresh doesn't try to rotate again
        return HttpResponseRedirect(reverse('core:user:api-key'))

    if request.method == 'POST' and request.POST.get('delete_key'):
        Token.objects.filter(user=request.user).delete()
        messages.success(request, _('API key was deleted'))
        return HttpResponseRedirect(reverse('core:user:api-key'))

    if request.method == 'POST' and request.POST.get('revoke_jwt_sessions'):
        blacklist_jwt_refresh_tokens(request.user)
        messages.success(request, _('All API sessions were revoked'))
        return HttpResponseRedirect(reverse('core:user:api-key'))

    # Long-lived refresh tokens (headless JWT, backed by a dedicated session).
    if request.method == 'POST' and request.POST.get('new_refresh_token'):
        new_refresh_token = mint_long_lived_refresh_token(
            request.user,
            settings.HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN,
        )
        # Carry the freshly minted token across the post-redirect step so the
        # next render can show it exactly once.
        request.session[_NEW_REFRESH_TOKEN_SESSION_KEY] = new_refresh_token
        return HttpResponseRedirect(reverse('core:user:api-key'))

    if request.method == 'POST' and request.POST.get('revoke_refresh_token'):
        if revoke_long_lived_session(request.user, request.POST['revoke_refresh_token']):
            messages.success(request, _('Refresh token was revoked'))
        return HttpResponseRedirect(reverse('core:user:api-key'))

    if request.method == 'POST' and request.POST.get('revoke_all_refresh_tokens'):
        count = revoke_all_long_lived_sessions(request.user)
        if count:
            messages.success(
                request,
                _('Revoked {count} refresh token(s)').format(count=count),
            )
        return HttpResponseRedirect(reverse('core:user:api-key'))

    context['token'] = token
    context['active_jwt_sessions'] = count_active_jwt_refresh_tokens(request.user)
    context['new_refresh_token'] = request.session.pop(_NEW_REFRESH_TOKEN_SESSION_KEY, None)
    context['long_lived_sessions'] = list_long_lived_sessions(request.user)
    context['refresh_token_lifetime_days'] = settings.HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN // 86400

    return render(request, 'user/api_key.html', context)


@login_required
def app_auth_handoff(request):
    """
    Browser-side endpoint that mints a long-lived headless refresh token for
    the authenticated user and redirects to a custom URL scheme so the wger
    mobile app can pick it up.

    The user must already be authenticated; @login_required redirects through
    the normal allauth login flow first.

    A ``?state=<nonce>`` query parameter is echoed back into the redirect
    fragment so the app can verify the response came from a handoff it started
    itself. The value is treated as opaque but constrained to base64url characters
    and a sane length to prevent abuse of the reflection.
    """
    token = mint_long_lived_refresh_token(
        request.user,
        settings.HEADLESS_JWT_REFRESH_TOKEN_EXPIRES_IN,
    )

    state = request.GET.get('state', '')
    if state and (len(state) > _APP_AUTH_STATE_MAX_LEN or not _APP_AUTH_STATE_ALLOWED.match(state)):
        state = ''

    # Token goes in the URL fragment, not the query string, so it never lands
    # in server access logs or referer headers. Refresh-token rotation is
    # the backstop against the one remaining leak surface (browser history).
    fragment = f'token={quote(token, safe="")}'
    if state:
        fragment += f'&state={quote(state, safe="")}'
    return_uri = f'{_APP_AUTH_SCHEME}://{_APP_AUTH_HOST}#{fragment}'
    return render(
        request,
        'user/app_auth_handoff.html',
        {'return_uri': return_uri},
    )


class UserDetailView(LoginRequiredMixin, WgerMultiplePermissionRequiredMixin, DetailView):
    """
    User overview for gyms
    """

    model = User
    permission_required = ('gym.manage_gym', 'gym.manage_gyms', 'gym.gym_trainer')
    template_name = 'user/overview.html'
    context_object_name = 'current_user'

    def dispatch(self, request, *args, **kwargs):
        """
        Check permissions

        - Only managers for this gym can access the members
        - General managers can access the detail page of all users
        """
        user = request.user

        if not user.is_authenticated:
            return HttpResponseForbidden()

        if (
            (user.has_perm('gym.manage_gym') or user.has_perm('gym.gym_trainer'))
            and not user.has_perm('gym.manage_gyms')
            and not user.is_superuser
            and not user.is_staff
            and not is_same_gym(user, self.get_object())
        ):
            return HttpResponseForbidden()

        return super(UserDetailView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        """
        Send some additional data to the template
        """
        context = super(UserDetailView, self).get_context_data(**kwargs)
        out = []
        routines = Routine.objects.filter(user=self.object).all()
        for routine in routines:
            logs = WorkoutLog.objects.filter(routine=routine)
            out.append(
                {
                    'routine': routine,
                    'logs': logs.dates('date', 'day').count(),
                    'last_log': logs.last(),
                }
            )
        context['routine_data'] = out
        context['weight_entries'] = WeightEntry.objects.filter(user=self.object).order_by('-date')[
            :5
        ]
        context['nutrition_plans'] = NutritionPlan.objects.filter(user=self.object).order_by(
            '-creation_date'
        )[:5]
        context['session'] = WorkoutSession.objects.filter(user=self.object).order_by('-date')[:10]
        context['admin_notes'] = AdminUserNote.objects.filter(member=self.object)[:5]
        context['contracts'] = Contract.objects.filter(member=self.object)[:5]

        page_user = self.object  # type: User
        request_user = self.request.user  # type: User
        context['enable_login_button'] = request_user.has_perm('gym.gym_trainer') and is_same_gym(
            request_user, page_user
        )
        context['gym_name'] = None  # request_user.userprofile.gym.name
        return context


class UserListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    """
    Overview of all users in the instance
    """

    model = User
    template_name = 'user/user_list_tailwind.html'

    def test_func(self):
        user = self.request.user
        return user.is_authenticated and (
            user.is_superuser
            or user.is_staff
            or user.has_perm('gym.manage_gyms')
        )

    def get_queryset(self):
        """
        Return a list with the users, not really a queryset.
        """
        user = self.request.user
        out = {'admins': [], 'members': []}

        qs = User.objects.select_related('usercache', 'userprofile__gym')
        if not (user.is_superuser or user.is_staff or user.has_perm('gym.manage_gyms')):
            gym = getattr(getattr(user, 'userprofile', None), 'gym', None)
            if gym:
                qs = qs.filter(userprofile__gym=gym)
            else:
                qs = qs.none()

        for u in qs.all():
            out['members'].append({'obj': u, 'last_log': None})  # u.usercache.last_activity

        return out

    def get_context_data(self, **kwargs):
        """
        Pass other info to the template
        """
        context = super(UserListView, self).get_context_data(**kwargs)
        context['show_gym'] = True
        context['user_table'] = {
            'keys': [
                _('ID'),
                _('Username'),
                _('Name'),
                _('Last activity'),
                _('Gym'),
            ],
            'users': context['object_list']['members'],
        }
        return context


class UserCreateView(LoginRequiredMixin, UserPassesTestMixin, CreateView):
    model = User
    form_class = UserAddForm
    template_name = 'user/add_user_tailwind.html'
    success_url = reverse_lazy('core:user:list')

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = _('Add User')
        return context

    def form_valid(self, form):
        self.object = form.save(commit=True)
        user = self.object

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
                GymUserConfig.objects.get_or_create(gym=gym_config.default_gym, user=user)
        except GymConfig.DoesNotExist:
            pass

        profile.save()

        if user.email:
            EmailAddress.objects.get_or_create(
                user=user,
                email=user.email,
                defaults={'primary': True, 'verified': True}
            )

        messages.success(self.request, _('User successfully created.'))
        return HttpResponseRedirect(self.get_success_url())


class WgerPasswordChangeView(PasswordChangeView):
    template_name = 'user/change_password_tailwind.html'
    success_url = reverse_lazy('core:dashboard')
    title = gettext_lazy('Change password')

    def get_form(self, form_class=None):
        form = super(WgerPasswordChangeView, self).get_form(form_class)
        form.helper = FormHelper()
        form.helper.form_class = 'wger-form'
        form.helper.layout = Layout(
            'old_password',
            Row(
                Column('new_password1', css_class='col-6'),
                Column('new_password2', css_class='col-6'),
                css_class='form-row',
            ),
            ButtonHolder(Submit('submit', _('Save'), css_class='btn-success btn-block')),
        )
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        profile = self.request.user.userprofile
        if profile.needs_password_change:
            profile.needs_password_change = False
            profile.save()
        messages.success(self.request, _('Password aggiornata con successo! Benvenuto in Onyx.'))
        return response


class WgerPasswordResetView(PasswordResetView):
    template_name = 'user/password_reset_tailwind.html'
    email_template_name = 'registration/password_reset_email.html'
    success_url = reverse_lazy('core:user:password_reset_done')
    from_email = settings.WGER_SETTINGS['EMAIL_FROM']

    def get_form_class(self):
        if settings.WGER_SETTINGS['USE_RECAPTCHA']:
            return PasswordResetFormCaptcha

        # From django
        return PasswordResetForm

    def get_form(self, form_class=None):
        # Massage django's default form. Our form already has a helper.
        if not settings.WGER_SETTINGS['USE_RECAPTCHA']:
            form = super().get_form(form_class)
            form.helper = FormHelper()
            form.helper.form_class = 'wger-form'
            form.helper.add_input(Submit('submit', _('Save'), css_class='btn-success btn-block'))
            return form

        return super().get_form(form_class)


class WgerPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = 'user/password_reset_confirm_tailwind.html'
    success_url = reverse_lazy('core:user:login')

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.helper = FormHelper()
        form.helper.form_class = 'wger-form'
        form.helper.add_input(Submit('submit', _('Save'), css_class='btn-success btn-block'))
        return form

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


class WgerLoginView(AllauthLoginView):
    """
    allauth's login view, with one wger carve-out: temporary (guest) users are
    still allowed to reach the login page so they can sign in as a real
    account. allauth would otherwise redirect every authenticated user away.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if hasattr(request.user, 'userprofile') and request.user.userprofile.is_temporary:
                # Skip RedirectAuthenticatedUserMixin's "already logged in"
                # redirect so temp users can sign in as a real account.
                return super(RedirectAuthenticatedUserMixin, self).dispatch(
                    request, *args, **kwargs
                )

            # Real authenticated user: respect ?next= or send them to the dashboard.
            next_url = request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect(reverse('core:dashboard'))

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['use_social_auth'] = bool(settings.WGER_SOCIAL_PROVIDERS)
        context['PASSKEY_LOGIN_ENABLED'] = getattr(settings, 'MFA_PASSKEY_LOGIN_ENABLED', False) and getattr(settings, 'WGER_PASSKEY_LOGIN_ENABLED', False)
        return context


@login_required
def dashboard_tailwind(request):
    from wger.trophies.models import UserStatistics
    from wger.core.models import DailyActivity
    from wger.manager.models import WorkoutSession
    from django.utils import timezone
    import datetime
    stats, created_stats = UserStatistics.objects.get_or_create(user=request.user)
    latest_session = WorkoutSession.objects.filter(user=request.user).order_by('-date', '-time_start').first()

    active_draft_session = WorkoutSession.objects.filter(
        user=request.user,
        status='active',
    ).select_related('day', 'routine').order_by('-date', '-time_start', '-id').first()

    try:
        activity, created_activity = DailyActivity.objects.get_or_create(user=request.user, date=timezone.localdate())
    except IntegrityError:
        activity = DailyActivity.objects.get(user=request.user, date=timezone.localdate())
    profile = request.user.userprofile
    ten_days_ago = timezone.localdate() - datetime.timedelta(days=10)
    from django.db.models import Count
    completed_sessions = WorkoutSession.objects.filter(
        user=request.user,
        date__gte=ten_days_ago
    ).annotate(num_logs=Count('logs')).filter(num_logs__gt=0).select_related('day', 'routine').order_by('-date', '-time_start')
    return render(request, 'user/dashboard_tailwind.html', {
        'stats': stats,
        'latest_session': latest_session,
        'active_draft_session': active_draft_session,
        'activity': activity,
        'profile': profile,
        'completed_sessions': completed_sessions,
    })


@login_required
def profile_tailwind(request):
    from wger.trophies.models import UserStatistics
    from decimal import Decimal, InvalidOperation
    from django.conf import settings
    from django.core.files.storage import FileSystemStorage
    import os

    stats, created_stats = UserStatistics.objects.get_or_create(user=request.user)
    profile = request.user.userprofile

    if request.method == 'POST':
        steps_goal = request.POST.get('steps_goal')
        calories_goal = request.POST.get('calories_goal')
        water_goal = request.POST.get('water_goal')
        avatar_url = request.POST.get('avatar_url')
        avatar_file = request.FILES.get('avatar_file')

        updated = False
        if steps_goal is not None and steps_goal != '':
            try:
                clean_steps = str(steps_goal).replace('.', '').replace(',', '').replace(' ', '')
                val = int(clean_steps)
                if 0 <= val <= 1_000_000:
                    profile.steps_goal = val
                    updated = True
                else:
                    messages.error(request, _('Steps goal must be between 0 and 1,000,000.'))
            except (ValueError, TypeError):
                messages.error(request, _('Invalid value for steps goal.'))
        if calories_goal is not None and calories_goal != '':
            try:
                clean_cals = str(calories_goal).replace('.', '').replace(',', '').replace(' ', '')
                val = int(clean_cals)
                if 0 <= val <= 50_000:
                    profile.calories_goal = val
                    updated = True
                else:
                    messages.error(request, _('Calories goal must be between 0 and 50,000.'))
            except (ValueError, TypeError):
                messages.error(request, _('Invalid value for calories goal.'))
        if water_goal is not None and water_goal != '':
            try:
                water_val_str = str(water_goal).replace(',', '.')
                val = Decimal(water_val_str)
                if Decimal('0.0') <= val <= Decimal('50.0'):
                    profile.water_goal = val
                    updated = True
                else:
                    messages.error(request, _('Water goal must be between 0 and 50 liters.'))
            except (ValueError, TypeError, InvalidOperation):
                messages.error(request, _('Invalid value for water goal.'))
        if avatar_file:
            from django.core.exceptions import ValidationError
            from wger.utils.images import validate_image_static_no_animation
            from PIL import Image

            try:
                if avatar_file.size > 5 * 1024 * 1024:
                    raise ValidationError(_('The maximum avatar file size is 5MB.'))
                validate_image_static_no_animation(avatar_file)
                avatar_file.open()
                img = Image.open(avatar_file)
                img_format = img.format.lower()
                ext = '.jpg' if img_format == 'jpeg' else f".{img_format}"
                filename = f"avatar_{request.user.id}{ext}"
                fs = FileSystemStorage(location=settings.MEDIA_ROOT, base_url=settings.MEDIA_URL)
                if fs.exists(filename):
                    fs.delete(filename)
                saved_name = fs.save(filename, avatar_file)
                profile.avatar_url = fs.url(saved_name)
                updated = True
            except ValidationError as e:
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
            except Exception as e:
                logger.error(f"Avatar upload failed for user {request.user.id}: {e}")
                messages.error(request, _('Invalid avatar image file.'))
        elif avatar_url is not None:
            clean_url = avatar_url.strip()
            if clean_url:
                if clean_url.startswith(('http://', 'https://')):
                    profile.avatar_url = clean_url
                    updated = True
                else:
                    messages.error(request, _('Avatar URL must start with http:// or https://'))
            else:
                profile.avatar_url = ''
                updated = True

        if updated:
            if profile.gym_id:
                from wger.gym.models import Gym
                if not Gym.objects.filter(id=profile.gym_id).exists():
                    profile.gym = None
            try:
                profile.save()
                messages.success(request, _('Profile settings successfully updated.'))
                return redirect('core:profile_tailwind')
            except Exception as e:
                logger.error(f"Failed to save user profile {request.user.id}: {e}")
                messages.error(request, _('Failed to update profile settings.'))

    return render(request, 'user/profile_tailwind.html', {
        'stats': stats,
        'profile': profile,
    })


@login_required
@require_POST
def log_daily_activity(request):
    import decimal
    from decimal import Decimal
    from django.utils import timezone
    from wger.core.models import DailyActivity

    try:
        activity, created_activity = DailyActivity.objects.get_or_create(
            user=request.user,
            date=timezone.localdate()
        )
    except IntegrityError:
        activity = DailyActivity.objects.get(user=request.user, date=timezone.localdate())

    activity_type = request.POST.get('activity_type')
    amount = request.POST.get('amount')
    value = request.POST.get('value')

    if activity_type == 'steps':
        try:
            if value is not None and value != '':
                val = int(value)
                if 0 <= val <= 1_000_000:
                    activity.steps = val
                    activity.save()
            elif amount is not None and amount != '':
                amt = int(amount)
                new_steps = activity.steps + amt
                if 0 <= new_steps <= 1_000_000:
                    activity.steps = new_steps
                    activity.save()
        except (ValueError, TypeError, Exception):
            pass
    elif activity_type == 'calories':
        try:
            if value is not None and value != '':
                val = int(value)
                if 0 <= val <= 50_000:
                    activity.calories = val
                    activity.save()
            elif amount is not None and amount != '':
                amt = int(amount)
                new_cals = activity.calories + amt
                if 0 <= new_cals <= 50_000:
                    activity.calories = new_cals
                    activity.save()
        except (ValueError, TypeError, Exception):
            pass
    elif activity_type == 'water':
        try:
            if value is not None and value != '':
                val_str = str(value).replace(',', '.')
                val = Decimal(val_str)
                if Decimal('0.0') <= val <= Decimal('50.0'):
                    activity.water = val
                    activity.save()
            elif amount is not None and amount != '':
                amt_str = str(amount).replace(',', '.')
                new_water = activity.water + Decimal(amt_str)
                if Decimal('0.0') <= new_water <= Decimal('50.0'):
                    activity.water = new_water
                    activity.save()
        except (ValueError, TypeError, decimal.InvalidOperation, Exception):
            pass

    profile = request.user.userprofile
    return render(request, 'user/daily_activity_fragment.html', {
        'activity': activity,
        'profile': profile,
    })


@login_required
def session_details_tailwind(request, session_id):
    from wger.manager.models import WorkoutSession, WorkoutLog, Routine
    from wger.manager.helpers import create_day_from_session
    from collections import OrderedDict
    import datetime

    session = get_object_or_404(WorkoutSession, id=session_id)
    if session.user != request.user:
        return HttpResponseForbidden()

    if request.method == 'POST' and request.POST.get('action') == 'save_as_routine_day':
        target_routine_id = request.POST.get('target_routine_id')
        new_routine_name = request.POST.get('new_routine_name')
        routine_day_name = request.POST.get('routine_day_name')
        try:
            created_day = create_day_from_session(
                user=request.user,
                session=session,
                target_routine_id=target_routine_id,
                new_routine_name=new_routine_name,
                day_name=routine_day_name,
            )
            if created_day:
                messages.success(request, _("Workout salvato come giorno di routine con successo!"))
                return redirect('manager:routine:view', pk=created_day.routine.pk)
            else:
                messages.error(request, _('Impossibile salvare il giorno di routine: routine di destinazione non valida o non trovata.'))
        except Exception as e:
            logger.error(f"Failed to create day from session {session_id} for user {request.user.id}: {e}")
            messages.error(request, _('Impossibile salvare il giorno di routine.'))

    from django.utils import timezone
    time_start_local = None
    if session.time_start:
        dt = datetime.datetime.combine(session.date, session.time_start)
        dt_utc = timezone.make_aware(dt, timezone.UTC)
        dt_local = timezone.localtime(dt_utc)
        time_start_local = dt_local.time()

    time_end_local = None
    if session.time_end:
        dt = datetime.datetime.combine(session.date, session.time_end)
        dt_utc = timezone.make_aware(dt, timezone.UTC)
        dt_local = timezone.localtime(dt_utc)
        time_end_local = dt_local.time()

    # Get duration if available
    duration_str = None
    if time_start_local and time_end_local:
        start_dt = datetime.datetime.combine(session.date, time_start_local)
        end_dt = datetime.datetime.combine(session.date, time_end_local)
        if end_dt < start_dt:
            end_dt += datetime.timedelta(days=1)
        total_seconds = int((end_dt - start_dt).total_seconds())
        if total_seconds < 60:
            duration_str = f"{total_seconds} sec"
        else:
            duration_mins = total_seconds // 60
            duration_str = f"{duration_mins} min"

    # Get logs grouped by exercise, preserving chronological order of logs
    from django.db.models import Q
    logs_query = Q(session=session)
    if session.date and session.routine:
        logs_query |= Q(user=session.user, routine=session.routine, date__date=session.date)

    logs = WorkoutLog.objects.filter(logs_query).select_related('exercise', 'weight_unit', 'repetitions_unit').distinct().order_by('date', 'id')
    
    grouped_logs = OrderedDict()
    for log in logs:
        exercise = log.exercise
        if exercise not in grouped_logs:
            grouped_logs[exercise] = []
        grouped_logs[exercise].append(log)

    user_routines = Routine.objects.filter(user=request.user)

    return render(request, 'user/session_details.html', {
        'session': session,
        'duration_str': duration_str,
        'grouped_logs': grouped_logs.items(),
        'time_start_local': time_start_local,
        'time_end_local': time_end_local,
        'user_routines': user_routines,
    })


@login_required
@require_POST
def update_log_ajax(request):
    import json
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404
    from wger.manager.models import WorkoutLog

    try:
        data = json.loads(request.body)
        log_id = data.get('log_id')
        reps = data.get('reps')
        weight = data.get('weight')
        
        log = get_object_or_404(WorkoutLog, id=log_id)
        
        # Check permissions: does this log belong to the user?
        user = log.session.user if log.session else log.user
        if user != request.user:
            return JsonResponse({'status': 'error', 'message': 'Forbidden'}, status=403)
            
        if reps is not None:
            log.repetitions = max(0, int(reps))
        if weight is not None:
            log.weight = max(0.0, float(weight))
            
        log.save()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Error in update_log_ajax for user {request.user.id}: {e}")
        return JsonResponse({'status': 'error', 'message': 'An error occurred while updating the log.'}, status=400)


