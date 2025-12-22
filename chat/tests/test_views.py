# chat/tests/test_views.py

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from chat.models import ChatMessage

User = get_user_model()


class ChatHistoryViewTest(TestCase):
    """Test cases for the ChatHistoryView API endpoint"""

    def setUp(self):
        """Set up test client and create test user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.url = '/chat/history/'

    def test_chat_history_requires_authentication(self):
        """Test that the endpoint requires authentication"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_empty_chat_history(self):
        """Test getting chat history when there are no messages"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(len(response.data['messages']), 0)

    def test_get_chat_history_with_messages(self):
        """Test getting chat history with existing messages"""
        # Create test messages
        ChatMessage.objects.create(
            user=self.user,
            sender_type='user',
            sender_name='testuser',
            message='Hello AI'
        )
        ChatMessage.objects.create(
            user=self.user,
            sender_type='ai',
            sender_name='AI',
            message='Hello! How can I help you?'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['count'], 2)
        self.assertEqual(len(response.data['messages']), 2)
        
        # Check message order (should be chronological)
        messages = response.data['messages']
        self.assertEqual(messages[0]['sender_type'], 'user')
        self.assertEqual(messages[0]['message'], 'Hello AI')
        self.assertEqual(messages[1]['sender_type'], 'ai')
        self.assertEqual(messages[1]['message'], 'Hello! How can I help you?')

    def test_user_only_sees_own_messages(self):
        """Test that users only see their own chat messages"""
        # Create another user with messages
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@example.com',
            password='otherpass123'
        )
        ChatMessage.objects.create(
            user=other_user,
            sender_type='user',
            sender_name='otheruser',
            message='Other user message'
        )
        
        # Create message for test user
        ChatMessage.objects.create(
            user=self.user,
            sender_type='user',
            sender_name='testuser',
            message='My message'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['messages'][0]['message'], 'My message')

    def test_response_structure(self):
        """Test that the response has the correct structure"""
        ChatMessage.objects.create(
            user=self.user,
            sender_type='user',
            sender_name='testuser',
            message='Test message'
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        
        # Check response structure
        self.assertIn('success', response.data)
        self.assertIn('count', response.data)
        self.assertIn('messages', response.data)
        
        # Check message structure
        message = response.data['messages'][0]
        self.assertIn('id', message)
        self.assertIn('sender_type', message)
        self.assertIn('sender_name', message)
        self.assertIn('message', message)
        self.assertIn('created_at', message)


class ChatbotPageViewTest(TestCase):
    """Test cases for the ChatbotPageView"""

    def setUp(self):
        """Set up test client"""
        self.client = APIClient()
        self.url = '/chat/'

    def test_chatbot_page_accessible(self):
        """Test that the chatbot page is accessible"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'chat/chatbot.html')
