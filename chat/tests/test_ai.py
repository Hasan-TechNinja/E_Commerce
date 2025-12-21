from django.test import TestCase
from unittest.mock import patch, MagicMock
import sys

# Mock openai and dotenv module before importing chat.ai
mock_openai = MagicMock()
sys.modules['openai'] = mock_openai
sys.modules['dotenv'] = MagicMock()

from chat.ai import get_ai_reply
from django.contrib.auth.models import User
from shop.models import Product, Type

class AIChatTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.type = Type.objects.create(name='Test Type')
        Product.objects.create(
            name='Test Product',
            initial_price=100.00,
            discounted_price=90.00,
            description='Test Description',
            size='M',
            category='Merchandise',
            type=self.type
        )

    def test_get_ai_reply_success(self):
        # Setup the mock for 'o' which is now our mock_openai.OpenAI()
        # In chat.ai: o = OpenAI(...) -> o is a mock instance
        
        # We need to access the 'o' object in chat.ai
        import chat.ai
        mock_o = chat.ai.o
        
        # Mock the chain: o.chat.completions.create
        mock_create = mock_o.chat.completions.create
        
        # Mock OpenAI response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"ai_response": "Hello! How can I help you with Test Product?"}'))
        ]
        mock_create.return_value = mock_response

        reply = get_ai_reply("Hello", user=self.user)
        
        self.assertEqual(reply, "Hello! How can I help you with Test Product?")
        
        # Verify OpenAI was called with correct system message containing product info
        args, kwargs = mock_create.call_args
        messages = kwargs['messages']
        system_content = messages[0]['content']
        self.assertIn("Test Product", system_content)
        self.assertIn("$90.00", system_content)

    def test_get_ai_reply_json_error(self):
        import chat.ai
        mock_o = chat.ai.o
        mock_create = mock_o.chat.completions.create
        
        # Mock invalid JSON response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='Not JSON'))
        ]
        mock_create.return_value = mock_response

        reply = get_ai_reply("Hello", user=self.user)
        
        # Should return raw content if JSON parse fails
        self.assertEqual(reply, "Not JSON")
