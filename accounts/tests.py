import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hr.models import Departement, Employe, HistoriqueAction, Poste, TacheEquipe

from .models import AccountCreationRequest, AdminSetting, Role, UtilisateurProfile, VerificationCode
from .services import BrevoEmailService, EmailResult, VerificationCodeService


class BrevoAccountSecurityTests(TestCase):
    def setUp(self):
        self.dep = Departement.objects.create(libelle="Operations")
        self.poste = Poste.objects.create(libelle="Analyste")
        self.admin_emp = Employe.objects.create(
            matricule="ADM-BREVO",
            nom="Admin",
            prenom="Root",
            email="admin@company.test",
            date_embauche=timezone.localdate(),
            departement=self.dep,
            poste=self.poste,
        )
        self.employee = Employe.objects.create(
            matricule="EMP-BREVO",
            nom="Verified",
            prenom="User",
            email="verified@company.test",
            telephone="+212600000000",
            date_embauche=timezone.localdate(),
            departement=self.dep,
            poste=self.poste,
        )
        self.admin_user = User.objects.create_user("admin-brevo", password="admin123", email="admin@company.test")
        UtilisateurProfile.objects.create(user=self.admin_user, role=Role.ADMIN, employe=self.admin_emp)
        AdminSetting.objects.create(key="company_email_domain", value="company.test")
        AdminSetting.objects.create(key="account_verification_resend_cooldown_seconds", value="0")
        AdminSetting.objects.create(key="password_reset_resend_cooldown_seconds", value="0")

    def signup_payload(self, **overrides):
        payload = {
            "email": "verified@company.test",
            "first_name": "Verified",
            "last_name": "User",
            "phone_number": "+212600000000",
            "matricule": "EMP-BREVO",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!",
        }
        payload.update(overrides)
        return payload

    @patch("accounts.services.BrevoEmailService.send_account_decision", return_value=EmailResult(True))
    @patch("accounts.services.BrevoEmailService.send_account_verification", return_value=EmailResult(True))
    @patch("accounts.services.VerificationCodeService.generate_code", return_value="123456")
    def test_account_creation_requires_email_code_then_admin_approval(self, code_mock, send_verification, send_decision):
        response = self.client.post(reverse("account_request_create"), self.signup_payload())

        self.assertRedirects(response, reverse("account_request_verify"))
        account_request = AccountCreationRequest.objects.get(email="verified@company.test")
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_VERIFYING)
        self.assertFalse(account_request.email_verified)
        self.assertNotIn("StrongPass123!", account_request.password_hash)
        verification = VerificationCode.objects.get(email="verified@company.test", purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION)
        self.assertNotIn("123456", verification.code_hash)
        self.assertFalse(self.client.login(username="verified@company.test", password="StrongPass123!"))

        wrong = self.client.post(reverse("account_request_verify"), {"code": "000000"})
        self.assertEqual(wrong.status_code, 200)
        verification.refresh_from_db()
        self.assertEqual(verification.attempts, 1)

        response = self.client.post(reverse("account_request_verify"), {"code": "123456"})
        self.assertRedirects(response, reverse("account_request_status"))
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_PENDING)
        self.assertTrue(account_request.email_verified)

        self.client.login(username="admin-brevo", password="admin123")
        response = self.client.post(reverse("admin_account_request_decision", args=[account_request.pk]), {"action": "approve", "admin_note": "OK"})
        self.assertRedirects(response, f"{reverse('admin_dashboard')}?tab=account_requests")
        account_request.refresh_from_db()
        self.assertEqual(account_request.status, AccountCreationRequest.STATUS_APPROVED)
        self.assertTrue(User.objects.filter(username="verified@company.test", is_active=True).exists())
        self.assertTrue(TacheEquipe.objects.filter(titre__icontains="Onboarding RH").exists())
        self.assertTrue(HistoriqueAction.objects.filter(action="ACCOUNT_REQUEST_APPROVED").exists())

        self.client.logout()
        self.assertTrue(self.client.login(username="verified@company.test", password="StrongPass123!"))

    @patch("accounts.services.BrevoEmailService.send_account_verification", return_value=EmailResult(True))
    def test_invalid_domain_duplicate_and_weak_password_are_blocked(self, send_verification):
        invalid_domain = self.client.post(reverse("account_request_create"), self.signup_payload(email="bad@external.test"))
        self.assertEqual(invalid_domain.status_code, 200)
        self.assertFalse(AccountCreationRequest.objects.exists())

        weak = self.client.post(reverse("account_request_create"), self.signup_payload(password1="123", password2="123"))
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(AccountCreationRequest.objects.exists())

        AccountCreationRequest.objects.create(email="verified@company.test", first_name="Existing", last_name="Pending", password_hash="hash")
        duplicate = self.client.post(reverse("account_request_create"), self.signup_payload())
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(AccountCreationRequest.objects.filter(email="verified@company.test").count(), 1)

    @patch("accounts.services.BrevoEmailService.send_account_decision", return_value=EmailResult(True))
    def test_non_admin_cannot_approve_and_unverified_request_cannot_be_approved(self, send_decision):
        plain_user = User.objects.create_user("plain", password="plain123", email="plain@company.test")
        UtilisateurProfile.objects.create(user=plain_user, role=Role.EMPLOYE)
        request_obj = AccountCreationRequest.objects.create(email="new@company.test", first_name="New", last_name="User", password_hash="hash")

        self.client.login(username="plain", password="plain123")
        response = self.client.post(reverse("admin_account_request_decision", args=[request_obj.pk]), {"action": "approve"})
        self.assertRedirects(response, reverse("dashboard"))

        self.client.login(username="admin-brevo", password="admin123")
        response = self.client.post(reverse("admin_account_request_decision", args=[request_obj.pk]), {"action": "approve"})
        self.assertRedirects(response, f"{reverse('admin_dashboard')}?tab=account_requests")
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, AccountCreationRequest.STATUS_VERIFYING)
        self.assertFalse(User.objects.filter(username="new@company.test").exists())

    @patch("accounts.services.BrevoEmailService.send_password_reset", return_value=EmailResult(True))
    @patch("accounts.services.VerificationCodeService.generate_code", return_value="654321")
    def test_password_reset_code_updates_password_without_revealing_unknown_email(self, code_mock, send_reset):
        user = User.objects.create_user("reset@company.test", password="OldPass123!", email="reset@company.test")
        UtilisateurProfile.objects.create(user=user, role=Role.EMPLOYE, employe=self.employee)

        response = self.client.post(reverse("password_reset_request"), {"email": "unknown@company.test"})
        self.assertRedirects(response, reverse("password_reset_verify"))
        self.assertFalse(VerificationCode.objects.filter(email="unknown@company.test").exists())

        self.client = self.client_class()
        response = self.client.post(reverse("password_reset_request"), {"email": "reset@company.test"})
        self.assertRedirects(response, reverse("password_reset_verify"))
        reset_code = VerificationCode.objects.get(email="reset@company.test", purpose=VerificationCode.PURPOSE_PASSWORD_RESET)
        self.assertNotIn("654321", reset_code.code_hash)

        wrong = self.client.post(reverse("password_reset_verify"), {"code": "111111"})
        self.assertEqual(wrong.status_code, 200)
        reset_code.refresh_from_db()
        self.assertEqual(reset_code.attempts, 1)

        response = self.client.post(reverse("password_reset_verify"), {"code": "654321"})
        self.assertRedirects(response, reverse("password_reset_confirm"))
        response = self.client.post(reverse("password_reset_confirm"), {"password1": "NewPass123!", "password2": "NewPass123!"})
        self.assertRedirects(response, reverse("login"))
        self.assertFalse(self.client.login(username="reset@company.test", password="OldPass123!"))
        self.assertTrue(self.client.login(username="reset@company.test", password="NewPass123!"))
        self.assertTrue(HistoriqueAction.objects.filter(action="PASSWORD_RESET_COMPLETED").exists())

    @override_settings(DEBUG=False)
    def test_brevo_missing_api_key_is_graceful_and_does_not_expose_secret(self):
        with patch.dict("os.environ", {"BREVO_API_KEY": "", "BREVO_SENDER_EMAIL": "hr@company.test"}, clear=False):
            result = BrevoEmailService().send_template(
                to_email="user@company.test",
                subject="Test",
                html_content="<p>Test</p>",
                audit_action="TEST_EMAIL",
            )
        self.assertFalse(result.ok)
        self.assertIn("configured", result.message)
        self.assertFalse(HistoriqueAction.objects.filter(details__icontains="api-key").exists())

    @patch("accounts.services.VerificationCodeService.generate_code", return_value="123456")
    def test_expired_codes_and_too_many_attempts_are_blocked(self, code_mock):
        service = VerificationCodeService()
        code_obj, raw = service.issue_code(
            email="edge@company.test",
            purpose=VerificationCode.PURPOSE_PASSWORD_RESET,
            ttl_minutes=10,
            max_attempts=2,
            cooldown_seconds=0,
        )
        code_obj.expires_at = timezone.now() - timezone.timedelta(minutes=1)
        code_obj.save(update_fields=["expires_at"])

        with self.assertRaisesMessage(Exception, "expired"):
            service.verify(email="edge@company.test", purpose=VerificationCode.PURPOSE_PASSWORD_RESET, code="123456")
        code_obj.refresh_from_db()
        self.assertIsNotNone(code_obj.locked_at)

        code_obj, raw = service.issue_code(
            email="edge@company.test",
            purpose=VerificationCode.PURPOSE_PASSWORD_RESET,
            ttl_minutes=10,
            max_attempts=2,
            cooldown_seconds=0,
        )
        for attempt in ["111111", "222222"]:
            with self.assertRaises(Exception):
                service.verify(email="edge@company.test", purpose=VerificationCode.PURPOSE_PASSWORD_RESET, code=attempt)
        code_obj.refresh_from_db()
        self.assertEqual(code_obj.attempts, 2)
        self.assertIsNotNone(code_obj.locked_at)

    @patch("accounts.services.VerificationCodeService.generate_code", return_value="123456")
    def test_resend_code_respects_cooldown(self, code_mock):
        service = VerificationCodeService()
        service.issue_code(
            email="cooldown@company.test",
            purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION,
            ttl_minutes=10,
            max_attempts=5,
            cooldown_seconds=60,
        )
        with self.assertRaisesMessage(Exception, "Please wait"):
            service.issue_code(
                email="cooldown@company.test",
                purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION,
                ttl_minutes=10,
                max_attempts=5,
                cooldown_seconds=60,
                resend=True,
            )
