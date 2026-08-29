from django.db import migrations, models


def valorizza_stato_invasettamento(apps, schema_editor):
    Produzione = apps.get_model("magazzino", "Produzione")
    Produzione.objects.filter(stato="CONFERMATA").update(stato_invasettamento="CONCLUSO")
    Produzione.objects.filter(
        stato="BOZZA", moca_igienizzati=True,
    ).update(stato_invasettamento="IN_CORSO")
    Produzione.objects.filter(
        stato="BOZZA", invasettamento_congelato=True,
    ).update(stato_invasettamento="CONGELATO")


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0059_batch_pianificati_e_materiali_nc")]

    operations = [
        migrations.AddField(
            model_name="produzione",
            name="stato_invasettamento",
            field=models.CharField(
                choices=[
                    ("NON_AVVIATO", "Non avviato"),
                    ("IN_CORSO", "In corso"),
                    ("CONGELATO", "Congelato per NC"),
                    ("CONCLUSO", "Concluso"),
                ],
                db_index=True,
                default="NON_AVVIATO",
                max_length=15,
            ),
        ),
        migrations.RunPython(valorizza_stato_invasettamento, migrations.RunPython.noop),
    ]
