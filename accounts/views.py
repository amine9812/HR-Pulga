from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render

from hr.models import Employe, HistoriqueAction

from .forms import AccountCreationRequestForm
from .models import AccountCreationRequest


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
            email = form.cleaned_data["email"]
            employee = Employe.objects.filter(email__iexact=email).first()
            if form.cleaned_data.get("matricule"):
                employee = Employe.objects.filter(matricule__iexact=form.cleaned_data["matricule"]).first() or employee
            account_request = AccountCreationRequest(
                email=email,
                first_name=form.cleaned_data.get("first_name", ""),
                last_name=form.cleaned_data.get("last_name", ""),
                matricule=form.cleaned_data.get("matricule", ""),
                employee=employee,
            )
            account_request.set_password(form.cleaned_data["password1"])
            account_request.save()
            HistoriqueAction.objects.create(action="ACCOUNT_REQUEST_CREATED", details=email, entite_concernee="AccountCreationRequest", entite_id=account_request.pk)
            messages.success(request, "Votre demande de compte a ete envoyee a l'administration.")
            return redirect("account_request_status")
    else:
        form = AccountCreationRequestForm()
    return render(request, "auth/account_request.html", {"form": form})


def account_request_status(request):
    return render(request, "auth/account_request_status.html")
