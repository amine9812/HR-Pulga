from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from accounts.models import Role, UtilisateurProfile
from hr.models import Departement, Employe, Poste, Service


class Command(BaseCommand):
    help = "Create default HR data and demo accounts."

    def handle(self, *args, **options):
        if UtilisateurProfile.objects.exists():
            self.stdout.write(self.style.WARNING("Seed skipped: users already exist."))
            return

        informatique = Departement.objects.create(
            libelle="Informatique",
            description="Departement charge des systemes d'information et du developpement",
        )
        ressources_humaines = Departement.objects.create(
            libelle="Ressources Humaines",
            description="Departement charge de la gestion administrative du personnel",
        )

        developpement = Service.objects.create(
            libelle="Developpement",
            description="Applications internes et plateformes web",
            departement=informatique,
        )
        infrastructure = Service.objects.create(
            libelle="Infrastructure",
            description="Reseaux, serveurs et support technique",
            departement=informatique,
        )
        administration_rh = Service.objects.create(
            libelle="Administration RH",
            description="Contrats, dossiers et documents administratifs",
            departement=ressources_humaines,
        )
        recrutement = Service.objects.create(
            libelle="Recrutement",
            description="Sourcing, entretiens et integration",
            departement=ressources_humaines,
        )

        developpeur = Poste.objects.create(
            libelle="Developpeur",
            description="Conception et maintenance des applications",
            niveau="Cadre",
        )
        chef_projet = Poste.objects.create(
            libelle="Chef de projet",
            description="Pilotage des projets et coordination des equipes",
            niveau="Manager",
        )
        charge_rh = Poste.objects.create(
            libelle="Charge RH",
            description="Suivi administratif et accompagnement RH",
            niveau="Cadre",
        )

        admin_employe = Employe.objects.create(
            matricule="EMP-0001",
            nom="Martin",
            prenom="Jeanne",
            email="jeanne.martin@hrplatform.local",
            telephone="0600000001",
            date_naissance=date(1984, 3, 12),
            date_embauche=date(2018, 1, 15),
            adresse="12 rue de la Paix, Paris",
            departement=ressources_humaines,
            service=administration_rh,
            poste=charge_rh,
        )
        rh_employe = Employe.objects.create(
            matricule="EMP-0002",
            nom="Bernard",
            prenom="Sophie",
            email="sophie.bernard@hrplatform.local",
            telephone="0600000002",
            date_naissance=date(1990, 7, 4),
            date_embauche=date(2020, 2, 10),
            adresse="8 avenue Hassan II, Casablanca",
            departement=ressources_humaines,
            service=recrutement,
            poste=charge_rh,
            responsable=admin_employe,
        )
        manager_employe = Employe.objects.create(
            matricule="EMP-0003",
            nom="Dubois",
            prenom="Marc",
            email="marc.dubois@hrplatform.local",
            telephone="0600000003",
            date_naissance=date(1987, 11, 22),
            date_embauche=date(2019, 5, 6),
            adresse="25 boulevard Zerktouni, Casablanca",
            departement=informatique,
            service=developpement,
            poste=chef_projet,
            responsable=admin_employe,
        )
        employe = Employe.objects.create(
            matricule="EMP-0004",
            nom="Petit",
            prenom="Claire",
            email="claire.petit@hrplatform.local",
            telephone="0600000004",
            date_naissance=date(1996, 9, 18),
            date_embauche=date(2022, 9, 1),
            adresse="17 rue Ibn Sina, Rabat",
            departement=informatique,
            service=infrastructure,
            poste=developpeur,
            responsable=manager_employe,
        )

        self.create_account("admin", "admin123", Role.ADMIN, admin_employe, is_staff=True, is_superuser=True)
        self.create_account("rh", "rh123", Role.RESPONSABLE_RH, rh_employe)
        self.create_account("manager", "manager123", Role.RESPONSABLE_HIERARCHIQUE, manager_employe)
        self.create_account("employe", "employe123", Role.EMPLOYE, employe)
        self.stdout.write(self.style.SUCCESS("Default HR data created."))

    def create_account(self, username, password, role, employe, is_staff=False, is_superuser=False):
        user = User.objects.create_user(
            username=username,
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser,
        )
        UtilisateurProfile.objects.create(user=user, role=role, employe=employe, actif=True)
