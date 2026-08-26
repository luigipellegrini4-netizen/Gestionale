from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0028_ruoli_magazzino"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="articolo",
            constraint=models.CheckConstraint(
                condition=models.Q(("scorta_minima__gte", 0)),
                name="articolo_scorta_minima_non_negativa",
            ),
        ),
        migrations.AddConstraint(
            model_name="rigaricetta",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita__gt", 0)),
                name="riga_ricetta_quantita_positiva",
            ),
        ),
    ]
