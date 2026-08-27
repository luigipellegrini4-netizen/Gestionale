from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0031_registro_operazione"),
    ]

    operations = [
        migrations.AddField(
            model_name="articolo",
            name="quantita_per_confezione",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="articolo",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(quantita_per_confezione__isnull=True)
                    | models.Q(quantita_per_confezione__gt=0)
                ),
                name="articolo_quantita_confezione_positiva",
            ),
        ),
    ]
