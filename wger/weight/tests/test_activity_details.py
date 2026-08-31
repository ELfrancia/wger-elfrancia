# -*- coding: utf-8 -*-
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from wger.core.tests.base_testcase import WgerTestCase
from wger.core.models import DailyActivity

class ActivityDetailsTestCase(WgerTestCase):
    """
    Test case per l'endpoint dei dettagli dell'attività giornaliera
    """

    def setUp(self):
        super().setUp()
        self.user_login('member1')
        self.user = User.objects.get(username='member1')

    def test_get_activity_details_default(self):
        """Testa la GET senza parametri (data odierna)"""
        response = self.client.get(reverse('weight:activity-details'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activity Calendar')
        self.assertFalse(DailyActivity.objects.filter(user=self.user, date=timezone.localdate()).exists())

    def test_get_activity_details_specific_date(self):
        """Testa la GET con una data specifica"""
        selected_date = '2026-07-16'
        response = self.client.get(reverse('weight:activity-details'), {'date': selected_date})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, selected_date)
        self.assertFalse(DailyActivity.objects.filter(user=self.user, date=selected_date).exists())

    def test_get_weight_overview_does_not_create_activity(self):
        """Testa che la GET su weight overview non crei DailyActivity su DB"""
        selected_date = '2026-07-17'
        response = self.client.get(reverse('weight:overview'), {'selected_date': selected_date})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DailyActivity.objects.filter(user=self.user, date=selected_date).exists())

    def test_post_log_activity_steps(self):
        """Testa la POST per loggare i passi su una data specifica"""
        selected_date = '2026-07-16'
        # Log iniziale
        response = self.client.post(
            reverse('weight:activity-details'),
            {
                'date': selected_date,
                'activity_type': 'steps',
                'amount': '1000'
            }
        )
        self.assertEqual(response.status_code, 200)
        activity = DailyActivity.objects.get(user=self.user, date=selected_date)
        self.assertEqual(activity.steps, 1000)
