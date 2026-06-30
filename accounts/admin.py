from django.contrib import admin

from .models import AccountCreationRequest, AdminSetting, UtilisateurProfile


@admin.register(UtilisateurProfile)
class UtilisateurProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "actif", "employe")
    list_filter = ("role", "actif")
    search_fields = ("user__username", "employe__nom", "employe__prenom")


admin.site.register(AdminSetting)
admin.site.register(AccountCreationRequest)
