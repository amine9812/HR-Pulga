import json
import os
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from hr.models import Employe, HistoriqueAction, TacheEquipe

from .models import AccountCreationRequest, AdminSetting, Role, UtilisateurProfile, VerificationCode


GENERIC_RESET_MESSAGE = "If this email is authorized, a verification code has been sent."
UNAUTHORIZED_EMAIL_MESSAGE = "This email is not authorized. Please use your company email address."


@dataclass
class EmailResult:
    ok: bool
    message: str = ""
    provider_status: int | None = None


def env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def setting_value(key, default=""):
    env_key = key.upper()
    value = os.environ.get(env_key)
    if value not in {None, ""}:
        return str(value).strip()
    return (AdminSetting.objects.filter(key=key).values_list("value", flat=True).first() or default).strip()


def setting_int(key, default):
    value = setting_value(key, "")
    try:
        return int(value) if value != "" else default
    except (TypeError, ValueError):
        return default


def audit(action, details="", utilisateur=None, entity="", entity_id=None):
    safe_details = re.sub(r"\b\d{6}\b", "[code-redacted]", str(details or ""))
    forbidden = ["api-key", "apikey", "password=", "password_hash", "brevo_api_key"]
    if any(term in safe_details.lower() for term in forbidden):
        safe_details = "[sensitive-details-redacted]"
    try:
        HistoriqueAction.objects.create(
            action=action,
            details=safe_details[:1000],
            utilisateur=utilisateur,
            entite_concernee=entity,
            entite_id=entity_id,
        )
    except Exception:
        # Audit failure must never break security-sensitive user workflows.
        pass


def normalize_email(email):
    return (email or "").strip().lower()


def allowed_company_domains():
    raw = []
    setting_domains = setting_value("company_allowed_email_domains")
    if setting_domains:
        raw.append(setting_domains)
    single_domain = setting_value("company_email_domain") or os.environ.get("COMPANY_EMAIL_DOMAIN", "")
    if single_domain:
        raw.append(single_domain)
    env_domains = os.environ.get("COMPANY_ALLOWED_EMAIL_DOMAINS", "")
    if env_domains:
        raw.append(env_domains)
    domains = []
    for chunk in raw:
        for value in re.split(r"[,;\s]+", chunk):
            domain = value.strip().lower().lstrip("@")
            if domain and domain not in domains:
                domains.append(domain)
    return domains


def validate_company_email(email, *, audit_invalid=True):
    email = normalize_email(email)
    domains = allowed_company_domains()
    if not domains:
        audit("COMPANY_EMAIL_DOMAIN_MISSING", "No company email domain configured")
        raise ValidationError("Company email verification is not configured. Please contact an administrator.")
    if "@" not in email or not email.rsplit("@", 1)[-1]:
        raise ValidationError("Enter a valid company email address.")
    domain = email.rsplit("@", 1)[-1]
    if domain not in domains:
        if audit_invalid:
            audit("ACCOUNT_INVALID_COMPANY_EMAIL_REJECTED", f"Rejected domain {domain}")
        raise ValidationError(UNAUTHORIZED_EMAIL_MESSAGE)
    return email


