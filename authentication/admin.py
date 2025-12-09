from django.contrib import admin
from . models import EmailVerification, PasswordResetCode

# Register your models here.

class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'code', 'created_at'
    )
admin.site.register(EmailVerification, EmailVerificationAdmin)



class PasswordResetCodeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'code', 'created_at'
    )
admin.site.register(PasswordResetCode, PasswordResetCodeAdmin)