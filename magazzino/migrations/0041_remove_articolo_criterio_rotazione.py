from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0040_ricetta_attiva_unica_mysql")]

    operations = [
        migrations.RemoveField(
            model_name="articolo",
            name="criterio_rotazione",
        ),
    ]
