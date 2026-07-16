# Django
from django.urls import reverse
from django.contrib.auth.models import User
from decimal import Decimal

# wger
from wger.core.models import DailyActivity
from wger.core.tests.base_testcase import WgerTestCase


class DailyActivityTestCase(WgerTestCase):
    """
    Test daily activity model, dashboard integration, and log endpoint
    """

    def setUp(self):
        super().setUp()
        self.user_login('member1')
        self.user = User.objects.get(username='member1')

    def test_daily_activity_defaults(self):
        """
        Verify DailyActivity properties/defaults
        """
        activity = DailyActivity.objects.create(
            user=self.user,
            steps=1000,
            calories=150,
            water=Decimal('0.75')
        )
        self.assertEqual(activity.steps, 1000)
        self.assertEqual(activity.calories, 150)
        self.assertEqual(activity.water, Decimal('0.75'))
        self.assertEqual(str(activity), f'{self.user.username} - {activity.date}')

    def test_log_daily_activity_view(self):
        """
        Test the log_daily_activity POST view via HTMX simulation
        """
        # Incremental steps
        response = self.client.post(
            reverse('core:user:log-daily-activity'),
            {'activity_type': 'steps', 'amount': '2500'}
        )
        self.assertEqual(response.status_code, 200)
        activity = DailyActivity.objects.get(user=self.user)
        self.assertEqual(activity.steps, 2500)

        # Direct values setting
        response = self.client.post(
            reverse('core:user:log-daily-activity'),
            {'activity_type': 'steps', 'value': '8000'}
        )
        activity.refresh_from_db()
        self.assertEqual(activity.steps, 8000)

        # Water increment
        response = self.client.post(
            reverse('core:user:log-daily-activity'),
            {'activity_type': 'water', 'amount': '0.5'}
        )
        activity.refresh_from_db()
        self.assertEqual(activity.water, Decimal('0.5'))

        # Water direct value
        response = self.client.post(
            reverse('core:user:log-daily-activity'),
            {'activity_type': 'water', 'value': '2.25'}
        )
        activity.refresh_from_db()
        self.assertEqual(activity.water, Decimal('2.25'))

        # Calories increment
        response = self.client.post(
            reverse('core:user:log-daily-activity'),
            {'activity_type': 'calories', 'amount': '300'}
        )
        activity.refresh_from_db()
        self.assertEqual(activity.calories, 300)

    def test_profile_goals_update(self):
        """
        Verify updating goals in user profile
        """
        profile = self.user.userprofile
        self.assertEqual(profile.steps_goal, 16000) # Check default
        
        response = self.client.post(
            reverse('core:profile_tailwind'),
            {
                'steps_goal': '12000',
                'calories_goal': '750',
                'water_goal': '3.0'
            }
        )
        self.assertEqual(response.status_code, 302) # Redirect to profile
        profile.refresh_from_db()
        self.assertEqual(profile.steps_goal, 12000)
        self.assertEqual(profile.calories_goal, 750)
        self.assertEqual(profile.water_goal, Decimal('3.0'))
