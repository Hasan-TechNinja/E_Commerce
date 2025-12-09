from django.contrib import admin
from . models import EmailVerification, PasswordResetCode, Profile

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


class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'image'
    )
admin.site.register(Profile, ProfileAdmin)