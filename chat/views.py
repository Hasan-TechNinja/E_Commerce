# chat/views.py

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import ChatMessage


class ChatHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        messages = ChatMessage.objects.filter(user=request.user)
        data = [
            {
                "sender": m.sender_name,
                "type": m.sender_type,
                "message": m.message,
                "time": m.created_at
            }
            for m in messages
        ]
        return Response(data)
