from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from django.contrib.auth.models import User
from .models import PasswordResetCode

class LoginTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.login_url = reverse('login')
        self.user_data = {
            'username': 'testuser@example.com',
            'email': 'testuser@example.com',
            'password': 'testpassword123',
            'first_name': 'Test',
            'last_name': 'User'
        }
        self.user = User.objects.create_user(**self.user_data)
        self.user.is_active = True
        self.user.save()

    def test_login_success(self):
        data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_login_invalid_credentials(self):
        data = {
            'email': self.user_data['email'],
            'password': 'wrongpassword'
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Invalid credentials.')

    def test_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        data = {
            'email': self.user_data['email'],
            'password': self.user_data['password']
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data['error'], 'Please verify your email first.')

    def test_login_missing_fields(self):
        data = {
            'email': self.user_data['email']
        }
        response = self.client.post(self.login_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Email and password required!')

class ForgetPasswordTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('forget-password')
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='testpassword123'
        )

    def test_forget_password_success(self):
        data = {'email': 'testuser@example.com'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Password reset code send successfully!')

    def test_forget_password_invalid_email(self):
        data = {'email': 'nonexistent@example.com'}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error'], 'User does not exist!')

    def test_forget_password_missing_email(self):
        data = {}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Email is required')

class PasswordResetFlowTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.verify_url = reverse('verify-pass-code')
        self.reset_url = reverse('set-new-password')
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='oldpassword123'
        )
        self.reset_code = PasswordResetCode.objects.create(
            user=self.user,
            code='1234'
        )

    def test_verify_code_success(self):
        data = {'email': self.user.email, 'code': '1234'}
        response = self.client.post(self.verify_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Code verified successfully')

    def test_verify_code_invalid(self):
        data = {'email': self.user.email, 'code': '0000'}
        response = self.client.post(self.verify_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Invalid code')

    def test_set_new_password_success(self):
        data = {
            'email': self.user.email,
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }
        response = self.client.post(self.reset_url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Password reset successfully')
        
        # Verify password changed
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword123'))
        
        # Verify code deleted (optional cleanup)
        self.assertFalse(PasswordResetCode.objects.filter(id=self.reset_code.id).exists())

    def test_set_new_password_mismatch(self):
        data = {
            'email': self.user.email,
            'new_password': 'newpassword123',
            'confirm_password': 'mismatchpassword'
        }
        response = self.client.post(self.reset_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Passwords do not match')

class SocialLoginTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('social-login')
        self.user_data = {
            'email': 'socialuser@example.com',
        }

    def test_social_login_existing_user(self):
        # Create user first
        User.objects.create_user(username='socialuser@example.com', email='socialuser@example.com')
        
        response = self.client.post(self.url, self.user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['email'], 'socialuser@example.com')

    def test_social_login_new_user(self):
        response = self.client.post(self.url, self.user_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['email'], 'socialuser@example.com')
        
        # Verify user created
        self.assertTrue(User.objects.filter(email='socialuser@example.com').exists())
        user = User.objects.get(email='socialuser@example.com')
        self.assertTrue(user.is_active)

    def test_social_login_missing_email(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Email is required!')


class ChangePasswordTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = reverse('change-password')
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='oldpassword123'
        )
        self.client.force_authenticate(user=self.user)

    def test_change_password_success(self):
        data = {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Password changed successfully.')
        
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newpassword123'))

    def test_change_password_incorrect_old_password(self):
        data = {
            'old_password': 'wrongpassword',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Incorrect old password.')

    def test_change_password_mismatch(self):
        data = {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword123',
            'confirm_password': 'mismatchpassword'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['new_password'][0], 'Passwords do not match')

    def test_change_password_unauthenticated(self):
        self.client.logout()
        data = {
            'old_password': 'oldpassword123',
            'new_password': 'newpassword123',
            'confirm_password': 'newpassword123'
        }
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
