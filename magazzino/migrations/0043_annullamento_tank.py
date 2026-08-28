from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("magazzino", "0042_timestamp_controlli_produzione"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(model_name="tankproduzione", name="annullato", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tankproduzione", name="motivo_annullamento", field=models.TextField(blank=True)),
        migrations.AddField(model_name="tankproduzione", name="data_ora_annullamento", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(
            model_name="tankproduzione",
            name="annullato_da",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="tank_produzione_annullati", to=settings.AUTH_USER_MODEL),
        ),
    ]
