from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from .models import ChatMessage
from .serializers import ChatMessageSerializer
from django.core.cache import cache


class ChatHistoryView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get all chat messages for the logged-in user
            messages = ChatMessage.objects.filter(user=request.user).reverse()
            
            # Serialize the messages
            serializer = ChatMessageSerializer(messages, many=True)
            
            # Return response with metadata
            return Response({
                'success': True,
                'count': messages.count(),
                'messages': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TestResponseView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, id):
        return Response({
            'message': 'Test response from Chat API is successful.',
            'id': id
        }, status=status.HTTP_200_OK)


class MigrateGuestChatView(APIView):
    """Move temporary guest messages (from cache) into DB for the logged-in user.

    Expected payload: {"guest_id": "..."}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        guest_id = request.data.get("guest_id")
        if not guest_id:
            return Response({"success": False, "error": "guest_id required"}, status=status.HTTP_400_BAD_REQUEST)

        key = f"guest_chat:{guest_id}"
        messages = cache.get(key, [])

        created = []
        try:
            for msg in messages:
                m = ChatMessage.objects.create(
                    user=request.user,
                    sender_type=msg.get("type", "user"),
                    sender_name=msg.get("sender", "guest"),
                    message=msg.get("message", ""),
                )
                created.append(m.id)

            # clear cache for this guest
            cache.delete(key)

            return Response({"success": True, "created_ids": created}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"success": False, "error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)