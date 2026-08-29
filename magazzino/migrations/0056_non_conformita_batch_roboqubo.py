import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0055_alter_produzione_options")]

    operations = [
        migrations.AddField(
            model_name="produzione", name="stato_roboqubo",
            field=models.CharField(
                choices=[("NORMALE", "In corso"), ("CON_NC", "In corso con NC aperta"), ("SOSPESA", "Sospesa per NC"), ("CONCLUSA", "Conclusa")],
                db_index=True, default="NORMALE", max_length=15,
            ),
        ),
        migrations.AddField(model_name="produzione", name="invasettamento_congelato", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="produzione", name="lotto_chiusura_provvisoria", field=models.CharField(blank=True, max_length=50)),
        migrations.AddField(model_name="produzione", name="chiusura_invasettamento_provvisoria_il", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="produzione", name="richiede_lotto_ripresa", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="produzione", name="chiusa_per_nc", field=models.BooleanField(default=False)),
        migrations.AddField(
            model_name="batchproduzione", name="stato",
            field=models.CharField(
                choices=[("CONFORME", "Conforme"), ("QUARANTENA", "In quarantena"), ("SOSPESO", "Sospeso per NC"), ("SCARTATO", "Scartato"), ("REINTEGRATO", "Reintegrato")],
                db_index=True, default="CONFORME", max_length=15,
            ),
        ),
        migrations.AddField(model_name="batchproduzione", name="quarantena_il", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="batchproduzione", name="risolto_il", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="nonconformitalotto", name="produzione",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="non_conformita", to="magazzino.produzione"),
        ),
        migrations.AddField(
            model_name="nonconformitalotto", name="batch",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="non_conformita", to="magazzino.batchproduzione"),
        ),
        migrations.AddField(model_name="nonconformitalotto", name="lotto_temporaneo", field=models.CharField(blank=True, max_length=50)),
        migrations.AddField(model_name="nonconformitalotto", name="produzione_puo_proseguire", field=models.BooleanField(blank=True, null=True)),
        migrations.CreateModel(
            name="MaterialeSospesoNonConformita",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantita", models.DecimalField(decimal_places=6, max_digits=12)),
                ("descrizione_miscela", models.CharField(blank=True, max_length=200)),
                ("esito", models.CharField(choices=[("DA_VALUTARE", "Da valutare"), ("RIUTILIZZA", "Riutilizzabile nella stessa produzione"), ("CONSERVA", "Conserva in Magazzino produzione"), ("SCARTA", "Da scartare")], default="DA_VALUTARE", max_length=15)),
                ("nuova_data_scadenza", models.DateField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("non_conformita", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="materiali_sospesi", to="magazzino.nonconformitalotto")),
                ("prelievo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sospensioni_nc", to="magazzino.prelievoproduzione")),
            ],
            options={"ordering": ("prelievo__lotto__articolo__codice", "id")},
        ),
        migrations.AddConstraint(
            model_name="materialesospesononconformita",
            constraint=models.UniqueConstraint(fields=("non_conformita", "prelievo"), name="unico_materiale_sospeso_per_nc"),
        ),
        migrations.AddConstraint(
            model_name="materialesospesononconformita",
            constraint=models.CheckConstraint(condition=models.Q(("quantita__gt", 0)), name="materiale_sospeso_quantita_positiva"),
        ),
        migrations.CreateModel(
            name="LottoUscitaProduzione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provvisorio", models.BooleanField(default=False)),
                ("motivo_separazione", models.TextField(blank=True)),
                ("creato_il", models.DateTimeField(auto_now_add=True)),
                ("lotto", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="uscita_produzione", to="magazzino.lotto")),
                ("non_conformita", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="lotti_uscita", to="magazzino.nonconformitalotto")),
                ("produzione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotti_uscita", to="magazzino.produzione")),
            ],
            options={"ordering": ("creato_il", "id")},
        ),
    ]
