from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.services import cache, reset_limiters

from .tokens import email_confirmation_token, password_reset_token

User = get_user_model()


class UsersFlowTests(APITestCase):
    def setUp(self):
        # Reset shared (process-wide) integration state between tests.
        cache.clear()
        reset_limiters()
        self.password = "Str0ng-Pass!23"
        self.user = User.objects.create_user(
            email="jane@example.com",
            password=self.password,
            first_name="Jane",
        )

    def test_register_creates_user_and_sends_email(self):
        url = reverse("users:register")
        payload = {
            "email": "john@example.com",
            "first_name": "John",
            "password": "An0ther-Pass!9",
            "password_confirm": "An0ther-Pass!9",
        }
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="john@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_register_rejects_mismatched_passwords(self):
        url = reverse("users:register")
        payload = {
            "email": "x@example.com",
            "password": "An0ther-Pass!9",
            "password_confirm": "different",
        }
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_returns_tokens(self):
        url = reverse("users:login")
        resp = self.client.post(
            url, {"email": self.user.email, "password": self.password}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["email"], self.user.email)

    def test_me_requires_auth(self):
        resp = self.client.get(reverse("users:me"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get(reverse("users:me"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["email"], self.user.email)

    def test_me_patch_updates_names(self):
        self.client.force_authenticate(self.user)
        resp = self.client.patch(
            reverse("users:me"),
            {"first_name": "Johny", "last_name": "Updated"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["first_name"], "Johny")
        self.assertEqual(resp.data["last_name"], "Updated")
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Johny")

    def test_me_patch_cannot_change_email(self):
        self.client.force_authenticate(self.user)
        resp = self.client.patch(
            reverse("users:me"), {"email": "hacker@example.com"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "jane@example.com")

    def test_change_password(self):
        self.client.force_authenticate(self.user)
        new_password = "Brand-New-Pass!1"
        resp = self.client.post(
            reverse("users:change-password"),
            {
                "old_password": self.password,
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_forgot_password_sends_email(self):
        resp = self.client.post(
            reverse("users:forgot-password"), {"email": self.user.email}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)

    def test_forgot_password_unknown_email_is_silent(self):
        resp = self.client.post(
            reverse("users:forgot-password"), {"email": "nobody@example.com"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_password_with_token(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = password_reset_token.make_token(self.user)
        new_password = "Reset-Pass!2024"
        resp = self.client.post(
            reverse("users:reset-password"),
            {
                "uid": uid,
                "token": token,
                "new_password": new_password,
                "new_password_confirm": new_password,
            },
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))

    def test_confirm_email_with_token(self):
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        self.assertFalse(self.user.is_email_confirmed)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = email_confirmation_token.make_token(self.user)
        resp = self.client.post(
            reverse("users:confirm-email"), {"uid": uid, "token": token}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_confirmed)


class IntegrationsTests(APITestCase):
    """Covers the Rust-backed integrations wired into the users app."""

    def setUp(self):
        cache.clear()
        reset_limiters()
        self.password = "Str0ng-Pass!23"
        self.user = User.objects.create_user(
            email="jane@example.com", password=self.password, first_name="Jane"
        )

    def test_me_is_cached(self):
        # rust-py-cache: first GET populates the cache, second is served from it.
        self.client.force_authenticate(self.user)
        self.assertIsNone(cache.get(f"user:{self.user.id}"))
        self.client.get(reverse("users:me"))
        self.assertIsNotNone(cache.get(f"user:{self.user.id}"))

    def test_patch_me_invalidates_cache(self):
        self.client.force_authenticate(self.user)
        self.client.get(reverse("users:me"))  # populate cache
        self.client.patch(reverse("users:me"), {"first_name": "Changed"})
        self.assertIsNone(cache.get(f"user:{self.user.id}"))

    @override_settings(
        RATE_LIMITS={
            "default": {"limit": 1000, "window_seconds": 60},
            "login": {"limit": 2, "window_seconds": 60},
        }
    )
    def test_login_is_rate_limited(self):
        # rust-py-rate-limit: 3rd attempt within the window is throttled (429).
        reset_limiters()
        url = reverse("users:login")
        payload = {"email": self.user.email, "password": "wrong-password"}
        self.assertEqual(self.client.post(url, payload).status_code, 401)
        self.assertEqual(self.client.post(url, payload).status_code, 401)
        resp = self.client.post(url, payload)
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_audit_log_records_and_verifies(self):
        # rust-py-audit: a register call appends a verifiable, chained event.
        from apps.core.services import audit

        before = audit.verify()["total_events"]
        self.client.post(
            reverse("users:register"),
            {
                "email": "audited@example.com",
                "password": "An0ther-Pass!9",
                "password_confirm": "An0ther-Pass!9",
            },
        )
        result = audit.verify()
        self.assertTrue(result["valid"])
        self.assertEqual(result["total_events"], before + 1)
