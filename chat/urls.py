# chat/urls.py

from django.urls import path
from .views import ChatHistoryView, TestResponseView

urlpatterns = [
    path('history/', ChatHistoryView.as_view(), name='chat_history'),
    path('test-response/', TestResponseView.as_view(), name='chat_test_response'),
]
