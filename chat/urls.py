# chat/urls.py

from django.urls import path
from .views import ChatHistoryView, TestResponseView, MigrateGuestChatView

urlpatterns = [
    path('history/', ChatHistoryView.as_view(), name='chat_history'),
    path('test-response/<int:id>', TestResponseView.as_view(), name='chat_test_response'),
    path('migrate/', MigrateGuestChatView.as_view(), name='chat_migrate_guest'),
]
