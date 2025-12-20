from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('login/', views.LoginView.as_view(), name="login"),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('forget-password/', views.ForgetPasswordCodeSend.as_view(), name='forget-password'),
    path('verify-pass-code/', views.VerifyPasswordResetCodeView.as_view(), name='verify-pass-code'),
    path('set-new-password/', views.SetNewPasswordView.as_view(), name='set-new-password'),
    path('social-login/', views.SocialLogin.as_view(), name='social-login'),
    path('change-password/', views.ChangePasswordView.as_view(), name='change-password'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]
