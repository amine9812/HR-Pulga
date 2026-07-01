from django.contrib import admin

from .models import (
    ActualitePieceJointe,
    DemandeAdministrative,
    DemandeConge,
    Departement,
    Document,
    Employe,
    HistoriqueAction,
    Notification,
    PlanningShift,
    Poste,
    Service,
    TacheEquipe,
    TacheEquipeMessage,
)


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display = ("matricule", "nom", "prenom", "email", "departement", "poste", "actif")
    list_filter = ("actif", "departement", "service", "poste")
    search_fields = ("matricule", "nom", "prenom", "email")


admin.site.register(Departement)
admin.site.register(Service)
admin.site.register(Poste)
admin.site.register(DemandeConge)
admin.site.register(DemandeAdministrative)
admin.site.register(Document)
admin.site.register(Notification)
admin.site.register(HistoriqueAction)
admin.site.register(PlanningShift)
admin.site.register(TacheEquipe)
admin.site.register(TacheEquipeMessage)
admin.site.register(ActualitePieceJointe)
