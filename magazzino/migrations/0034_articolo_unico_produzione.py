from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0033_fasi_lotto_tank_produzione")]

    operations = [
        migrations.RemoveField(
            model_name="articolo",
            name="prodotto_finito_collegato",
        ),
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
                    ("PRODOTTO_FINITO", "Prodotto finito"),
                ],
                max_length=25,
            ),
        ),
        migrations.AlterField(
            model_name="produzione",
            name="articolo",
            field=models.ForeignKey(
                limit_choices_to={"categoria": "PRODOTTO_FINITO"},
                on_delete=django.db.models.deletion.PROTECT,
                related_name="produzioni",
                to="magazzino.articolo",
            ),
        ),
    ]
