from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailConfirmationTokenGenerator(PasswordResetTokenGenerator):
    """
    Token generator for email confirmation.

    The hash incorporates ``is_email_confirmed`` so the token is automatically
    invalidated once the email has been confirmed.
    """

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.is_email_confirmed}"


# Reuse Django's built-in generator for password resets (invalidated on
# password change because the hash includes the current password).
password_reset_token = PasswordResetTokenGenerator()
email_confirmation_token = EmailConfirmationTokenGenerator()
