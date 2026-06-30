from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import models


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
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_DENIED = "denied"
    STATUSES = [(STATUS_PENDING, "Pending"), (STATUS_APPROVED, "Approved"), (STATUS_DENIED, "Denied")]
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=120, blank=True)
    last_name = models.CharField(max_length=120, blank=True)
    matricule = models.CharField(max_length=80, blank=True)
    password_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING)
    employee = models.ForeignKey("hr.Employe", on_delete=models.SET_NULL, null=True, blank=True, related_name="account_requests")
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="account_request")
    admin_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(UtilisateurProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="account_request_decisions")

    class Meta:
        ordering = ["-submitted_at"]

    def set_password(self, raw_password):
        self.password_hash = make_password(raw_password)

    def __str__(self):
        return self.email
