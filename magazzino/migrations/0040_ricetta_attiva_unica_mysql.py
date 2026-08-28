from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0039_formato_articolo_resa_produzione")]

    operations = [
        migrations.RemoveConstraint(
            model_name="ricetta",
            name="unica_ricetta_attiva_per_articolo",
        ),
        migrations.AddField(
            model_name="ricetta",
            name="articolo_ricetta_attiva",
            field=models.GeneratedField(
                blank=True,
                db_persist=True,
                editable=False,
                expression=models.Case(
                    models.When(attiva=True, then=models.F("articolo")),
                    default=models.Value(None),
                ),
                output_field=models.BigIntegerField(),
                unique=True,
            ),
        ),
    ]
