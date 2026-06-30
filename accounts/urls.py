from django.urls import path

from . import views

urlpatterns = [
    path("login", views.login_view, name="login"),
    path("creer-compte", views.account_request_create, name="account_request_create"),
    path("creer-compte/verification", views.account_request_verify, name="account_request_verify"),
    path("demande-compte/statut", views.account_request_status, name="account_request_status"),
    path("mot-de-passe-oublie", views.password_reset_request, name="password_reset_request"),
    path("mot-de-passe-oublie/verification", views.password_reset_verify, name="password_reset_verify"),
    path("mot-de-passe-oublie/nouveau", views.password_reset_confirm, name="password_reset_confirm"),
    path("logout", views.logout_view, name="logout"),
]
