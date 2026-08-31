from django.db import migrations, models
import django.db.models.deletion


def popola_lotto_originale(apps, schema_editor):
    Materiale = apps.get_model("magazzino", "MaterialeSospesoNonConformita")
    for materiale in Materiale.objects.select_related("prelievo").iterator():
        materiale.lotto_originale_id = materiale.prelievo.lotto_id
        materiale.save(update_fields=["lotto_originale"])


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0069_aggiungi_categoria_ricambi")]

    operations = [
        migrations.AlterField(
            model_name="batchproduzione",
            name="stato",
            field=models.CharField(
                choices=[
                    ("DA_LAVORARE", "Da lavorare"),
                    ("CONFORME", "Conforme"),
                    ("QUARANTENA", "In quarantena"),
                    ("SOSPESO", "Sospeso per NC"),
                    ("SCARTATO", "Scartato"),
                    ("REINTEGRATO", "Reintegrato"),
                    ("ANNULLATO", "Annullato per non conformità"),
                ],
                db_index=True,
                default="CONFORME",
                max_length=15,
            ),
        ),
        migrations.AddField(
            model_name="materialesospesononconformita",
            name="lotto_originale",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="materiali_recuperati_nc",
                to="magazzino.lotto",
            ),
        ),
        migrations.RunPython(popola_lotto_originale, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="materialesospesononconformita",
            name="descrizione_miscela",
        ),
    ]
