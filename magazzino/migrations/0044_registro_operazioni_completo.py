import uuid

from django.db import migrations, models


CAMPI_NUOVI = (
    "esito", "modello", "record_id", "oggetto", "valori_precedenti",
    "valori_successivi", "motivazione", "codice_operazione", "user_agent", "errore",
)


def aggiungi_campi_mancanti(apps, schema_editor):
    """Rende la migrazione ripetibile dopo un ALTER parziale di MySQL."""
    RegistroOperazione = apps.get_model("magazzino", "RegistroOperazione")
    with schema_editor.connection.cursor() as cursor:
        presenti = {
            colonna.name
            for colonna in schema_editor.connection.introspection.get_table_description(
                cursor, RegistroOperazione._meta.db_table
            )
        }
    campi = {
        "esito": models.CharField(default="RIUSCITA", max_length=15, db_index=True),
        "modello": models.CharField(blank=True, db_index=True, max_length=100),
        "record_id": models.CharField(blank=True, db_index=True, max_length=100),
        "oggetto": models.CharField(blank=True, max_length=500),
        "valori_precedenti": models.JSONField(blank=True, default=dict),
        "valori_successivi": models.JSONField(blank=True, default=dict),
        "motivazione": models.TextField(blank=True),
        "codice_operazione": models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        "user_agent": models.TextField(blank=True),
        "errore": models.TextField(blank=True),
    }
    for nome in CAMPI_NUOVI:
        if nome not in presenti:
            campo = campi[nome]
            campo.set_attributes_from_name(nome)
            campo.model = RegistroOperazione
            schema_editor.add_field(RegistroOperazione, campo)


def assegna_codici_univoci(apps, schema_editor):
    RegistroOperazione = apps.get_model("magazzino", "RegistroOperazione")
    for operazione in RegistroOperazione.objects.only("pk").iterator():
        RegistroOperazione.objects.filter(pk=operazione.pk).update(
            codice_operazione=uuid.uuid4()
        )


class Migration(migrations.Migration):
    dependencies = [("magazzino", "0043_annullamento_tank")]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="registrooperazione", name="esito",
                    field=models.CharField(
                        choices=[("RIUSCITA", "Riuscita"), ("RIFIUTATA", "Rifiutata"), ("ERRORE", "Errore")],
                        db_index=True, default="RIUSCITA", max_length=15,
                    ),
                ),
                migrations.AddField(model_name="registrooperazione", name="modello", field=models.CharField(blank=True, db_index=True, max_length=100)),
                migrations.AddField(model_name="registrooperazione", name="record_id", field=models.CharField(blank=True, db_index=True, max_length=100)),
                migrations.AddField(model_name="registrooperazione", name="oggetto", field=models.CharField(blank=True, max_length=500)),
                migrations.AddField(model_name="registrooperazione", name="valori_precedenti", field=models.JSONField(blank=True, default=dict)),
                migrations.AddField(model_name="registrooperazione", name="valori_successivi", field=models.JSONField(blank=True, default=dict)),
                migrations.AddField(model_name="registrooperazione", name="motivazione", field=models.TextField(blank=True)),
                migrations.AddField(model_name="registrooperazione", name="codice_operazione", field=models.UUIDField(default=uuid.uuid4, editable=False, null=True)),
                migrations.AddField(model_name="registrooperazione", name="user_agent", field=models.TextField(blank=True)),
                migrations.AddField(model_name="registrooperazione", name="errore", field=models.TextField(blank=True)),
            ],
            database_operations=[
                migrations.RunPython(aggiungi_campi_mancanti, migrations.RunPython.noop)
            ],
        ),
        migrations.RunPython(assegna_codici_univoci, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="registrooperazione", name="codice_operazione",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
