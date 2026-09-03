import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def migra_origini_singole(apps, schema_editor):
    Unita = apps.get_model("produzione_v2", "UnitaProduzione")
    Allocazione = apps.get_model("produzione_v2", "AllocazioneOrigineUnita")
    for unita in Unita.objects.exclude(origine_id=None).exclude(quantita_origine=None).iterator():
        Allocazione.objects.get_or_create(
            origine_id=unita.origine_id,
            destinazione_id=unita.pk,
            defaults={"quantita": unita.quantita_origine},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("produzione_v2", "0019_dipendenza_flusso"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LottoCommerciale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice_proposto", models.CharField(max_length=50)),
                ("codice", models.CharField(max_length=50)),
                ("vasetti_conformi", models.PositiveIntegerField(default=0)),
                ("vasetti_scartati", models.PositiveIntegerField(default=0)),
                ("capsule_scartate", models.PositiveIntegerField(default=0)),
                ("chiuso_il", models.DateTimeField(default=django.utils.timezone.now)),
                ("note", models.TextField(blank=True)),
                ("chiuso_da", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotti_commerciali_v2_chiusi", to=settings.AUTH_USER_MODEL)),
                ("ordine", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotti_commerciali", to="produzione_v2.ordineproduzione")),
            ],
            options={"ordering": ("chiuso_il", "id")},
        ),
        migrations.CreateModel(
            name="ConsuntivoEtichettatura",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("vasetti_conformi", models.PositiveIntegerField()),
                ("vasetti_scartati", models.PositiveIntegerField(default=0)),
                ("etichette_scartate", models.PositiveIntegerField(default=0)),
                ("registrato_il", models.DateTimeField(auto_now_add=True)),
                ("registrato_da", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="consuntivi_etichettatura_v2", to=settings.AUTH_USER_MODEL)),
                ("lotto_commerciale", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="consuntivo_etichettatura", to="produzione_v2.lottocommerciale")),
            ],
        ),
        migrations.CreateModel(
            name="LottoLavorazione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codice", models.CharField(max_length=50)),
                ("stato", models.CharField(choices=[("APERTO", "Aperto"), ("CHIUSO", "Chiuso")], default="APERTO", max_length=8)),
                ("aperto_il", models.DateTimeField(auto_now_add=True)),
                ("chiuso_il", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("aperto_da", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotti_lavorazione_v2_aperti", to=settings.AUTH_USER_MODEL)),
                ("chiuso_da", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="lotti_lavorazione_v2_chiusi", to=settings.AUTH_USER_MODEL)),
                ("ordine", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="lotti_lavorazione", to="produzione_v2.ordineproduzione")),
            ],
            options={"ordering": ("ordine", "aperto_il")},
        ),
        migrations.CreateModel(
            name="AppartenenzaUnitaLotto",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("unita", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="appartenenza_lotto", to="produzione_v2.unitaproduzione")),
                ("lotto_lavorazione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="unita_collegate", to="produzione_v2.lottolavorazione")),
            ],
        ),
        migrations.CreateModel(
            name="OrigineLottoCommerciale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("autorizzazione_eccezione", models.BooleanField(default=False)),
                ("motivazione_eccezione", models.TextField(blank=True)),
                ("autorizzata_da", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="unioni_lotti_v2_autorizzate", to=settings.AUTH_USER_MODEL)),
                ("lotto_commerciale", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="origini_lavorazione", to="produzione_v2.lottocommerciale")),
                ("lotto_lavorazione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="destinazioni_commerciali", to="produzione_v2.lottolavorazione")),
            ],
        ),
        migrations.CreateModel(
            name="AllocazioneOrigineUnita",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantita", models.DecimalField(decimal_places=3, max_digits=14)),
                ("creata_il", models.DateTimeField(auto_now_add=True)),
                ("destinazione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="allocazioni_origine", to="produzione_v2.unitaproduzione")),
                ("origine", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="allocazioni_come_origine", to="produzione_v2.unitaproduzione")),
            ],
            options={
                "ordering": ("destinazione", "id"),
                "constraints": [
                    models.UniqueConstraint(fields=("origine", "destinazione"), name="v2_unica_allocazione_origine_unita"),
                    models.CheckConstraint(condition=models.Q(("quantita__gt", 0)), name="v2_quantita_allocazione_positiva"),
                    models.CheckConstraint(condition=models.Q(("origine", models.F("destinazione")), _negated=True), name="v2_allocazione_unita_non_riflessiva"),
                ],
            },
        ),
        migrations.AddConstraint(model_name="lottocommerciale", constraint=models.UniqueConstraint(fields=("ordine", "codice"), name="v2_unico_lotto_commerciale_ordine")),
        migrations.AddConstraint(model_name="lottolavorazione", constraint=models.UniqueConstraint(fields=("ordine", "codice"), name="v2_unico_lotto_lavorazione_ordine")),
        migrations.AddConstraint(model_name="originelottocommerciale", constraint=models.UniqueConstraint(fields=("lotto_commerciale", "lotto_lavorazione"), name="v2_unica_origine_lotto_commerciale")),
        migrations.RunPython(migra_origini_singole, migrations.RunPython.noop),
    ]
