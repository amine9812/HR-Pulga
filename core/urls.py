from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("dashboard", views.dashboard, name="dashboard"),
    path("admin", views.admin_dashboard, name="admin_dashboard"),
    path("admin/account-requests/<int:pk>/decision", views.admin_account_request_decision, name="admin_account_request_decision"),
    path("admin/users/<int:pk>/update", views.admin_user_update, name="admin_user_update"),
    path("admin/settings/save", views.admin_settings_save, name="admin_settings_save"),
]
