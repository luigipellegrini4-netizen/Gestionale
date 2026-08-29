import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0056_non_conformita_batch_roboqubo")]

    operations = [
        migrations.RemoveField(model_name="produzione", name="lotto_chiusura_provvisoria"),
        migrations.RemoveField(model_name="produzione", name="chiusura_invasettamento_provvisoria_il"),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="numero_vasetti_buoni",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="numero_vasetti_scartati",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="numero_capsule_difettose",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="peso_netto_vasetto_g",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="quantita_ottenuta_kg",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="note",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="tankproduzione", name="lotto_uscita",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tank", to="magazzino.lottouscitaproduzione"),
        ),
        migrations.AddField(
            model_name="carrelloproduzione", name="lotto_uscita",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="carrelli", to="magazzino.lottouscitaproduzione"),
        ),
    ]
