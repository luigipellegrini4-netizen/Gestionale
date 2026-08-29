import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0058_produzione_derivata_nc")]

    operations = [
        migrations.AlterField(
            model_name="produzione", name="stato",
            field=models.CharField(choices=[("BOZZA", "Bozza"), ("CONFERMATA", "Confermata"), ("ABORTITA", "Abortita per non conformità")], default="BOZZA", max_length=15),
        ),
        migrations.AlterField(model_name="batchproduzione", name="ora_inizio", field=models.TimeField(blank=True, null=True)),
        migrations.AlterField(model_name="batchproduzione", name="ora_fine", field=models.TimeField(blank=True, null=True)),
        migrations.AlterField(
            model_name="batchproduzione", name="esito_conformita",
            field=models.CharField(blank=True, choices=[("C", "Conforme"), ("NC", "Non conforme"), ("NA", "Non applicabile")], max_length=2),
        ),
        migrations.AlterField(
            model_name="batchproduzione", name="stato",
            field=models.CharField(choices=[("DA_LAVORARE", "Da lavorare"), ("CONFORME", "Conforme"), ("QUARANTENA", "In quarantena"), ("SOSPESO", "Sospeso per NC"), ("SCARTATO", "Scartato"), ("REINTEGRATO", "Reintegrato")], db_index=True, default="CONFORME", max_length=15),
        ),
        migrations.AddField(
            model_name="materialesospesononconformita", name="lotto_recuperato",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="materiali_sospesi_nc", to="magazzino.lotto"),
        ),
        migrations.AddField(
            model_name="produzione", name="quantita_batch_reintegrato_kg",
            field=models.DecimalField(decimal_places=6, default=0, max_digits=12),
        ),
        migrations.AddField(
            model_name="nonconformitalotto", name="numero_batch_origine",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
