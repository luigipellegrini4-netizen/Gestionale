from django.db import migrations, models


def normalizza_versioni_e_ricette_attive(apps, schema_editor):
    Ricetta = apps.get_model("magazzino", "Ricetta")
    articolo_ids = Ricetta.objects.values_list("articolo_id", flat=True).distinct()
    for articolo_id in articolo_ids:
        ricette = list(Ricetta.objects.filter(articolo_id=articolo_id).order_by("id"))
        versioni_usate = set()
        prossimo_numero = 1
        for ricetta in ricette:
            versione = str(ricetta.versione)
            if versione in versioni_usate:
                while str(prossimo_numero) in versioni_usate:
                    prossimo_numero += 1
                ricetta.versione = str(prossimo_numero)
                ricetta.save(update_fields=["versione"])
                versione = ricetta.versione
            versioni_usate.add(versione)

        attive = [ricetta for ricetta in ricette if ricetta.attiva]
        for ricetta in attive[:-1]:
            ricetta.attiva = False
            ricetta.save(update_fields=["attiva"])


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0037_tank_batch_senza_limite")]

    operations = [
        migrations.RunPython(
            normalizza_versioni_e_ricette_attive,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="ricetta",
            constraint=models.UniqueConstraint(
                fields=("articolo", "versione"),
                name="unica_versione_ricetta_per_articolo",
            ),
        ),
        migrations.AddConstraint(
            model_name="ricetta",
            constraint=models.UniqueConstraint(
                condition=models.Q(attiva=True),
                fields=("articolo",),
                name="unica_ricetta_attiva_per_articolo",
            ),
        ),
    ]
