from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Departement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["libelle"]},
        ),
        migrations.CreateModel(
            name="Poste",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("niveau", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["libelle"]},
        ),
        migrations.CreateModel(
            name="Service",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("libelle", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("departement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="services", to="hr.departement")),
            ],
            options={"ordering": ["libelle"]},
        ),
        migrations.CreateModel(
            name="Employe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("matricule", models.CharField(max_length=100, unique=True)),
                ("nom", models.CharField(max_length=255)),
                ("prenom", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("telephone", models.CharField(blank=True, max_length=80)),
                ("date_naissance", models.DateField(blank=True, null=True)),
                ("date_embauche", models.DateField()),
                ("adresse", models.TextField(blank=True)),
                ("photo", models.ImageField(blank=True, null=True, upload_to="uploads/photos/")),
                ("actif", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("departement", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employes", to="hr.departement")),
                ("poste", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employes", to="hr.poste")),
                ("responsable", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="collaborateurs", to="hr.employe")),
                ("service", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="employes", to="hr.service")),
            ],
            options={"ordering": ["nom", "prenom"]},
        ),
        migrations.CreateModel(
            name="DemandeAdministrative",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type_demande", models.CharField(max_length=255)),
                ("description", models.TextField()),
                ("statut", models.CharField(choices=[("EN_ATTENTE", "En attente"), ("EN_COURS", "En cours"), ("VALIDEE", "Validee"), ("REFUSEE", "Refusee"), ("CLOTUREE", "Cloturee")], default="EN_ATTENTE", max_length=30)),
                ("date_creation", models.DateTimeField(default=django.utils.timezone.now)),
                ("date_traitement", models.DateTimeField(blank=True, null=True)),
                ("reponse", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("employe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="demandes_administratives", to="hr.employe")),
                ("traitee_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="demandes_admin_traitees", to="hr.employe")),
            ],
            options={"ordering": ["-date_creation"]},
        ),
        migrations.CreateModel(
            name="DemandeConge",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("type", models.CharField(choices=[("ANNUEL", "Annuel"), ("MALADIE", "Maladie"), ("MATERNITE", "Maternite"), ("SANS_SOLDE", "Sans solde")], max_length=30)),
                ("date_debut", models.DateField()),
                ("date_fin", models.DateField()),
                ("motif", models.TextField(blank=True)),
                ("statut", models.CharField(choices=[("EN_ATTENTE", "En attente"), ("EN_COURS", "En cours"), ("VALIDEE", "Validee"), ("REFUSEE", "Refusee"), ("CLOTUREE", "Cloturee")], default="EN_ATTENTE", max_length=30)),
                ("date_traitement", models.DateTimeField(blank=True, null=True)),
                ("commentaire_reponse", models.TextField(blank=True)),
                ("date_creation", models.DateTimeField(default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("employe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conges", to="hr.employe")),
                ("traitee_par", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conges_traites", to="hr.employe")),
            ],
            options={"ordering": ["-date_creation"]},
        ),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fichier", models.FileField(upload_to="uploads/documents/")),
                ("nom_fichier", models.CharField(max_length=255)),
                ("nom_original", models.CharField(max_length=255)),
                ("categorie", models.CharField(blank=True, default="General", max_length=255)),
                ("chemin_fichier", models.CharField(blank=True, max_length=500)),
                ("date_ajout", models.DateTimeField(default=django.utils.timezone.now)),
                ("taille", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("demande_admin", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="hr.demandeadministrative")),
                ("employe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="documents", to="hr.employe")),
                ("uploade_par", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="documents_uploades", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date_ajout"]},
        ),
    ]
