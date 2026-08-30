from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0065_rimuovi_imballi_da_articolo")]

    operations = [
        migrations.RemoveField(
            model_name="ubicazione",
            name="scaffale",
        ),
        migrations.RemoveField(
            model_name="ubicazione",
            name="piano",
        ),
    ]
