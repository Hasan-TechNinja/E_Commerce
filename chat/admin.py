from django.contrib import admin
from . models import ChatMessage

# Register your models here.

class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'sender_type', 'sender_name', 'message', 'created_at'
    )
    list_filter = ['user']
admin.site.register(ChatMessage, ChatMessageAdmin)