import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0057_lotto_definitivo_parziale_nc")]

    operations = [
        migrations.AddField(
            model_name="produzione", name="derivata_da",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="produzioni_derivate", to="magazzino.produzione"),
        ),
        migrations.AddField(
            model_name="produzione", name="bloccata_da_nc",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="produzioni_bloccate", to="magazzino.nonconformitalotto"),
        ),
        migrations.AddField(
            model_name="prelievoproduzione", name="quantita_trasferita_nc",
            field=models.DecimalField(decimal_places=6, default=0, help_text="Quota trasferita a una nuova produzione in seguito a NC.", max_digits=12),
        ),
    ]
