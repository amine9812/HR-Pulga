from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "ADMIN", "ADMIN"
    RESPONSABLE_RH = "RESPONSABLE_RH", "RESPONSABLE RH"
    RESPONSABLE_HIERARCHIQUE = "RESPONSABLE_HIERARCHIQUE", "RESPONSABLE HIERARCHIQUE"
    EMPLOYE = "EMPLOYE", "EMPLOYE"


class UtilisateurProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=40, choices=Role.choices)
    actif = models.BooleanField(default=True)
    employe = models.OneToOneField(
        "hr.Employe",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="utilisateur_profile",
    )

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"

    def __str__(self):
        return self.user.username

    @property
    def login(self):
        return self.user.username

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN

    @property
    def is_rh(self):
        return self.role in {Role.ADMIN, Role.RESPONSABLE_RH}

    @property
    def is_manager(self):
        return self.role == Role.RESPONSABLE_HIERARCHIQUE


class AdminSetting(models.Model):
    key = models.CharField(max_length=80, unique=True)
    value = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class AccountCreationRequest(models.Model):
    STATUS_VERIFYING = "verifying"
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUSES = [
        (STATUS_VERIFYING, "Email verification"),
        (STATUS_PENDING, "Pending approval"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_DENIED, "Denied"),
    ]
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    phone_number = models.CharField(max_length=40, blank=True)
    matricule = models.CharField(max_length=80, blank=True)
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_VERIFYING)
    email_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    employee = models.ForeignKey("hr.Employe", on_delete=models.SET_NULL, null=True, blank=True, related_name="account_requests")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="account_request")
    onboarding_task = models.ForeignKey("hr.TacheEquipe", on_delete=models.SET_NULL, null=True, blank=True, related_name="account_onboarding_requests")
    onboarding_created_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(UtilisateurProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="account_request_decisions")

    class Meta:
        ordering = ["-submitted_at"]

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_decision_ready(self):
        return self.status == self.STATUS_PENDING and self.email_verified

    def __str__(self):
        return self.email


class VerificationCode(models.Model):
    PURPOSE_ACCOUNT_CREATION = "account_creation"
    PURPOSE_PASSWORD_RESET = "password_reset"
    PURPOSES = [
        (PURPOSE_ACCOUNT_CREATION, "Account creation"),
        (PURPOSE_PASSWORD_RESET, "Password reset"),
    ]
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=40, choices=PURPOSES, db_index=True)
    code_hash = models.CharField(max_length=255)
    request = models.ForeignKey(AccountCreationRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="verification_codes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="verification_codes")
    expires_at = models.DateTimeField()
    max_attempts = models.PositiveSmallIntegerField(default=5)
    attempts = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveSmallIntegerField(default=0)
    resend_available_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email", "purpose", "consumed_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def set_code(self, raw_code):
        self.code_hash = make_password(raw_code)

    def check_code(self, raw_code):
        return check_password(raw_code, self.code_hash)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return bool(self.consumed_at)

    @property
    def is_locked(self):
        return bool(self.locked_at) or self.attempts >= self.max_attempts

    def __str__(self):
        return f"{self.purpose}:{self.email}"
