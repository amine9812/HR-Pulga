from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User

from .models import AccountCreationRequest
from .services import validate_company_email


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Login", widget=forms.TextInput(attrs={"name": "login", "class": "form-control"}))
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control"}))


class AccountCreationRequestForm(forms.Form):
    email = forms.EmailField(label="Email professionnel")
    first_name = forms.CharField(label="Prenom", max_length=120)
    last_name = forms.CharField(label="Nom", max_length=120)
    phone_number = forms.CharField(label="Telephone", max_length=40)
    matricule = forms.CharField(label="Matricule / code employe", max_length=80, required=False)
    password1 = forms.CharField(label="Mot de passe", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = validate_company_email(self.cleaned_data.get("email") or "")
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            raise forms.ValidationError("Un compte existe deja pour cet email.")
        if AccountCreationRequest.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Une demande est deja en cours pour cet email.")
        return email

    def clean_phone_number(self):
        phone = (self.cleaned_data.get("phone_number") or "").strip()
        compact = phone.replace(" ", "").replace("-", "").replace(".", "")
        if not compact.startswith("+"):
            compact = compact.lstrip("0")
        digits = compact[1:] if compact.startswith("+") else compact
        if not digits.isdigit() or len(digits) < 8 or len(digits) > 15:
            raise forms.ValidationError("Entrez un numero de telephone valide.")
        return phone

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        if password1:
            password_validation.validate_password(password1)
        return cleaned


class VerificationCodeForm(forms.Form):
    code = forms.CharField(label="Code de verification", min_length=6, max_length=6)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].widget.attrs.update({"class": "form-control verification-code-input", "inputmode": "numeric", "autocomplete": "one-time-code", "placeholder": "000000"})

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code.isdigit() or len(code) != 6:
            raise forms.ValidationError("Entrez le code a 6 chiffres.")
        return code


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email professionnel")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({"class": "form-control", "autocomplete": "email"})

    def clean_email(self):
        return validate_company_email(self.cleaned_data.get("email") or "", audit_invalid=False)


class PasswordResetNewPasswordForm(forms.Form):
    password1 = forms.CharField(label="Nouveau mot de passe", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmation", widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}))

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        if password1:
            password_validation.validate_password(password1)
        return cleaned
