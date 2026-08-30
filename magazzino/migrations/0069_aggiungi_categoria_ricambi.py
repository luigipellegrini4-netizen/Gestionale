from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0068_quantita_nc_per_unita")]

    operations = [
        migrations.AlterField(
            model_name="articolo",
            name="categoria",
            field=models.CharField(
                choices=[
                    ("MATERIA_PRIMA", "Materia prima"),
                    ("MOCA", "MOCA"),
                    ("IGIENE", "Igiene"),
                    ("SEMILAVORATO", "Semilavorato"),
                    ("PACKAGING", "Packaging"),
                    ("CONSUMABILI", "Consumabili"),
                    ("RICAMBI", "Ricambi"),
                    ("PRODOTTO_FINITO", "Prodotto finito"),
                ],
                max_length=25,
            ),
        ),
    ]
