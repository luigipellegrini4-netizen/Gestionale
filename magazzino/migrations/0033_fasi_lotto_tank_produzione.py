from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0032_articolo_quantita_per_confezione")]

    operations = [
        migrations.AddField(
            model_name="lotto",
            name="fase",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Non applicabile"),
                    ("INVASETTATO", "Invasettato"),
                    ("ETICHETTATO", "Etichettato"),
                    ("INSCATOLATO", "Inscatolato"),
                ],
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="produzione",
            name="pastorizzazione_completata",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="produzione",
            name="vuoto_controllato",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="TankProduzione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveSmallIntegerField()),
                ("numero_batch", models.PositiveSmallIntegerField()),
                ("gradi_brix", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ("ph", models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                ("produzione", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tank", to="magazzino.produzione")),
            ],
            options={"ordering": ["numero"]},
        ),
        migrations.AddField(
            model_name="prelievoproduzione",
            name="tank",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="prelievi", to="magazzino.tankproduzione"),
        ),
        migrations.AddConstraint(
            model_name="tankproduzione",
            constraint=models.UniqueConstraint(fields=("produzione", "numero"), name="unico_numero_tank_per_produzione"),
        ),
        migrations.AddConstraint(
            model_name="tankproduzione",
            constraint=models.CheckConstraint(condition=models.Q(numero_batch__gte=1, numero_batch__lte=5), name="tank_numero_batch_da_uno_a_cinque"),
        ),
        migrations.AddConstraint(
            model_name="tankproduzione",
            constraint=models.CheckConstraint(condition=models.Q(gradi_brix__isnull=True) | models.Q(gradi_brix__gte=0), name="tank_brix_non_negativo"),
        ),
        migrations.AddConstraint(
            model_name="tankproduzione",
            constraint=models.CheckConstraint(condition=models.Q(ph__isnull=True) | models.Q(ph__gte=0, ph__lte=14), name="tank_ph_valido"),
        ),
    ]