class BrevoEmailService:
    API_URL = "https://api.brevo.com/v3/smtp/email"

    def __init__(self):
        self.api_key = os.environ.get("BREVO_API_KEY", "").strip()
        self.sender_email = setting_value("brevo_sender_email") or os.environ.get("BREVO_SENDER_EMAIL", "").strip()
        self.sender_name = setting_value("brevo_sender_name", "HR Platform") or os.environ.get("BREVO_SENDER_NAME", "HR Platform").strip()
        self.timeout = env_int("BREVO_TIMEOUT_SECONDS", 12)

    def send_template(self, *, to_email, to_name="", template_env="", subject="", html_content="", params=None, audit_action="BREVO_EMAIL_SENT"):
        to_email = normalize_email(to_email)
        if not self.api_key:
            audit("BREVO_EMAIL_SEND_FAILED", f"Missing BREVO_API_KEY for {audit_action}; recipient={to_email}")
            return EmailResult(False, "Email service is not configured.")
        if not self.sender_email:
            audit("BREVO_EMAIL_SEND_FAILED", f"Missing BREVO_SENDER_EMAIL for {audit_action}; recipient={to_email}")
            return EmailResult(False, "Email sender is not configured.")
        template_id = ""
        if template_env:
            template_id = os.environ.get(template_env, "").strip() or setting_value(template_env.lower(), "")
        payload = {
            "sender": {"email": self.sender_email, "name": self.sender_name},
            "to": [{"email": to_email, "name": to_name or to_email}],
            "params": params or {},
        }
        if template_id:
            try:
                payload["templateId"] = int(template_id)
            except ValueError:
                audit("BREVO_EMAIL_SEND_FAILED", f"Invalid template id for {template_env}; recipient={to_email}")
                return EmailResult(False, "Email template is invalid.")
        else:
            payload["subject"] = subject
            payload["htmlContent"] = html_content
            audit("BREVO_TEMPLATE_MISSING_FALLBACK_USED", f"{template_env or 'no-template'}; recipient={to_email}")
        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"accept": "application/json", "api-key": self.api_key, "content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.getcode()
            audit(audit_action, f"Brevo accepted email to {to_email}; status={status}")
            return EmailResult(200 <= status < 300, "Email sent.", status)
        except urllib.error.HTTPError as exc:
            status = exc.code
            if status == 401 or status == 403:
                message = "Brevo API key is invalid or unauthorized."
            elif status == 429:
                message = "Brevo rate limit or quota was reached."
            else:
                message = "Brevo rejected the email request."
            audit("BREVO_EMAIL_SEND_FAILED", f"{message} status={status}; recipient={to_email}")
            return EmailResult(False, message, status)
        except TimeoutError:
            audit("BREVO_EMAIL_SEND_FAILED", f"Brevo timeout; recipient={to_email}")
            return EmailResult(False, "Brevo timed out.")
        except Exception as exc:
            audit("BREVO_EMAIL_SEND_FAILED", f"Brevo unavailable: {type(exc).__name__}; recipient={to_email}")
            return EmailResult(False, "Email service is temporarily unavailable.")

    def send_account_verification(self, request_obj, code, expires_minutes):
        return self.send_template(
            to_email=request_obj.email,
            to_name=request_obj.full_name,
            template_env="BREVO_ACCOUNT_VERIFICATION_TEMPLATE_ID",
            subject="Your HR account verification code",
            html_content=f"<p>Your HR account verification code is <strong>{code}</strong>. It expires in {expires_minutes} minutes.</p>",
            params={
                "first_name": request_obj.first_name,
                "last_name": request_obj.last_name,
                "verification_code": code,
                "expiration_minutes": expires_minutes,
                "company_name": os.environ.get("COMPANY_NAME", "HR Platform"),
            },
            audit_action="ACCOUNT_VERIFICATION_CODE_SENT",
        )

    def send_password_reset(self, user, email, code, expires_minutes):
        return self.send_template(
            to_email=email,
            to_name=user.get_full_name() if user else "",
            template_env="BREVO_PASSWORD_RESET_TEMPLATE_ID",
            subject="Your HR password reset code",
            html_content=f"<p>Your password reset code is <strong>{code}</strong>. It expires in {expires_minutes} minutes.</p>",
            params={
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "verification_code": code,
                "expiration_minutes": expires_minutes,
                "company_name": os.environ.get("COMPANY_NAME", "HR Platform"),
            },
            audit_action="PASSWORD_RESET_CODE_SENT",
        )

    def send_account_decision(self, request_obj, approved):
        template_env = "BREVO_ACCOUNT_APPROVED_TEMPLATE_ID" if approved else "BREVO_ACCOUNT_REJECTED_TEMPLATE_ID"
        status_text = "approved" if approved else "rejected"
        return self.send_template(
            to_email=request_obj.email,
            to_name=request_obj.full_name,
            template_env=template_env,
            subject=f"Your HR account request was {status_text}",
            html_content=f"<p>Your HR account request was {status_text}. You can contact HR for additional details.</p>",
            params={
                "first_name": request_obj.first_name,
                "last_name": request_obj.last_name,
                "request_status": status_text,
                "admin_note": request_obj.admin_note[:300],
                "login_url": os.environ.get("LOGIN_URL", ""),
                "company_name": os.environ.get("COMPANY_NAME", "HR Platform"),
            },
            audit_action="ACCOUNT_DECISION_EMAIL_SENT",
        )


