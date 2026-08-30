from django.db import migrations, models


def inizializza_unita_legacy(apps, schema_editor):
    NonConformita = apps.get_model("magazzino", "NonConformitaLotto")
    NonConformita.objects.filter(numero_uda_quarantena__isnull=False).update(
        unita_quarantena="UDA"
    )


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0067_rinomina_roboqbo")]

    operations = [
        migrations.AddField(
            model_name="nonconformitalotto",
            name="unita_quarantena",
            field=models.CharField(
                blank=True, choices=[("UDA", "UDA"), ("KG", "kg")], max_length=5,
            ),
        ),
        migrations.AddField(
            model_name="nonconformitalotto",
            name="quantita_scartata",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="nonconformitalotto",
            name="quantita_reintegrata",
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=12, null=True),
        ),
        migrations.RunPython(inizializza_unita_legacy, migrations.RunPython.noop),
    ]
