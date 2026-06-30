from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import AccountCreationRequest, AdminSetting


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Login", widget=forms.TextInput(attrs={"name": "login", "class": "form-control"}))
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))


class AccountCreationRequestForm(forms.Form):
    email = forms.EmailField(label="Email professionnel")
    first_name = forms.CharField(label="Prenom", max_length=120, required=False)
    last_name = forms.CharField(label="Nom", max_length=120, required=False)
    matricule = forms.CharField(label="Matricule / code employe", max_length=80, required=False)
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        domain = (AdminSetting.objects.filter(key="company_email_domain").values_list("value", flat=True).first() or "").strip().lower()
        if domain:
            domain = domain if domain.startswith("@") else f"@{domain}"
            if not email.endswith(domain):
                raise forms.ValidationError(f"Utilisez un email professionnel se terminant par {domain}.")
        if User.objects.filter(email__iexact=email, is_active=True).exists() or User.objects.filter(username__iexact=email, is_active=True).exists():
            raise forms.ValidationError("Un compte actif existe deja pour cet email.")
        if AccountCreationRequest.objects.filter(email__iexact=email, status=AccountCreationRequest.STATUS_PENDING).exists():
            raise forms.ValidationError("Une demande est deja en attente pour cet email.")
        return email

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        if password1:
            password_validation.validate_password(password1)
        return cleaned
