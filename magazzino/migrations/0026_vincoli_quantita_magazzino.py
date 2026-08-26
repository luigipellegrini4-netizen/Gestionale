from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0025_remove_prelievoproduzione_quantita_residua_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="lotto",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita_iniziale__gt", 0)),
                name="lotto_quantita_iniziale_positiva",
            ),
        ),
        migrations.AddConstraint(
            model_name="giacenza",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita__gte", 0)),
                name="giacenza_quantita_non_negativa",
            ),
        ),
        migrations.AddConstraint(
            model_name="movimento",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita__gt", 0)),
                name="movimento_quantita_positiva",
            ),
        ),
    ]
