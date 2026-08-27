from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0035_ubicazione_padre")]

    operations = [
        migrations.RemoveConstraint(
            model_name="ubicazione",
            name="unica_posizione_in_ubicazione",
        ),
        migrations.RemoveField(
            model_name="ubicazione",
            name="ubicazione_padre",
        ),
        migrations.RemoveConstraint(
            model_name="giacenza",
            name="unica_giacenza_lotto_ubicazione",
        ),
        migrations.AddField(
            model_name="giacenza",
            name="scaffale",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="giacenza",
            name="piano",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="giacenza",
            constraint=models.UniqueConstraint(
                fields=("lotto", "ubicazione", "scaffale", "piano"),
                name="unica_giacenza_lotto_ubicazione",
            ),
        ),
        migrations.AddField(
            model_name="movimento",
            name="scaffale_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="movimento",
            name="piano_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="movimento",
            name="scaffale_destinazione",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="movimento",
            name="piano_destinazione",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prelievoproduzione",
            name="scaffale_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prelievoproduzione",
            name="piano_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prelievoproduzionesemilavorato",
            name="scaffale_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="prelievoproduzionesemilavorato",
            name="piano_origine",
            field=models.CharField(blank=True, default="", max_length=30),
            preserve_default=False,
        ),
    ]
