from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.services import audit, cache, invalidate_user, user_cache_key
from apps.core.throttle import client_ip, enforce

from .emails import send_email_confirmation, send_password_reset
from .serializers import (
    ChangePasswordSerializer,
    ConfirmEmailSerializer,
    ForgotPasswordSerializer,
    RegisterSerializer,
    ResetPasswordConfirmSerializer,
    UserSerializer,
)

User = get_user_model()


def _audit(request, actor_id, action, resource_id, **metadata):
    """Record a semantic domain event in the tamper-evident audit log."""
    metadata.setdefault("ip", client_ip(request))
    audit.log(
        actor_id=str(actor_id),
        action=action,
        resource="user",
        resource_id=str(resource_id),
        metadata=metadata,
    )


class RegisterView(generics.CreateAPIView):
    """POST /register — create an account and send the confirmation email."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        enforce("register", client_ip(request))  # rust-py-rate-limit
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        send_email_confirmation(user)
        _audit(request, user.id, "USER_REGISTERED", user.id, email=user.email)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginSerializer(TokenObtainPairSerializer):
    """Adds user data alongside the access/refresh tokens."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LoginView(TokenObtainPairView):
    """POST /login — authenticate by email + password and return JWT tokens."""

    permission_classes = [permissions.AllowAny]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        enforce("login", client_ip(request))  # rust-py-rate-limit
        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            user = response.data.get("user", {})
            _audit(request, user.get("id", "anonymous"), "USER_LOGIN", user.get("id", "-"))
        return response


class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /me — retrieve or update the authenticated user."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        # rust-py-cache: serve the cached representation when available.
        key = user_cache_key(request.user.id)
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        data = self.get_serializer(request.user).data
        cache.set(key, data, ttl=settings.USER_CACHE_TTL)
        return Response(data)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        invalidate_user(request.user.id)  # rust-py-cache: bust stale entry
        _audit(request, request.user.id, "PROFILE_UPDATED", request.user.id)
        return response


class ChangePasswordView(APIView):
    """POST /change-password — change the password of the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_user(request.user.id)
        _audit(request, request.user.id, "PASSWORD_CHANGED", request.user.id)
        return Response({"detail": "Password updated successfully."})


class ForgotPasswordView(APIView):
    """POST /forgot-password — email a reset link if the account exists."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        enforce("forgot_password", client_ip(request))  # rust-py-rate-limit
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.filter(email__iexact=email).first()
        if user is not None:
            send_password_reset(user)
            _audit(request, user.id, "PASSWORD_RESET_REQUESTED", user.id, email=email)

        # Always respond the same way to avoid leaking which emails are registered.
        return Response(
            {"detail": "If the email exists, a reset link has been sent."}
        )


class ResetPasswordConfirmView(APIView):
    """POST /reset-password — complete the forgot-password flow."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        invalidate_user(user.id)
        _audit(request, user.id, "PASSWORD_RESET", user.id)
        return Response({"detail": "Password has been reset successfully."})


class ConfirmEmailView(APIView):
    """POST /confirm-email — validate the email confirmation token."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ConfirmEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        invalidate_user(user.id)
        _audit(request, user.id, "EMAIL_CONFIRMED", user.id)
        return Response({"detail": "Email confirmed successfully."})
