from django.db import migrations


def correggi_esito_batch_reintegrati(apps, schema_editor):
    Batch = apps.get_model("magazzino", "BatchProduzione")
    Batch.objects.filter(
        stato__in=["REINTEGRATO", "CONFORME"],
        risolto_il__isnull=False,
        esito_conformita="NC",
    ).update(esito_conformita="C", stato="CONFORME")


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0061_riordino_lotti_produzione")]

    operations = [
        migrations.RunPython(correggi_esito_batch_reintegrati, migrations.RunPython.noop),
    ]
