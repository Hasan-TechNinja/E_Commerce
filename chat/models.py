# chat/models.py

from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class ChatMessage(models.Model):
    SENDER_CHOICES = (
        ("user", "User"),
        ("ai", "AI"),
    )

    user = models.ForeignKey(User,on_delete=models.CASCADE,related_name="chat_messages")
    sender_type = models.CharField(max_length=10,choices=SENDER_CHOICES)
    sender_name = models.CharField(max_length=100)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.sender_name}: {self.message[:30]}"
