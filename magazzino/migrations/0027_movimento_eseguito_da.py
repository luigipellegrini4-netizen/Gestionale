from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0026_vincoli_quantita_magazzino"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="movimento",
            name="eseguito_da",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="movimenti_magazzino",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
