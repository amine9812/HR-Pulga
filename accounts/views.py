from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AccountCreationRequestForm, PasswordResetNewPasswordForm, PasswordResetRequestForm, VerificationCodeForm
from .models import AccountCreationRequest
from .services import AccountRequestService, PasswordResetService


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        username = request.POST.get("login") or request.POST.get("username")
        password = request.POST.get("password") or request.POST.get("motDePasse")
        user = authenticate(request, username=username, password=password)
        if user is not None and getattr(getattr(user, "profile", None), "actif", True):
            login(request, user)
            return redirect("dashboard")
        messages.error(request, "Login ou mot de passe incorrect.")
    return render(request, "auth/login.html")


def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "Vous etes deconnecte.")
    return redirect("login")


def account_request_create(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = AccountCreationRequestForm(request.POST)
        if form.is_valid():
            try:
                account_request = AccountRequestService().start_request(form.cleaned_data)
                request.session["account_request_id"] = account_request.pk
                messages.success(request, "Un code de verification a ete envoye a votre email professionnel.")
                return redirect("account_request_verify")
            except ValidationError as exc:
                form.add_error(None, _validation_message(exc))
    else:
        form = AccountCreationRequestForm()
    return render(request, "auth/account_request.html", {"form": form})


def account_request_verify(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    account_request_id = request.session.get("account_request_id")
    if not account_request_id:
        messages.error(request, "Votre session de verification a expire. Recommencez la demande.")
        return redirect("account_request_create")
    account_request = get_object_or_404(AccountCreationRequest, pk=account_request_id, status=AccountCreationRequest.STATUS_VERIFYING)
    form = VerificationCodeForm(request.POST or None)
    service = AccountRequestService()
    if request.method == "POST" and request.POST.get("action") == "resend":
        try:
            service.resend_code(account_request)
            messages.success(request, "Un nouveau code de verification a ete envoye.")
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        return redirect("account_request_verify")
    if request.method == "POST" and form.is_valid():
        try:
            service.verify_email(account_request, form.cleaned_data["code"])
            request.session.pop("account_request_id", None)
            messages.success(request, "Email verifie. Votre demande est maintenant en attente d'approbation administrateur.")
            return redirect("account_request_status")
        except ValidationError as exc:
            form.add_error("code", _validation_message(exc))
    return render(request, "auth/account_request_verify.html", {"form": form, "account_request": account_request})


def account_request_status(request):
    return render(request, "auth/account_request_status.html")


def password_reset_request(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            message = PasswordResetService().request_reset(form.cleaned_data["email"])
            request.session["password_reset_email"] = form.cleaned_data["email"]
            messages.success(request, message)
            return redirect("password_reset_verify")
        except ValidationError as exc:
            form.add_error(None, _validation_message(exc))
    return render(request, "auth/password_reset_request.html", {"form": form})


def password_reset_verify(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    email = request.session.get("password_reset_email")
    if not email:
        messages.error(request, "Votre session de reinitialisation a expire. Recommencez la demande.")
        return redirect("password_reset_request")
    form = VerificationCodeForm(request.POST or None)
    service = PasswordResetService()
    if request.method == "POST" and request.POST.get("action") == "resend":
        try:
            message = service.resend_code(email)
            messages.success(request, message)
        except ValidationError as exc:
            messages.error(request, _validation_message(exc))
        return redirect("password_reset_verify")
    if request.method == "POST" and form.is_valid():
        try:
            service.verify_code(email, form.cleaned_data["code"])
            request.session["password_reset_verified"] = True
            return redirect("password_reset_confirm")
        except ValidationError as exc:
            form.add_error("code", _validation_message(exc))
    return render(request, "auth/password_reset_verify.html", {"form": form, "email": email})


def password_reset_confirm(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    email = request.session.get("password_reset_email")
    if not email or not request.session.get("password_reset_verified"):
        messages.error(request, "Votre session de reinitialisation a expire. Recommencez la demande.")
        return redirect("password_reset_request")
    form = PasswordResetNewPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            PasswordResetService().complete_reset(email, form.cleaned_data["password1"])
            request.session.pop("password_reset_email", None)
            request.session.pop("password_reset_verified", None)
            messages.success(request, "Votre mot de passe a ete mis a jour. Vous pouvez vous connecter.")
            return redirect("login")
        except ValidationError as exc:
            form.add_error(None, _validation_message(exc))
    return render(request, "auth/password_reset_confirm.html", {"form": form})


def _validation_message(exc):
    return " ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
