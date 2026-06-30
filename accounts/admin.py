from django.contrib import admin

from .models import AccountCreationRequest, AdminSetting, UtilisateurProfile, VerificationCode


@admin.register(UtilisateurProfile)
class UtilisateurProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "actif", "employe")
    list_filter = ("role", "actif")
    search_fields = ("user__username", "employe__nom", "employe__prenom")


admin.site.register(AdminSetting)
admin.site.register(AccountCreationRequest)


@admin.register(VerificationCode)
class VerificationCodeAdmin(admin.ModelAdmin):
    list_display = ("email", "purpose", "expires_at", "attempts", "max_attempts", "consumed_at", "locked_at")
    list_filter = ("purpose", "consumed_at", "locked_at")
    search_fields = ("email",)
    readonly_fields = ("code_hash", "created_at", "updated_at")
