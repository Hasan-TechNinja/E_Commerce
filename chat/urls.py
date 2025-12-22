# chat/urls.py

from django.urls import path
from .views import ChatHistoryView

urlpatterns = [
    path('history/', ChatHistoryView.as_view(), name='chat_history'),
]
