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

# Django
from django.urls import reverse

# wger
from wger.core.tests.base_testcase import WgerTestCase


logger = logging.getLogger(__name__)


class WeightOverviewTestCase(WgerTestCase):
    """
    Test case for the weight overview page
    """

    def weight_overview(self):
        """
        Helper function to test the weight overview page
        """
        response = self.client.get(reverse('weight:overview'))
        self.assertEqual(response.status_code, 200)

    def test_daily_summary_only_shows_finished_sessions(self):
        """
        Interrupted / discarded / active sessions and their logs must not appear
        in the "resoconto allenamenti del giorno" section.
        """
        import datetime

        from django.contrib.auth.models import User

        from wger.manager.models import Day, WorkoutSession, WorkoutLog

        user = User.objects.get(username='test')
        self.client.force_login(user)

        day = Day.objects.get(pk=1)
        routine = day.routine
        routine.user = user
        routine.save()

        slot = day.slots.first()
        slot_entry = slot.entries.first()
        today = datetime.date.today()

        finished = WorkoutSession.objects.create(
            user=user, routine=routine, day=day, date=today,
            time_start=datetime.time(10, 0), time_end=datetime.time(11, 0),
            status='finished',
        )
        WorkoutLog.objects.create(
            user=user, session=finished, routine=routine, exercise=slot.obj,
            slot_entry=slot_entry, repetitions=10, weight=50, date=today,
        )

        interrupted = WorkoutSession.objects.create(
            user=user, routine=routine, day=day, date=today,
            time_start=datetime.time(12, 0), status='interrupted',
        )
        WorkoutLog.objects.create(
            user=user, session=interrupted, routine=routine, exercise=slot.obj,
            slot_entry=slot_entry, repetitions=99, weight=999, date=today,
        )

        response = self.client.get(
            reverse('weight:overview'), {'selected_date': today.strftime('%Y-%m-%d')}
        )
        self.assertEqual(response.status_code, 200)
        session_ids = {se['session_id'] for se in response.context['session_exercises']}
        self.assertIn(finished.id, session_ids)
        self.assertNotIn(interrupted.id, session_ids)

    def test_weight_overview_loged_in(self):
        """
        Test the weight overview page by a logged in user
        """
        self.user_login('test')
        self.weight_overview()


class WeightExportCsvTestCase(WgerTestCase):
    """
    Tests exporting the saved weight entries as a CSV file
    """

    def csv_export(self):
        """
        Helper function to test exporting the saved weight entries as a CSV file
        """
        response = self.client.get(reverse('weight:export-csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertGreaterEqual(len(response.content), 150)
        self.assertLessEqual(len(response.content), 300)

    def test_csv_export_loged_in(self):
        """
        Test exporting the saved weight entries as a CSV file by a logged in user
        """
        self.user_login('test')
        self.csv_export()
