# chat/middleware.py
import jwt
from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()


class JWTAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        token = None

        # Authorization header
        auth_header = headers.get(b"authorization")
        if auth_header:
            auth_header = auth_header.decode()
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        # Query param fallback
        if not token:
            query = parse_qs(scope.get("query_string", b"").decode())
            token_list = query.get("token")
            if token_list:
                token = token_list[0]

        if not token:
            scope["user"] = AnonymousUser()
            return await self.app(scope, receive, send)

        try:
            payload = jwt.decode(
                token,
                api_settings.SIGNING_KEY,
                algorithms=[api_settings.ALGORITHM],
            )
            user_id = payload.get("user_id")
        except Exception:
            scope["user"] = AnonymousUser()
            return await self.app(scope, receive, send)

        scope["user"] = await self.get_user(user_id)
        return await self.app(scope, receive, send)

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return AnonymousUser()
