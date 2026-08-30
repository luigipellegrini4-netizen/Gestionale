from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0066_rimuovi_posizione_da_ubicazione")]

    operations = [
        migrations.AlterField(
            model_name="produzione",
            name="fase",
            field=models.CharField(
                choices=[
                    ("PREPARAZIONE", "Preparazione"),
                    ("ROBOQUBO", "RoboQbo"),
                    ("INVASETTAMENTO", "Invasettamento"),
                    ("COMPLETATA", "Completata"),
                ],
                default="PREPARAZIONE",
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name="produzione",
            options={
                "permissions": [
                    ("operare_roboqubo", "Può registrare i cicli RoboQbo"),
                    ("operare_invasettamento", "Può registrare l'invasettamento"),
                    ("gestire_produzioni", "Può verificare e correggere le produzioni"),
                ],
            },
        ),
    ]
