from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import RegisterSerializer, ProfileSerializer
from django.contrib.auth.models import User
from .models import EmailVerification, PasswordResetCode, Profile
import random
from django.core.mail import send_mail
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken


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
    

class LoginView(APIView):
    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:
            return Response(
                {"error": "Email and password required!"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = User.objects.filter(email=email).first()

        if not user or not user.check_password(password):
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.is_active:
            return Response(
                {"error": "Please verify your email first."},
                status=status.HTTP_403_FORBIDDEN
            )

        # authenticate to respect auth backends
        user = authenticate(username=user.username, password=password)
        if user is None:
            return Response(
                {"error": "Invalid credentials."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ safe profile handling
        profile = Profile.objects.filter(user=user).first()

        refresh = RefreshToken.for_user(user)

        data = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "image": profile.image.url if profile and profile.image else None,
        }

        return Response({
            "message": "Login successful.",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "data": data
        }, status=status.HTTP_200_OK)
        


class ForgetPasswordCodeSend(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        email = request.data.get("email")
        if not email:
             return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        try: 
            user = User.objects.get(email = email)
        except User.DoesNotExist:
            return Response({"error": "User does not exist!"}, status=status.HTTP_404_NOT_FOUND)
        
        code = random.randint(1000, 9999)

        PasswordResetCode.objects.create(user = user, code = code)

        send_mail(
            "Password reset Code",
            f"Your password reset code is: {code}",
            "noreply@yourdomain.com",
            [email],
        )

        return Response({"message": "Password reset code send successfully!"})


class VerifyPasswordResetCodeView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        code = request.data.get("code")

        if not email or not code:
            return Response({"error": "Email and code are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User does not exist"}, status=status.HTTP_404_NOT_FOUND)

        try:
            reset_code = PasswordResetCode.objects.get(user=user, code=code)
        except PasswordResetCode.DoesNotExist:
            return Response({"error": "Invalid code"}, status=status.HTTP_400_BAD_REQUEST)

        if reset_code.is_expired():
            reset_code.delete()
            return Response({"error": "Code expired"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Code verified successfully"}, status=status.HTTP_200_OK)


class SetNewPasswordView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not email or not new_password or not confirm_password:
            return Response({"error": "Email, new password, and confirm password are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        if new_password != confirm_password:
             return Response({"error": "Passwords do not match"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response({"error": "User does not exist"}, status=status.HTTP_404_NOT_FOUND)


        user.set_password(new_password)
        user.save()
        
        PasswordResetCode.objects.filter(user=user).delete()

        return Response({"message": "Password reset successfully"}, status=status.HTTP_200_OK)
    

class SocialLogin(APIView):
    
    def login_user(self, user):
        refresh = RefreshToken.for_user(user)
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'email': user.email
        }, status=status.HTTP_200_OK)

    def send_account_creation_email(self, user):
        send_mail(
            "Welcome to Our Platform",
            "Your account has been created successfully via social login.",
            "noreply@yourdomain.com",
            [user.email],
            fail_silently=True,
        )

    def post(self, request):
        # Get the email from the request data
        email = request.data.get('email')

        if not email:
            return Response({"error": "Email is required!"}, status=status.HTTP_400_BAD_REQUEST)

        # Check if the user exists
        user = User.objects.filter(email=email).first()

        if user:
            # If the user exists, simply log them in and return tokens
            return self.login_user(user)
        else:
            # If the user does not exist, create a new user
            user = User.objects.create_user(
                email=email,
                username=email,
                password=None  # No password needed for social/login
            )
            user.is_active = True # Social login users are verified by provider
            user.save()
            
            # Send account creation email
            self.send_account_creation_email(user)
            
            # Login the newly created user and return tokens
            return self.login_user(user)
        

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response({"message": "Logout successful"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)
        

class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = Profile.objects.get(user = request.user)

        serializer = ProfileSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    

    def put(self, request):
        profile = Profile.objects.get(user=request.user)

        serializer = ProfileSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)