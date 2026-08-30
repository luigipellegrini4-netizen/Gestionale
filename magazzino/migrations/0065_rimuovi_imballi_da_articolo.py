from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0064_rimuovi_formato_da_articolo")]

    operations = [
        migrations.RemoveConstraint(
            model_name="articolo",
            name="articolo_quantita_confezione_positiva",
        ),
        migrations.RemoveField(
            model_name="articolo",
            name="quantita_per_confezione",
        ),
        migrations.RemoveField(
            model_name="articolo",
            name="pezzi_per_imballo",
        ),
        migrations.AddField(
            model_name="lotto",
            name="capacita_imballo",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Numero di prodotti contenuti nella singola scatola o cofanetto.",
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="lotto",
            constraint=models.CheckConstraint(
                condition=models.Q(capacita_imballo__isnull=True)
                | models.Q(capacita_imballo__gt=0),
                name="lotto_capacita_imballo_positiva",
            ),
        ),
    ]
