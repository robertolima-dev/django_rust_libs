from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .tokens import email_confirmation_token, password_reset_token


def _uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def send_email_confirmation(user):
    """Send the email-confirmation link to a freshly registered user."""
    uid = _uid(user)
    token = email_confirmation_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/confirm-email?uid={uid}&token={token}"

    send_mail(
        subject="Confirm your email address",
        message=(
            f"Welcome!\n\nPlease confirm your email by visiting:\n{link}\n\n"
            "If you did not create an account, you can ignore this message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )


def send_password_reset(user):
    """Send a password-reset link to a user that requested it."""
    uid = _uid(user)
    token = password_reset_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

    send_mail(
        subject="Reset your password",
        message=(
            f"We received a request to reset your password.\n\n"
            f"Use this link to choose a new one:\n{link}\n\n"
            "If you did not request this, you can safely ignore this email."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
