from decimal import Decimal

from django.db import migrations, models


def configura_preset_a_flusso(apps, schema_editor):
    Dipendenza = apps.get_model("produzione_v2", "DipendenzaPassaggio")
    Dipendenza.objects.filter(
        passaggio__linea__codice="RQ-INV-V2",
        passaggio__stazione__codice="INVASETTAMENTO-V2",
        predecessore__stazione__codice="ROBOQBO-V2",
    ).update(modalita="FLUSSO", quantita_minima_avvio=Decimal("0"))


class Migration(migrations.Migration):
    dependencies = [("produzione_v2", "0018_eventoproduzione_hash_evento_and_more")]

    operations = [
        migrations.AddField(
            model_name="dipendenzapassaggio",
            name="modalita",
            field=models.CharField(
                choices=[
                    ("COMPLETAMENTO", "Attendi completamento"),
                    ("FLUSSO", "Avvio su prodotto disponibile"),
                ],
                default="COMPLETAMENTO",
                max_length=15,
            ),
        ),
        migrations.AddField(
            model_name="unitaproduzione",
            name="quantita_origine",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                help_text="Quantità prelevata dall'unità della stazione precedente.",
                max_digits=14,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="dipendenzapassaggio",
            name="quantita_minima_avvio",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("0"),
                help_text="Per il flusso, quantità conforme che rende avviabile la stazione.",
                max_digits=14,
            ),
        ),
        migrations.AddConstraint(
            model_name="dipendenzapassaggio",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita_minima_avvio__gte", 0)),
                name="v2_quantita_minima_flusso_non_negativa",
            ),
        ),
        migrations.AddConstraint(
            model_name="unitaproduzione",
            constraint=models.CheckConstraint(
                condition=models.Q(("quantita_origine__isnull", True)) | models.Q(("quantita_origine__gt", 0)),
                name="v2_quantita_origine_unita_positiva",
            ),
        ),
        migrations.RunPython(configura_preset_a_flusso, migrations.RunPython.noop),
    ]
