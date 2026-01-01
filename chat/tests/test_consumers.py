from django.test import TransactionTestCase, override_settings
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from chat.consumers import ChatConsumer
from django.contrib.auth import get_user_model
from chat.models import ChatMessage
from rest_framework_simplejwt.tokens import AccessToken


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
})
class ChatConsumerTest(TransactionTestCase):
    def setUp(self):
        self.User = get_user_model()

    def test_anonymous_chat_not_saved(self):
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/")
        connected, _ = async_to_sync(communicator.connect)()
        self.assertTrue(connected)

        async_to_sync(communicator.send_json_to)({"message": "Hello guest"})
        event = async_to_sync(communicator.receive_json_from)()
        # Should receive messages (user + ai)
        self.assertIn("messages", event)
        async_to_sync(communicator.disconnect)()

        # Nothing persisted for anonymous
        self.assertEqual(ChatMessage.objects.count(), 0)

    def test_authenticated_chat_saved(self):
        user = self.User.objects.create_user(username="tester", email="t@e.com", password="pass")
        token = str(AccessToken.for_user(user))

        path = f"/ws/chat/?token={token}"
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), path)
        connected, _ = async_to_sync(communicator.connect)()
        self.assertTrue(connected)

        async_to_sync(communicator.send_json_to)({"message": "Hello auth"})
        event = async_to_sync(communicator.receive_json_from)()
        self.assertIn("messages", event)
        async_to_sync(communicator.disconnect)()

        # Two messages should be saved: the user message and the AI reply
        msgs = ChatMessage.objects.filter(user=user)
        self.assertEqual(msgs.count(), 2)
