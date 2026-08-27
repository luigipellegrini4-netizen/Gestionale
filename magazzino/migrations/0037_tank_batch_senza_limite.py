from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0036_posizione_su_giacenza")]

    operations = [
        migrations.RemoveConstraint(
            model_name="tankproduzione",
            name="tank_numero_batch_da_uno_a_cinque",
        ),
        migrations.AddConstraint(
            model_name="tankproduzione",
            constraint=models.CheckConstraint(
                condition=models.Q(numero_batch__gte=1),
                name="tank_numero_batch_positivo",
            ),
        ),
    ]
