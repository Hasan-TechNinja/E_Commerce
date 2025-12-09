from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RegisterSerializer
from django.contrib.auth.models import User
from .models import EmailVerification, PasswordResetCode
import random
from django.core.mail import send_mail


# Create your views here.

class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)

        if serializer.is_valid():
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            first_name = serializer.validated_data['first_name']
            last_name = serializer.validated_data['last_name']

            existing_user = User.objects.filter(email=email).first()

            # CASE 1: User already exists and active → BLOCK registration
            if existing_user and existing_user.is_active:
                return Response(
                    {"error": "Email already in use"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # CASE 2: User exists but NOT active → regenerate verification code
            if existing_user and not existing_user.is_active:
                # update user data
                existing_user.first_name = first_name
                existing_user.last_name = last_name
                existing_user.set_password(password)
                existing_user.save()

                # delete any old codes
                EmailVerification.objects.filter(user=existing_user).delete()

                # generate new code
                code = random.randint(1000, 9999)
                EmailVerification.objects.create(user=existing_user, code=str(code))

                send_mail(
                    "Resend Verification Code",
                    f"Your new verification code is {code}",
                    "noreply@yourdomain.com",
                    [email],
                )

                return Response(
                    {"message": "User already exists but not verified. New code sent."},
                    status=status.HTTP_200_OK
                )

            # CASE 3: User does NOT exist → Create new inactive user
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            user.is_active = False
            user.save()

            # send verification code
            code = random.randint(1000, 9999)
            EmailVerification.objects.create(user=user, code=str(code))

            send_mail(
                "Registration Verification Code",
                f"Your verification code is {code}",
                "noreply@yourdomain.com",
                [email],
            )

            return Response(
                {"message": "User registered successfully. Please verify your email."},
                status=status.HTTP_201_CREATED
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class VerifyEmailView(APIView):
    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User does not exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            verification = EmailVerification.objects.get(user=user, code=code)
        except EmailVerification.DoesNotExist:
            return Response({"error": "Invalid verification code"}, status=status.HTTP_400_BAD_REQUEST)

        if verification.is_expired():
            verification.delete()
            return Response({"error": "Verification code expired"}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.save()
        verification.delete()

        return Response({"message": "Email verified successfully"}, status=status.HTTP_200_OK)
