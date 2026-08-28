from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0041_remove_articolo_criterio_rotazione")]

    operations = [
        migrations.AddField(
            model_name="tankproduzione",
            name="data_ora_controlli",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="produzione",
            name="data_ora_pastorizzazione",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="produzione",
            name="data_ora_verifica_vuoto",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
