from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0034_articolo_unico_produzione")]

    operations = [
        migrations.AddField(
            model_name="ubicazione",
            name="ubicazione_padre",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sotto_ubicazioni",
                to="magazzino.ubicazione",
            ),
        ),
        migrations.AddConstraint(
            model_name="ubicazione",
            constraint=models.UniqueConstraint(
                fields=("ubicazione_padre", "scaffale", "piano"),
                name="unica_posizione_in_ubicazione",
            ),
        ),
    ]
