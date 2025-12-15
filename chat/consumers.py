# chat/consumers.py

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import ChatMessage
from .ai import get_ai_reply


class ChatConsumer(AsyncWebsocketConsumer):

    # -----------------------------
    # WebSocket lifecycle
    # -----------------------------

    async def connect(self):
        self.user = self.scope.get("user")

        if not self.user or self.user.is_anonymous:
            await self.close()
            return

        # Each user has their own room
        self.room_group_name = f"user_{self.user.id}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # -----------------------------
    # Message handling
    # -----------------------------

    async def receive(self, text_data):
        """
        Expected payload:
        {
            "message": "Hello"
        }
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        user_message = data.get("message")
        if not user_message:
            return

        # 1️⃣ Save user message
        await self.save_message(
            sender_type="user",
            sender_name=self.user.username,
            message=user_message
        )

        # 2️⃣ Get AI response (from ai.py)
        ai_response = await self.get_ai_response(user_message)

        # 3️⃣ Save AI message
        await self.save_message(
            sender_type="ai",
            sender_name="AI",
            message=ai_response
        )

        # 4️⃣ Send both messages to frontend
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "messages": [
                    {
                        "sender": self.user.username,
                        "type": "user",
                        "message": user_message
                    },
                    {
                        "sender": "AI",
                        "type": "ai",
                        "message": ai_response
                    }
                ]
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    # -----------------------------
    # AI integration
    # -----------------------------

    async def get_ai_response(self, message: str) -> str:
        """
        Async-safe wrapper for ai.py
        """
        return await self.run_ai(message)

    @database_sync_to_async
    def run_ai(self, message: str) -> str:
        return get_ai_reply(message)

    # -----------------------------
    # Database helpers
    # -----------------------------

    @database_sync_to_async
    def save_message(self, sender_type: str, sender_name: str, message: str):
        ChatMessage.objects.create(
            user=self.user,
            sender_type=sender_type,
            sender_name=sender_name,
            message=message
        )
