from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr", "0013_conversationrh_date_note_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="planningshift",
            name="date_fin",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="planningshift",
            name="plan_type",
            field=models.CharField(
                choices=[("normal", "Plan normal"), ("permanent", "Plan permanent")],
                default="normal",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="planningshift",
            name="recurrence_rule",
            field=models.CharField(
                choices=[("none", "Aucune"), ("weekdays", "Jours ouvrables"), ("daily", "Tous les jours"), ("weekly", "Hebdomadaire")],
                default="none",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="planningshift",
            name="permanent_end_time",
            field=models.TimeField(blank=True, null=True),
        ),
    ]
