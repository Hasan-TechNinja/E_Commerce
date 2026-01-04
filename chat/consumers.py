# chat/consumers.py

import json
from urllib.parse import parse_qs
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from django.core.cache import cache

from .models import ChatMessage
from .ai import get_ai_reply


class ChatConsumer(AsyncWebsocketConsumer):

    # -----------------------------
    # WebSocket lifecycle
    # -----------------------------

    async def connect(self):
        self.user = self.scope.get("user")

        # If user is anonymous, allow guest access. Identify guest by a
        # `guest_id` query param. If not provided, generate one and send it
        # back to the client so they can persist it locally.
        if not self.user or self.user.is_anonymous:
            query = parse_qs(self.scope.get("query_string", b"").decode())
            guest_list = query.get("guest_id")
            if guest_list:
                self.guest_id = guest_list[0]
            else:
                self.guest_id = str(uuid.uuid4())

            # Room per guest
            self.room_group_name = f"guest_{self.guest_id}"

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()

            # Inform the client of their assigned guest_id (if newly generated)
            await self.send(text_data=json.dumps({"type": "guest_id", "guest_id": self.guest_id}))
            return

        # Authenticated user
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

        # 1️⃣ Save user message (persist for authenticated users; cache for guests)
        if self.user and not self.user.is_anonymous:
            sender_name = self.user.username
        else:
            sender_name = f"guest_{getattr(self, 'guest_id', 'unknown')}"

        await self.save_message(
            sender_type="user",
            sender_name=sender_name,
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
                        "sender": sender_name,
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
        # Pass `None` for anonymous/guest users so the AI helper treats them
        # as guests (no user history lookup) instead of receiving an
        # AnonymousUser instance which may be truthy in some contexts.
        user_arg = None
        if hasattr(self, "user") and self.user and not getattr(self.user, "is_anonymous", False):
            user_arg = self.user
        return get_ai_reply(message, user=user_arg)

    # -----------------------------
    # Database helpers
    # -----------------------------

    @database_sync_to_async
    def save_message(self, sender_type: str, sender_name: str, message: str):
        # If authenticated user, persist to DB as before.
        if self.user and not self.user.is_anonymous:
            return ChatMessage.objects.create(
                user=self.user,
                sender_type=sender_type,
                sender_name=sender_name,
                message=message
            )

        # Guest user: store temporarily in cache under a guest-specific key
        guest_id = getattr(self, "guest_id", None)
        if not guest_id:
            return None

        key = f"guest_chat:{guest_id}"
        messages = cache.get(key, [])
        messages.append({
            "sender": sender_name,
            "type": sender_type,
            "message": message,
        })
        # Keep guest messages for 7 days by default
        cache.set(key, messages, timeout=60 * 60 * 24 * 7)
        return None

    @staticmethod
    def get_guest_messages(guest_id: str):
        key = f"guest_chat:{guest_id}"
        return cache.get(key, [])

    @staticmethod
    def clear_guest_messages(guest_id: str):
        key = f"guest_chat:{guest_id}"
        cache.delete(key)
