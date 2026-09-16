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
import datetime
import json

# Django
from django.contrib.auth.models import User
from django.urls import reverse

# wger
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import (
    Day,
    Routine,
)


class RenameViewsTestCase(WgerTestCase):
    """
    Tests for manager:routine:rename and manager:day:rename
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        self.routine.user = self.user
        self.routine.save()

        profile = self.user.userprofile
        profile.onboarding_completed = True
        profile.save()

        self.routine_url = reverse('manager:routine:rename', kwargs={'pk': self.routine.pk})
        self.day_url = reverse(
            'manager:day:rename',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )

    #
    # Routine
    #

    def test_rename_routine_requires_login(self):
        response = self.client.post(self.routine_url, {'name': 'Nope'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    def test_rename_routine_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.routine_url).status_code, 405)

    def test_rename_routine_htmx(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.routine_url,
            {'name': 'Push Pull Legs'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'Push Pull Legs')

        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, 'Push Pull Legs')

        trigger = json.loads(response['HX-Trigger'])
        self.assertEqual(
            trigger['onyx:routine-renamed'],
            {'id': self.routine.pk, 'name': 'Push Pull Legs'},
        )

    def test_rename_routine_escapes_html(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.routine_url,
            {'name': '<script>x</script>'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'<script>', response.content)

    def test_rename_routine_strips_whitespace(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.routine_url,
            {'name': '   Upper   '},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, 'Upper')

    def test_rename_routine_rejects_empty_name(self):
        self.client.force_login(self.user)
        original = self.routine.name
        response = self.client.post(self.routine_url, {'name': '   '}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 422)
        self.assertIn('onyx:rename-error', json.loads(response['HX-Trigger']))
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, original)

    def test_rename_routine_rejects_too_long_name(self):
        self.client.force_login(self.user)
        original = self.routine.name
        response = self.client.post(self.routine_url, {'name': 'x' * 26}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 422)
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, original)

    def test_rename_routine_non_htmx_redirects(self):
        self.client.force_login(self.user)
        response = self.client.post(self.routine_url, {'name': 'Classic post'})
        self.assertEqual(response.status_code, 302)
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, 'Classic post')

    def test_rename_routine_other_user_forbidden(self):
        """A routine that isn't ours must not even be found"""
        self.client.force_login(User.objects.get(username='admin'))
        original = self.routine.name
        response = self.client.post(self.routine_url, {'name': 'Stolen'}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 404)
        self.routine.refresh_from_db()
        self.assertEqual(self.routine.name, original)

    #
    # Day
    #

    def test_rename_day_requires_login(self):
        response = self.client.post(self.day_url, {'name': 'Nope'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    def test_rename_day_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.day_url).status_code, 405)

    def test_rename_day_htmx(self):
        self.client.force_login(self.user)
        response = self.client.post(self.day_url, {'name': 'Upper A'}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode(), 'Upper A')

        self.day.refresh_from_db()
        self.assertEqual(self.day.name, 'Upper A')

        trigger = json.loads(response['HX-Trigger'])
        self.assertEqual(trigger['onyx:day-renamed'], {'id': self.day.pk, 'name': 'Upper A'})

    def test_rename_day_rejects_empty_name(self):
        self.client.force_login(self.user)
        original = self.day.name
        response = self.client.post(self.day_url, {'name': ''}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 422)
        self.day.refresh_from_db()
        self.assertEqual(self.day.name, original)

    def test_rename_day_rejects_too_long_name(self):
        self.client.force_login(self.user)
        original = self.day.name
        response = self.client.post(self.day_url, {'name': 'y' * 21}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 422)
        self.day.refresh_from_db()
        self.assertEqual(self.day.name, original)

    def test_rename_day_other_user_forbidden(self):
        self.client.force_login(User.objects.get(username='admin'))
        original = self.day.name
        response = self.client.post(self.day_url, {'name': 'Stolen'}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 404)
        self.day.refresh_from_db()
        self.assertEqual(self.day.name, original)

    def test_rename_day_wrong_routine_forbidden(self):
        """day_pk must actually belong to routine_pk"""
        self.client.force_login(self.user)
        other_routine = Routine.objects.create(
            user=self.user,
            name='Other',
            start=datetime.date.today(),
            end=datetime.date.today() + datetime.timedelta(weeks=4),
        )
        other_day = Day.objects.create(routine=other_routine, name='Foreign day', order=1)
        url = reverse(
            'manager:day:rename',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': other_day.pk},
        )
        response = self.client.post(url, {'name': 'Mismatch'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 404)