class VerificationCodeService:
    def __init__(self, email_service=None):
        self.email_service = email_service or BrevoEmailService()

    @staticmethod
    def generate_code():
        return f"{secrets.randbelow(1_000_000):06d}"

    def issue_code(self, *, email, purpose, request_obj=None, user=None, ttl_minutes=10, max_attempts=5, cooldown_seconds=60, resend=False):
        email = normalize_email(email)
        now = timezone.now()
        active = VerificationCode.objects.filter(email__iexact=email, purpose=purpose, consumed_at__isnull=True, locked_at__isnull=True).order_by("-created_at").first()
        resend_count = 0
        if active:
            if resend and active.resend_available_at and active.resend_available_at > now:
                seconds = max(1, int((active.resend_available_at - now).total_seconds()))
                audit("VERIFICATION_CODE_RESEND_RATE_LIMITED", f"purpose={purpose}; email={email}; wait_seconds={seconds}")
                raise ValidationError(f"Please wait {seconds} seconds before requesting another code.")
            resend_count = active.resend_count + (1 if resend else 0)
            active.locked_at = now
            active.save(update_fields=["locked_at", "updated_at"])
        raw_code = self.generate_code()
        code_obj = VerificationCode(
            email=email,
            purpose=purpose,
            request=request_obj,
            user=user,
            expires_at=now + timezone.timedelta(minutes=ttl_minutes),
            max_attempts=max_attempts,
            resend_count=resend_count,
            resend_available_at=now + timezone.timedelta(seconds=cooldown_seconds),
        )
        code_obj.set_code(raw_code)
        code_obj.save()
        return code_obj, raw_code

    def verify(self, *, email, purpose, code):
        email = normalize_email(email)
        raw_code = (code or "").strip()
        if not re.fullmatch(r"\d{6}", raw_code):
            raise ValidationError("Enter the 6-digit verification code.")
        error_message = ""
        with transaction.atomic():
            code_obj = (
                VerificationCode.objects.select_for_update()
                .filter(email__iexact=email, purpose=purpose, consumed_at__isnull=True, locked_at__isnull=True)
                .order_by("-created_at")
                .first()
            )
            if not code_obj:
                error_message = "No active verification code is available. Please request a new code."
            elif code_obj.is_expired:
                code_obj.locked_at = timezone.now()
                code_obj.save(update_fields=["locked_at", "updated_at"])
                error_message = "This verification code has expired. Please request a new code."
            elif code_obj.attempts >= code_obj.max_attempts:
                code_obj.locked_at = timezone.now()
                code_obj.save(update_fields=["locked_at", "updated_at"])
                error_message = "Too many attempts. Please request a new code."
            elif not code_obj.check_code(raw_code):
                code_obj.attempts += 1
                update_fields = ["attempts", "updated_at"]
                if code_obj.attempts >= code_obj.max_attempts:
                    code_obj.locked_at = timezone.now()
                    update_fields.append("locked_at")
                code_obj.save(update_fields=update_fields)
                error_message = "The verification code is incorrect."
            else:
                code_obj.consumed_at = timezone.now()
                code_obj.save(update_fields=["consumed_at", "updated_at"])
                return code_obj
        raise ValidationError(error_message)


