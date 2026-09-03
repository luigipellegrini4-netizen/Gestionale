from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0070_materiali_nc_tracciabilita")]
    operations = [
        migrations.AlterField(
            model_name="nonconformitalotto", name="stato",
            field=models.CharField(max_length=20, db_index=True, default="APERTA",
                choices=[("APERTA", "Aperta"), ("BOZZA", "Bozza"),
                         ("IN_LAVORAZIONE", "In lavorazione"), ("CHIUSA", "Chiusa")]),
        ),
    ]
