from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("hr", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="HistoriqueAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(max_length=255)),
                ("details", models.TextField(blank=True)),
                ("date_action", models.DateTimeField(default=django.utils.timezone.now)),
                ("entite_concernee", models.CharField(blank=True, max_length=255)),
                ("entite_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("utilisateur", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="actions", to="accounts.utilisateurprofile")),
            ],
            options={"ordering": ["-date_action"]},
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField()),
                ("date_envoi", models.DateTimeField(default=django.utils.timezone.now)),
                ("lue", models.BooleanField(default=False)),
                ("lien", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("destinataire", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="accounts.utilisateurprofile")),
            ],
            options={"ordering": ["-date_envoi"]},
        ),
    ]
