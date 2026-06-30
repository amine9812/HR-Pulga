from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("hr", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UtilisateurProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("ADMIN", "ADMIN"), ("RESPONSABLE_RH", "RESPONSABLE RH"), ("RESPONSABLE_HIERARCHIQUE", "RESPONSABLE HIERARCHIQUE"), ("EMPLOYE", "EMPLOYE")], max_length=40)),
                ("actif", models.BooleanField(default=True)),
                ("employe", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="utilisateur_profile", to="hr.employe")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Utilisateur", "verbose_name_plural": "Utilisateurs"},
        ),
    ]