class AccountRequestService:
    def __init__(self, code_service=None, email_service=None):
        self.email_service = email_service or BrevoEmailService()
        self.code_service = code_service or VerificationCodeService(self.email_service)

    def _find_employee(self, email, matricule=""):
        employee = Employe.objects.filter(email__iexact=email).first()
        if matricule:
            employee = Employe.objects.filter(matricule__iexact=matricule).first() or employee
        return employee

    def start_request(self, cleaned_data):
        email = validate_company_email(cleaned_data["email"])
        audit("ACCOUNT_REQUEST_FORM_SUBMITTED", f"email={email}")
        if User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).exists():
            raise ValidationError("An account already exists for this email.")
        existing = AccountCreationRequest.objects.filter(email__iexact=email).first()
        if existing and existing.status in {AccountCreationRequest.STATUS_VERIFYING, AccountCreationRequest.STATUS_PENDING, AccountCreationRequest.STATUS_APPROVED, AccountCreationRequest.STATUS_DENIED}:
            raise ValidationError("An account request already exists for this email.")
        employee = self._find_employee(email, cleaned_data.get("matricule", ""))
        with transaction.atomic():
            request_obj = AccountCreationRequest(
                email=email,
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
                phone_number=cleaned_data.get("phone_number", ""),
                matricule=cleaned_data.get("matricule", ""),
                employee=employee,
                status=AccountCreationRequest.STATUS_VERIFYING,
                email_verified=False,
            )
            request_obj.set_password(cleaned_data["password1"])
            request_obj.save()
            ttl = setting_int("account_verification_code_ttl_minutes", 10)
            code_obj, raw_code = self.code_service.issue_code(
                email=email,
                purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION,
                request_obj=request_obj,
                ttl_minutes=ttl,
                max_attempts=setting_int("account_verification_max_attempts", 5),
                cooldown_seconds=setting_int("account_verification_resend_cooldown_seconds", 60),
            )
        result = self.email_service.send_account_verification(request_obj, raw_code, ttl)
        if not result.ok:
            request_obj.delete()
            raise ValidationError(f"We could not send the verification email. {result.message}")
        audit("ACCOUNT_REQUEST_CREATED", f"email={email}", entity="AccountCreationRequest", entity_id=request_obj.pk)
        return request_obj

    def resend_code(self, request_obj):
        if request_obj.status != AccountCreationRequest.STATUS_VERIFYING:
            raise ValidationError("This request is no longer waiting for email verification.")
        ttl = setting_int("account_verification_code_ttl_minutes", 10)
        code_obj, raw_code = self.code_service.issue_code(
            email=request_obj.email,
            purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION,
            request_obj=request_obj,
            ttl_minutes=ttl,
            max_attempts=setting_int("account_verification_max_attempts", 5),
            cooldown_seconds=setting_int("account_verification_resend_cooldown_seconds", 60),
            resend=True,
        )
        result = self.email_service.send_account_verification(request_obj, raw_code, ttl)
        if not result.ok:
            raise ValidationError(f"We could not resend the verification email. {result.message}")
        audit("ACCOUNT_VERIFICATION_CODE_RESENT", f"email={request_obj.email}", entity="AccountCreationRequest", entity_id=request_obj.pk)

    def verify_email(self, request_obj, code):
        if request_obj.status != AccountCreationRequest.STATUS_VERIFYING:
            raise ValidationError("This request is no longer waiting for email verification.")
        try:
            self.code_service.verify(email=request_obj.email, purpose=VerificationCode.PURPOSE_ACCOUNT_CREATION, code=code)
        except ValidationError:
            audit("ACCOUNT_VERIFICATION_FAILED", f"email={request_obj.email}", entity="AccountCreationRequest", entity_id=request_obj.pk)
            raise
        request_obj.email_verified = True
        request_obj.verified_at = timezone.now()
        request_obj.status = AccountCreationRequest.STATUS_PENDING
        request_obj.save(update_fields=["email_verified", "verified_at", "status", "updated_at"])
        audit("ACCOUNT_EMAIL_VERIFIED", f"email={request_obj.email}", entity="AccountCreationRequest", entity_id=request_obj.pk)
        return request_obj

    def approve(self, request_obj, admin_profile, note=""):
        if not admin_profile or admin_profile.role != Role.ADMIN:
            raise PermissionDenied("Only administrators can approve account creation requests.")
        with transaction.atomic():
            locked = AccountCreationRequest.objects.select_for_update().get(pk=request_obj.pk)
            if not locked.is_decision_ready:
                raise ValidationError("This account request is not ready for approval.")
            if User.objects.filter(Q(username__iexact=locked.email) | Q(email__iexact=locked.email)).exists():
                raise ValidationError("An account already exists for this email.")
            if locked.employee and UtilisateurProfile.objects.filter(employe=locked.employee, actif=True).exists():
                raise ValidationError("This employee is already linked to an active account.")
            user = User(username=locked.email, email=locked.email, first_name=locked.first_name, last_name=locked.last_name, is_active=True)
            user.password = locked.password_hash
            user.save()
            UtilisateurProfile.objects.create(user=user, role=Role.EMPLOYE, employe=locked.employee, actif=True)
            locked.user = user
            locked.status = AccountCreationRequest.STATUS_APPROVED
            locked.admin_note = note
            locked.decided_at = timezone.now()
            locked.decided_by = admin_profile
            locked.save(update_fields=["user", "status", "admin_note", "decided_at", "decided_by", "updated_at"])
            audit("ACCOUNT_REQUEST_APPROVED", f"email={locked.email}", admin_profile, "AccountCreationRequest", locked.pk)
            audit("USER_ACCOUNT_ACTIVATED", f"email={locked.email}", admin_profile, "User", user.pk)
            self._create_onboarding_task(locked, admin_profile)
        self.email_service.send_account_decision(locked, approved=True)
        return locked

    def deny(self, request_obj, admin_profile, note=""):
        if not admin_profile or admin_profile.role != Role.ADMIN:
            raise PermissionDenied("Only administrators can deny account creation requests.")
        with transaction.atomic():
            locked = AccountCreationRequest.objects.select_for_update().get(pk=request_obj.pk)
            if locked.status in {AccountCreationRequest.STATUS_APPROVED, AccountCreationRequest.STATUS_DENIED}:
                raise ValidationError("This account request has already been decided.")
            locked.status = AccountCreationRequest.STATUS_DENIED
            locked.admin_note = note
            locked.decided_at = timezone.now()
            locked.decided_by = admin_profile
            locked.save(update_fields=["status", "admin_note", "decided_at", "decided_by", "updated_at"])
            audit("ACCOUNT_REQUEST_DENIED", f"email={locked.email}", admin_profile, "AccountCreationRequest", locked.pk)
        self.email_service.send_account_decision(locked, approved=False)
        return locked

    def _create_onboarding_task(self, request_obj, admin_profile):
        if request_obj.onboarding_task_id:
            return request_obj.onboarding_task
        try:
            task = TacheEquipe.objects.create(
                titre=f"Onboarding RH - {request_obj.full_name or request_obj.email}",
                description=(
                    "Finalize HR onboarding after account activation: role, department, service, job, manager, "
                    "team assignment, and missing employee profile details."
                ),
                employe=request_obj.employee,
                departement=request_obj.employee.departement if request_obj.employee else None,
                service=request_obj.employee.service if request_obj.employee else None,
                priorite="haute",
                mode_affectation="open",
                statut="ouverte",
                cree_par=admin_profile,
                date_limite=timezone.now() + timezone.timedelta(days=3),
            )
            request_obj.onboarding_task = task
            request_obj.onboarding_created_at = timezone.now()
            request_obj.save(update_fields=["onboarding_task", "onboarding_created_at", "updated_at"])
            audit("HR_ONBOARDING_ITEM_CREATED", f"email={request_obj.email}", admin_profile, "TacheEquipe", task.pk)
            return task
        except Exception as exc:
            audit("HR_ONBOARDING_CREATION_FAILED", f"email={request_obj.email}; error={type(exc).__name__}", admin_profile, "AccountCreationRequest", request_obj.pk)
            return None


