from django.urls import path

from . import views

urlpatterns = [
    path("login", views.login_view, name="login"),
    path("creer-compte", views.account_request_create, name="account_request_create"),
    path("demande-compte/statut", views.account_request_status, name="account_request_status"),
    path("logout", views.logout_view, name="logout"),
]
