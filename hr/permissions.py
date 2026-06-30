from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from accounts.models import Role


def profile_for(user):
    return getattr(user, "profile", None)


def has_any_role(user, *roles):
    profile = profile_for(user)
    return bool(user.is_authenticated and profile and profile.actif and profile.role in roles)


def role_required(*roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not has_any_role(request.user, *roles):
                messages.error(request, "Vous n'etes pas autorise a acceder a cette page.")
                return redirect("dashboard")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def can_manage_hr(user):
    return has_any_role(user, Role.ADMIN, Role.RESPONSABLE_RH)


def can_view_employees(user):
    return has_any_role(user, Role.ADMIN, Role.RESPONSABLE_RH, Role.RESPONSABLE_HIERARCHIQUE)