class PasswordResetService:
    def __init__(self, code_service=None, email_service=None):
        self.email_service = email_service or BrevoEmailService()
        self.code_service = code_service or VerificationCodeService(self.email_service)

    def request_reset(self, email):
        email = validate_company_email(email, audit_invalid=False)
        audit("PASSWORD_RESET_REQUESTED", f"email={email}")
        user = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).select_related("profile").first()
        if not user or not user.is_active or (hasattr(user, "profile") and not user.profile.actif):
            audit("PASSWORD_RESET_INELIGIBLE", f"email={email}")
            return GENERIC_RESET_MESSAGE
        ttl = setting_int("password_reset_code_ttl_minutes", 10)
        code_obj, raw_code = self.code_service.issue_code(
            email=email,
            purpose=VerificationCode.PURPOSE_PASSWORD_RESET,
            user=user,
            ttl_minutes=ttl,
            max_attempts=setting_int("password_reset_max_attempts", 5),
            cooldown_seconds=setting_int("password_reset_resend_cooldown_seconds", 60),
        )
        result = self.email_service.send_password_reset(user, email, raw_code, ttl)
        if not result.ok:
            raise ValidationError(f"We could not send the password reset email. {result.message}")
        return GENERIC_RESET_MESSAGE

    def resend_code(self, email):
        email = validate_company_email(email, audit_invalid=False)
        user = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).select_related("profile").first()
        if not user or not user.is_active or (hasattr(user, "profile") and not user.profile.actif):
            return GENERIC_RESET_MESSAGE
        ttl = setting_int("password_reset_code_ttl_minutes", 10)
        code_obj, raw_code = self.code_service.issue_code(
            email=email,
            purpose=VerificationCode.PURPOSE_PASSWORD_RESET,
            user=user,
            ttl_minutes=ttl,
            max_attempts=setting_int("password_reset_max_attempts", 5),
            cooldown_seconds=setting_int("password_reset_resend_cooldown_seconds", 60),
            resend=True,
        )
        result = self.email_service.send_password_reset(user, email, raw_code, ttl)
        if not result.ok:
            raise ValidationError(f"We could not resend the password reset email. {result.message}")
        audit("PASSWORD_RESET_CODE_RESENT", f"email={email}")
        return GENERIC_RESET_MESSAGE

    def verify_code(self, email, code):
        email = normalize_email(email)
        try:
            code_obj = self.code_service.verify(email=email, purpose=VerificationCode.PURPOSE_PASSWORD_RESET, code=code)
        except ValidationError as exc:
            audit("PASSWORD_RESET_FAILED", f"email={email}")
            text = " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            if "No active" in text:
                raise ValidationError("The verification code is incorrect or expired.") from exc
            raise
        audit("PASSWORD_RESET_VERIFIED", f"email={email}")
        return code_obj

    def complete_reset(self, email, password):
        email = normalize_email(email)
        user = User.objects.filter(Q(email__iexact=email) | Q(username__iexact=email)).select_related("profile").first()
        if not user or not user.is_active or (hasattr(user, "profile") and not user.profile.actif):
            raise ValidationError("This password reset session is no longer valid.")
        password_validation.validate_password(password, user)
        user.set_password(password)
        user.save(update_fields=["password"])
        audit("PASSWORD_RESET_COMPLETED", f"email={email}", getattr(user, "profile", None), "User", user.pk)
        return user
