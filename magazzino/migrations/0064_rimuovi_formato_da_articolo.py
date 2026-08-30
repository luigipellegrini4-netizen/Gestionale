from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0063_ricalcola_quantita_teoriche_produzioni")]

    operations = [
        migrations.RemoveConstraint(
            model_name="articolo",
            name="articolo_formato_positivo",
        ),
        migrations.RemoveConstraint(
            model_name="articolo",
            name="articolo_formato_unita_coerenti",
        ),
        migrations.RemoveField(
            model_name="articolo",
            name="formato",
        ),
        migrations.RemoveField(
            model_name="articolo",
            name="unita_formato",
        ),
    ]
