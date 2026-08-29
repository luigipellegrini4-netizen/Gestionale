from decimal import Decimal

from django.db import migrations


def ricalcola_quantita_teoriche(apps, schema_editor):
    Produzione = apps.get_model("magazzino", "Produzione")
    Ricetta = apps.get_model("magazzino", "Ricetta")
    RigaRicetta = apps.get_model("magazzino", "RigaRicetta")

    for produzione in Produzione.objects.all().iterator():
        ricetta = Ricetta.objects.filter(
            articolo_id=produzione.articolo_id, attiva=True,
        ).order_by("id").first()
        if ricetta is None:
            continue
        quantita_per_batch = sum(
            RigaRicetta.objects.filter(
                ricetta_id=ricetta.pk, ingrediente_prodotto=True,
            ).values_list("quantita", flat=True),
            Decimal("0"),
        )
        produzione.quantita_teorica_kg = (
            quantita_per_batch * Decimal(produzione.numero_batch_previsti)
        ).quantize(Decimal("0.001"))
        produzione.save(update_fields=["quantita_teorica_kg"])


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0062_esito_batch_reintegrati")]

    operations = [
        migrations.RunPython(ricalcola_quantita_teoriche, migrations.RunPython.noop),
    ]
