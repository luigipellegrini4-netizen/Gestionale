from django.db import migrations, models


def trasferisci_stato_tank_e_risultati(apps, schema_editor):
    Tank = apps.get_model("magazzino", "TankProduzione")
    Uscita = apps.get_model("magazzino", "LottoUscitaProduzione")
    Produzione = apps.get_model("magazzino", "Produzione")
    Tank.objects.filter(lotto_uscita__isnull=False).update(stato_invasettamento="INVASETTATO")
    for uscita in Uscita.objects.all():
        produzione = Produzione.objects.filter(pk=uscita.produzione_id).first()
        if produzione:
            teorica_intera = produzione.quantita_teorica_kg
            batch_uscita = sum(t.numero_batch for t in uscita.tank.all())
            if teorica_intera is not None and produzione.numero_batch_previsti:
                uscita.quantita_teorica_kg = (
                    teorica_intera * batch_uscita / produzione.numero_batch_previsti
                    if batch_uscita else teorica_intera
                )
            if uscita.quantita_teorica_kg and uscita.quantita_ottenuta_kg:
                uscita.resa_percentuale = (
                    uscita.quantita_ottenuta_kg / uscita.quantita_teorica_kg * 100
                )
            uscita.save(update_fields=["quantita_teorica_kg", "resa_percentuale"])


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0060_stato_invasettamento")]

    operations = [
        migrations.AddField(
            model_name="tankproduzione", name="stato_invasettamento",
            field=models.CharField(
                choices=[("DISPONIBILE", "Disponibile"), ("INVASETTATO", "Invasettato")],
                db_index=True, default="DISPONIBILE", max_length=15,
            ),
        ),
        migrations.AddField(
            model_name="tankproduzione", name="invasettato_il",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="quantita_teorica_kg",
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name="lottouscitaproduzione", name="resa_percentuale",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.RunPython(trasferisci_stato_tank_e_risultati, migrations.RunPython.noop),
        migrations.RemoveField(model_name="tankproduzione", name="lotto_uscita"),
    ]
