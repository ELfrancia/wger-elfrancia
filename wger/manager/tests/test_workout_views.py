# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.urls import reverse
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.models import Day, WorkoutSession, WorkoutLog, SlotEntry, Slot

class WorkoutViewsTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.get(username='test')
        self.client.force_login(self.user)
        self.day = Day.objects.get(pk=1)
        self.routine = self.day.routine
        # Ensure routine belongs to the logged in user
        self.routine.user = self.user
        self.routine.save()

    def test_log_tailwind_get(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('completed_exercise_ids', response.context)
        # Initially, no exercises are completed
        self.assertEqual(len(response.context['completed_exercise_ids']), 0)

    def test_log_tailwind_post_complete_exercise(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id

        # POST to complete exercise
        response = self.client.post(url, {'action': 'complete_exercise', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        
        # Verify logs were created for slot entries matching exercise_id
        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day).first()
        self.assertIsNotNone(session)
        target_entries = slot.entries.filter(exercise_id=exercise_id)
        slot_entry_ids = [e.id for e in target_entries]
        logs_count = session.logs.filter(slot_entry_id__in=slot_entry_ids).count()
        self.assertEqual(logs_count, target_entries.count())

        # POST again to uncheck/delete logs
        response = self.client.post(url, {'action': 'complete_exercise', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        logs_count = session.logs.filter(slot_entry_id__in=slot_entry_ids).count()
        self.assertEqual(logs_count, 0)

    def test_log_tailwind_post_add_and_delete_set_config(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id
        initial_count = slot.entries.count()

        # POST to add set
        response = self.client.post(url, {'action': 'add_set', 'exercise_id': exercise_id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(slot.entries.count(), initial_count + 1)

        # Get the newly created slot entry
        new_entry = slot.entries.order_by('-order').first()

        # POST to delete set configuration (not the last one)
        response = self.client.post(url, {'action': 'delete_set_config', 'slot_entry_id': new_entry.id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(slot.entries.count(), initial_count)

        # Let's delete all but one, and then delete the last one
        for entry in list(slot.entries.all())[1:]:
            entry.delete()
        self.assertEqual(slot.entries.count(), 1)
        last_entry = slot.entries.first()

        # Deleting the last slot entry should delete the slot and return empty string
        response = self.client.post(url, {'action': 'delete_set_config', 'slot_entry_id': last_entry.id}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'')
        self.assertFalse(Slot.objects.filter(id=slot.id).exists())

    def test_log_tailwind_post_delete_set(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        slot = self.day.slots.first()
        exercise_id = slot.obj.id
        slot_entry = slot.entries.first()

        # First, log a set
        response = self.client.post(url, {
            'exercise_id': exercise_id,
            'slot_entry_id': slot_entry.id,
            'repetitions': 10,
            'weight': 50
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)

        session = WorkoutSession.objects.get(user=self.user, routine=self.routine, day=self.day)
        self.assertTrue(session.logs.filter(slot_entry_id=slot_entry.id).exists())

        # Now delete it using delete_set
        response = self.client.post(url, {
            'action': 'delete_set',
            'slot_entry_id': slot_entry.id,
            'exercise_id': exercise_id
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(session.logs.filter(slot_entry_id=slot_entry.id).exists())

    def test_upload_condition_photo(self):
        import io
        from PIL import Image as PILImage
        from django.core.files.uploadedfile import SimpleUploadedFile
        from wger.gallery.models.image import Image
        import datetime

        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})
        
        # Create a valid PNG image in memory
        img_bytes = io.BytesIO()
        PILImage.new('RGB', (100, 100), color='red').save(img_bytes, format='PNG')
        img_bytes.seek(0)
        uploaded_file = SimpleUploadedFile('test_photo.png', img_bytes.read(), content_type='image/png')

        response = self.client.post(url, {
            'action': 'upload_condition_photo',
            'image': uploaded_file,
            'description': 'Test foto condizione post-workout'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertEqual(json_data['status'], 'ok')
        self.assertGreaterEqual(json_data['photos_count'], 1)

        # Verify image object created in gallery
        gallery_img = Image.objects.filter(user=self.user, date=datetime.date.today()).first()
        self.assertIsNotNone(gallery_img)
        self.assertIn('Test foto condizione', gallery_img.description)

    def test_server_side_draft_lookup_24h(self):
        import datetime
        from django.utils import timezone
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})

        # 1. Create an active session created within the last 24h
        session_24h = WorkoutSession.objects.create(
            user=self.user,
            routine=self.routine,
            day=self.day,
            date=datetime.date.today(),
            time_start=timezone.localtime(timezone.now()).time(),
            status='active'
        )

        # GET request should load this existing active session as context session
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['session'].id, session_24h.id)

        # 2. Test old active session (> 24h ago)
        session_24h.date = datetime.date.today() - datetime.timedelta(days=2)
        session_24h.save()

        # Clear active session key in Django session to simulate return after login on another device
        session_key = f'active_session_{self.day.pk}'
        if session_key in self.client.session:
            del self.client.session[session_key]

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should create a new active session draft instead of using >24h old session
        self.assertNotEqual(response.context['session'].id, session_24h.id)
        self.assertEqual(response.context['session'].status, 'active')

    def test_finish_and_discard_workout_actions(self):
        url = reverse('manager:day:overview', kwargs={'routine_pk': self.routine.pk, 'day_pk': self.day.pk})

        # Start/Load session
        self.client.get(url)
        session = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').first()
        self.assertIsNotNone(session)

        # Test finish workout action
        response = self.client.post(url, {'action': 'finish_workout'})
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, 'finished')
        self.assertIsNotNone(session.time_end)

        # Create new active session and test discard workout action
        self.client.get(url)
        session_new = WorkoutSession.objects.filter(user=self.user, routine=self.routine, day=self.day, status='active').first()
        self.assertIsNotNone(session_new)

        response = self.client.post(url, {'action': 'discard_workout'})
        self.assertEqual(response.status_code, 302)
        session_new.refresh_from_db()
        self.assertEqual(session_new.status, 'interrupted')
        self.assertEqual(session_new.logs.count(), 0)


