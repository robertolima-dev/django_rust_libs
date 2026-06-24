from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .tokens import email_confirmation_token, password_reset_token

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of a user (used by /me)."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "is_email_confirmed",
            "date_joined",
        )
        # Only the name fields are editable (via PATCH /me); the rest are read-only.
        read_only_fields = (
            "id",
            "email",
            "full_name",
            "is_email_confirmed",
            "date_joined",
        )


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "password", "password_confirm")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["password"])
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        return User.objects.create_user(password=password, **validated_data)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class _UidTokenSerializer(serializers.Serializer):
    """Shared validation for actions that carry a uid + signed token."""

    uid = serializers.CharField()
    token = serializers.CharField()

    token_generator = None  # set by subclasses

    def _get_user(self, uid):
        try:
            pk = force_str(urlsafe_base64_decode(uid))
            return User.objects.get(pk=pk)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

    def validate(self, attrs):
        user = self._get_user(attrs["uid"])
        if user is None or not self.token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError("Invalid or expired token.")
        attrs["user"] = user
        return attrs


class ConfirmEmailSerializer(_UidTokenSerializer):
    token_generator = email_confirmation_token

    def save(self, **kwargs):
        user = self.validated_data["user"]
        if not user.is_email_confirmed:
            user.is_email_confirmed = True
            user.save(update_fields=["is_email_confirmed", "updated_at"])
        return user


class ResetPasswordConfirmSerializer(_UidTokenSerializer):
    token_generator = password_reset_token

    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password_confirm = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["new_password"], attrs["user"])
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user
