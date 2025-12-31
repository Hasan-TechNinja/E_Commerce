from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from .models import ChatMessage
from .serializers import ChatMessageSerializer


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

    def get(self, request):
        return Response({
            'message': 'Test response from Chat API is successful.'
        }, status=status.HTTP_200_OK)