from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0038_vincoli_versioni_ricetta")]

    operations = [
        migrations.AddField(
            model_name="articolo",
            name="formato",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="articolo",
            name="unita_formato",
            field=models.CharField(blank=True, choices=[("G", "g"), ("KG", "kg"), ("ML", "ml"), ("L", "l")], max_length=2),
        ),
        migrations.AddField(
            model_name="produzione",
            name="quantita_ottenuta_kg",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
        migrations.AddConstraint(
            model_name="articolo",
            constraint=models.CheckConstraint(
                condition=models.Q(formato__isnull=True) | models.Q(formato__gt=0),
                name="articolo_formato_positivo",
            ),
        ),
        migrations.AddConstraint(
            model_name="articolo",
            constraint=models.CheckConstraint(
                condition=models.Q(formato__isnull=True, unita_formato="") | (models.Q(formato__isnull=False) & ~models.Q(unita_formato="")),
                name="articolo_formato_unita_coerenti",
            ),
        ),
        migrations.AddConstraint(
            model_name="produzione",
            constraint=models.CheckConstraint(
                condition=models.Q(quantita_ottenuta_kg__isnull=True) | models.Q(quantita_ottenuta_kg__gt=0),
                name="produzione_quantita_ottenuta_positiva",
            ),
        ),
    ]
