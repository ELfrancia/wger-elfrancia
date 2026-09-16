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
from decimal import Decimal

# Django
from django.contrib.auth.models import User
from django.urls import reverse

# wger
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import (
    Day,
    Slot,
    SlotEntry,
)


class AddSetTestCase(WgerTestCase):
    """
    "Add set" is reachable from two different pages, each hitting a different
    view. Both have to actually create the SlotEntry and answer htmx in a way
    the client can act on.
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

        self.slot = self.day.slots.first()
        self.assertIsNotNone(self.slot)
        self.exercise = self.slot.obj

        self.client.force_login(self.user)

        self.url = reverse(
            'manager:routine:add-set',
            kwargs={
                'routine_pk': self.routine.pk,
                'day_pk': self.day.pk,
                'slot_pk': self.slot.pk,
            },
        )

    #
    # Routine page: manager:routine:add-set
    #

    def test_add_set_with_explicit_exercise(self):
        """The superset form posts an explicit exercise_id"""
        initial = self.slot.entries.count()
        response = self.client.post(
            self.url,
            {'reps': '8', 'weight': '42.5', 'exercise_id': self.exercise.id},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.slot.entries.count(), initial + 1)

        entry = self.slot.entries.order_by('-order').first()
        self.assertEqual(entry.exercise_id, self.exercise.id)
        self.assertEqual(entry.reps_config.reps, 8)
        self.assertEqual(entry.weight_config.weight, Decimal('42.5'))

    def test_add_set_without_exercise_id_falls_back_to_slot_exercise(self):
        """The plain (non superset) form posts no exercise_id at all"""
        initial = self.slot.entries.count()
        response = self.client.post(
            self.url,
            {'reps': '12', 'weight': ''},
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.slot.entries.count(), initial + 1)

        entry = self.slot.entries.order_by('-order').first()
        self.assertEqual(entry.exercise_id, self.exercise.id)
        self.assertEqual(entry.weight_config.weight, 0)

    def test_add_set_accepts_comma_decimal_weight(self):
        self.client.post(
            self.url,
            {'reps': '10', 'weight': '12,5'},
            HTTP_HX_REQUEST='true',
        )
        entry = self.slot.entries.order_by('-order').first()
        self.assertEqual(entry.weight_config.weight, Decimal('12.5'))

    def test_add_set_htmx_response_is_actionable(self):
        """
        htmx silently ignores an empty 200 with no swap instruction: the
        response has to either carry a fragment or tell the client to reload.
        """
        response = self.client.post(
            self.url,
            {'reps': '10', 'weight': '20'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.has_header('HX-Redirect') or response.content.strip(),
            'htmx response carries neither a fragment nor HX-Redirect',
        )

    def test_add_set_requires_post(self):
        initial = self.slot.entries.count()
        response = self.client.get(self.url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.slot.entries.count(), initial)

    def test_add_set_requires_reps(self):
        """A missing/invalid reps value must not silently create a broken set"""
        initial = self.slot.entries.count()
        response = self.client.post(self.url, {'weight': '20'}, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.slot.entries.count(), initial)

    def test_add_set_empty_slot_reports_error(self):
        """
        A slot without entries has no exercise to fall back to. That used to be
        a silent no-op answered with a 200.
        """
        empty_slot = Slot.objects.create(day=self.day, order=99)
        url = reverse(
            'manager:routine:add-set',
            kwargs={
                'routine_pk': self.routine.pk,
                'day_pk': self.day.pk,
                'slot_pk': empty_slot.pk,
            },
        )
        response = self.client.post(url, {'reps': '10'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 422)
        self.assertEqual(empty_slot.entries.count(), 0)

    def test_add_set_other_user_forbidden(self):
        self.client.force_login(User.objects.get(username='admin'))
        initial = self.slot.entries.count()
        response = self.client.post(
            self.url,
            {'reps': '10', 'weight': '20'},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.slot.entries.count(), initial)

    def test_add_set_requires_login(self):
        self.client.logout()
        response = self.client.post(self.url, {'reps': '10'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response['Location'])

    #
    # Workout page: manager:day:overview with action=add_set
    #

    def test_add_set_from_workout_page_returns_card_fragment(self):
        url = reverse(
            'manager:day:overview',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )
        initial = self.slot.entries.count()
        response = self.client.post(
            url,
            {
                'action': 'add_set',
                'slot_id': self.slot.pk,
                'exercise_id': self.exercise.id,
                'reps': '9',
                'weight': '30',
            },
            HTTP_HX_REQUEST='true',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.slot.entries.count(), initial + 1)

        # The swapped fragment must be the card htmx is targeting
        self.assertIn(
            f'id="exercise-card-{self.slot.pk}"'.encode(),
            response.content,
        )

        new_entry = SlotEntry.objects.order_by('-id').first()
        self.assertEqual(new_entry.slot_id, self.slot.pk)
        self.assertEqual(new_entry.reps_config.reps, 9)

    def test_add_set_preserves_decimal_reps(self):
        """
        The reps field doubles as seconds in timed-set mode, so "12,5" must be
        stored as 12.5 - not truncated to 12, and certainly not replaced by 10.
        """
        for raw, expected in (('12,5', Decimal('12.50')), ('12.5', Decimal('12.50'))):
            with self.subTest(raw=raw):
                self.client.post(self.url, {'reps': raw, 'weight': '20'}, HTTP_HX_REQUEST='true')
                entry = self.slot.entries.order_by('-order').first()
                self.assertEqual(entry.reps_config.reps, expected)

    def test_add_set_from_workout_page_preserves_decimal_reps(self):
        url = reverse(
            'manager:day:overview',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )
        self.client.post(
            url,
            {
                'action': 'add_set',
                'slot_id': self.slot.pk,
                'exercise_id': self.exercise.id,
                'reps': '12,5',
                'weight': '20',
            },
            HTTP_HX_REQUEST='true',
        )
        entry = self.slot.entries.order_by('-order').first()
        self.assertEqual(entry.reps_config.reps, Decimal('12.50'))

    def test_add_set_from_workout_page_rejects_invalid_reps(self):
        """
        A reps value the user typed is never silently swapped for another one.
        """
        url = reverse(
            'manager:day:overview',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )
        initial = self.slot.entries.count()
        response = self.client.post(
            url,
            {
                'action': 'add_set',
                'slot_id': self.slot.pk,
                'exercise_id': self.exercise.id,
                'reps': 'abc',
            },
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('onyx:set-error', response['HX-Trigger'])
        self.assertEqual(self.slot.entries.count(), initial)

    def test_add_set_from_workout_page_without_reps_repeats_last_set(self):
        """No reps posted at all is the bare "+ set" affordance, not an error."""
        url = reverse(
            'manager:day:overview',
            kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk},
        )
        last = self.slot.entries.order_by('-order').first()
        expected = last.reps_config.reps
        initial = self.slot.entries.count()

        response = self.client.post(
            url,
            {'action': 'add_set', 'slot_id': self.slot.pk, 'exercise_id': self.exercise.id},
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.slot.entries.count(), initial + 1)
        self.assertEqual(self.slot.entries.order_by('-order').first().reps_config.reps, expected)
