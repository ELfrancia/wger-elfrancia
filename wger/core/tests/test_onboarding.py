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
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

# wger
from wger.core.tests.base_testcase import WgerTestCase
from wger.weight.models import WeightEntry


logger = logging.getLogger(__name__)


class OnboardingMiddlewareTestCase(WgerTestCase):
    """
    Tests the OnboardingRequiredMiddleware gate
    """

    def setUp(self):
        super().setUp()
        self.dashboard_url = reverse('core:dashboard')
        self.onboarding_url = reverse('core:onboarding')

    def _set_onboarded(self, username, value):
        profile = User.objects.get(username=username).userprofile
        profile.onboarding_completed = value
        profile.save()

    def test_unonboarded_user_is_redirected(self):
        self._set_onboarded('test', False)
        self.user_login('test')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.onboarding_url, response['Location'])

    def test_onboarded_user_reaches_dashboard(self):
        self._set_onboarded('test', True)
        self.user_login('test')
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_onboarding_page_itself_not_redirected(self):
        self._set_onboarded('test', False)
        self.user_login('test')
        response = self.client.get(self.onboarding_url)
        self.assertEqual(response.status_code, 200)

    def test_api_paths_excluded_for_unonboarded_user(self):
        self._set_onboarded('test', False)
        self.user_login('test')
        response = self.client.get('/api/v2/', HTTP_ACCEPT='application/json')
        self.assertNotEqual(response.status_code, 302)

    def test_anonymous_user_not_affected(self):
        response = self.client.get(self.onboarding_url)
        # login_required kicks in, but not the onboarding redirect
        self.assertEqual(response.status_code, 302)
        self.assertIn('/user/login', response['Location'])


class OnboardingWizardTestCase(WgerTestCase):
    """
    Tests the onboarding wizard view
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('core:onboarding')
        profile = User.objects.get(username='test').userprofile
        profile.onboarding_completed = False
        profile.activity_level = ''
        profile.weight_goal = None
        profile.save()
        self.user_login('test')

    def _profile(self):
        return User.objects.get(username='test').userprofile

    def test_full_submit_persists_data(self):
        response = self.client.post(
            self.url,
            {
                'weight': '82.5',
                'height': '181',
                'activity_level': 'advanced',
                'first_name': 'Franz',
                'last_name': 'Tester',
                'email': 'franz@example.com',
            },
        )
        self.assertRedirects(response, reverse('core:dashboard'))

        profile = self._profile()
        self.assertTrue(profile.onboarding_completed)
        self.assertEqual(profile.height, 181)
        self.assertEqual(profile.activity_level, 'advanced')

        entry = WeightEntry.objects.get(user=profile.user, date=timezone.localdate())
        self.assertEqual(entry.weight, Decimal('82.5'))

        user = profile.user
        self.assertEqual(user.first_name, 'Franz')
        self.assertEqual(user.email, 'franz@example.com')

    def test_skip_completes_without_data(self):
        response = self.client.get(self.url + '?skip=1')
        self.assertRedirects(response, reverse('core:dashboard'))

        profile = self._profile()
        self.assertTrue(profile.onboarding_completed)
        self.assertEqual(profile.height, 180)  # unchanged fixture value
        self.assertFalse(
            WeightEntry.objects.filter(
                user=profile.user, date=timezone.localdate()
            ).exists()
        )

    def test_invalid_values_are_ignored_but_onboarding_completes(self):
        response = self.client.post(
            self.url,
            {'weight': '9', 'height': '10', 'activity_level': 'bogus'},
        )
        self.assertRedirects(response, reverse('core:dashboard'))

        profile = self._profile()
        self.assertTrue(profile.onboarding_completed)
        self.assertEqual(profile.height, 180)
        self.assertEqual(profile.activity_level, '')


class ProfileWeightGoalTestCase(WgerTestCase):
    """
    Tests the personal-data / weight-goal block on the profile page
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('core:profile_tailwind')
        self.user_login('test')

    def _profile(self):
        return User.objects.get(username='test').userprofile

    def test_post_persists_weight_goal(self):
        response = self.client.post(self.url, {'weight_goal': '78'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._profile().weight_goal, Decimal('78'))

    def test_empty_weight_goal_clears_it(self):
        profile = self._profile()
        profile.weight_goal = Decimal('80')
        profile.save()

        self.client.post(self.url, {'weight_goal': ''})
        self.assertIsNone(self._profile().weight_goal)

    def test_page_renders_weight_goal_delta(self):
        profile = self._profile()
        profile.weight_goal = Decimal('70')
        profile.save()
        WeightEntry.objects.update_or_create(
            user=profile.user,
            date=timezone.localdate(),
            defaults={'weight': Decimal('75')},
        )

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['weight_goal_delta'], Decimal('-5.0'))

    def test_post_updates_height(self):
        self.client.post(self.url, {'height': '177'})
        self.assertEqual(self._profile().height, 177)
