from django.contrib.auth.models import User
from django.urls import reverse
from wger.core.tests.base_testcase import WgerTestCase

class AdminUserCreationTestCase(WgerTestCase):
    def setUp(self):
        super().setUp()
        # WgerTestCase loads test-user-data.json where admin is is_superuser=False by default.
        # Fetch the admin user and ensure they are a superuser for these tests.
        self.admin = User.objects.get(username='admin')
        self.admin.is_superuser = True
        self.admin.save()

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
        self.user_logout()

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
        self.assertEqual(new_user.first_name, 'New')
        self.assertEqual(new_user.last_name, 'User')
        self.assertEqual(new_user.email, 'newuser123@example.com')
        self.assertTrue(new_user.userprofile.needs_password_change)
        
        # Verify allauth EmailAddress is created
        from allauth.account.models import EmailAddress
        email_addr = EmailAddress.objects.get(user=new_user)
        self.assertEqual(email_addr.email, 'newuser123@example.com')
        self.assertTrue(email_addr.verified)
        self.assertTrue(email_addr.primary)
        
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
        self.assertRedirects(response, reverse('core:dashboard'))
        
        # Verify flag is cleared
        user.refresh_from_db()
        self.assertFalse(user.userprofile.needs_password_change)

    def test_forced_password_change_middleware_api(self):
        # Create user with needs_password_change=True
        user = User.objects.create_user(
            username='tempuser_api',
            email='temp_api@example.com',
            password='TempPassword123'
        )
        user.userprofile.needs_password_change = True
        user.userprofile.save()

        # Login as tempuser_api
        self.client.login(username='tempuser_api', password='TempPassword123')

        # Non-exempt API endpoint should return 403 with error detail
        response = self.client.get('/api/v2/userprofile/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'detail': 'Password change required.'})

        # Another non-exempt endpoint
        response = self.client.get('/api/v1/exercises/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {'detail': 'Password change required.'})

        # Schema endpoint is exempt
        response = self.client.get('/api/v2/schema')
        self.assertEqual(response.status_code, 200)

        # Clear the flag (simulating password change)
        user.userprofile.needs_password_change = False
        user.userprofile.save()

        response = self.client.get('/api/v2/userprofile/')
        self.assertEqual(response.status_code, 200)

    def test_user_creation_password_validation(self):
        self.user_login('admin')
        post_data = {
            'username': 'weakuser',
            'email': 'weakuser@example.com',
            'first_name': 'Weak',
            'last_name': 'User',
            'password': '123',
        }
        response = self.client.post(reverse('core:user:add-user'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].has_error('password'))
        self.assertFalse(User.objects.filter(username='weakuser').exists())
        self.user_logout()
