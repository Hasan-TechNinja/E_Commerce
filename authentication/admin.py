from django.contrib import admin
from . models import EmailVerification, PasswordResetCode, Profile

# Register your models here.



class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'image'
    )
admin.site.register(Profile, ProfileAdmin)