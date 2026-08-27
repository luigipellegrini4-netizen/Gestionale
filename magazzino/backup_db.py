import json
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import serializers
from django.db import connection, transaction

from .models import (
    Articolo, Confezionamento, ConsumoConfezionamento, Fornitore,
    Giacenza, Inscatolamento, Lotto, Movimento, PrelievoProduzione,
    PrelievoProduzioneSemilavorato, Produzione, ProduzioneSemilavorato,
    RegistroOperazione, Ricetta, RigaRicetta, TankProduzione, Ubicazione,
)


FORMATO = "MIRA_BACKUP"
VERSIONE = 1
MODELLI = [
    Fornitore, Ubicazione, Articolo, Lotto, Giacenza, Movimento, Ricetta,
    RigaRicetta, Produzione, TankProduzione, PrelievoProduzione,
    ProduzioneSemilavorato,
    PrelievoProduzioneSemilavorato, Confezionamento,
    ConsumoConfezionamento, Inscatolamento,
    RegistroOperazione,
]
MODELLI_AMMESSI = {modello._meta.label_lower for modello in MODELLI}
ORDINE_ELIMINAZIONE = [
    RegistroOperazione, ConsumoConfezionamento, Inscatolamento, Confezionamento,
    PrelievoProduzioneSemilavorato, PrelievoProduzione,
    TankProduzione, ProduzioneSemilavorato, Produzione,
    RigaRicetta, Ricetta, Movimento,
    Giacenza, Lotto, Articolo, Ubicazione, Fornitore,
]


def crea_backup():
    records = []
    conteggi = {}
    utenti = dict(
        get_user_model().objects.values_list("pk", "username")
    )
    for modello in MODELLI:
        queryset = modello.objects.all().order_by("pk")
        dati = json.loads(serializers.serialize("json", queryset))
        if modello in {Movimento, RegistroOperazione}:
            for record in dati:
                campo = "eseguito_da" if modello is Movimento else "utente"
                utente_id = record["fields"].get(campo)
                record["fields"][campo] = utenti.get(utente_id)
        records.extend(dati)
        conteggi[modello._meta.label_lower] = len(dati)

    documento = {
        "formato": FORMATO,
        "versione": VERSIONE,
        "creato_il": datetime.now(timezone.utc).isoformat(),
        "conteggi": conteggi,
        "dati": records,
    }
    return json.dumps(documento, ensure_ascii=False, indent=2)


def _prepara_backup(contenuto):
    try:
        documento = json.loads(contenuto.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as errore:
        raise ValueError("Il file non contiene un JSON valido in UTF-8.") from errore
    if documento.get("formato") != FORMATO or documento.get("versione") != VERSIONE:
        raise ValueError("Formato o versione del backup non supportati.")
    dati = documento.get("dati")
    if not isinstance(dati, list):
        raise ValueError("La sezione dati del backup non è valida.")
    if any(record.get("model") not in MODELLI_AMMESSI for record in dati):
        raise ValueError("Il backup contiene modelli non ammessi.")

    utenti = dict(
        get_user_model().objects.values_list("username", "pk")
    )
    for record in dati:
        if record["model"] in {
            Movimento._meta.label_lower,
            RegistroOperazione._meta.label_lower,
        }:
            campo = (
                "eseguito_da"
                if record["model"] == Movimento._meta.label_lower
                else "utente"
            )
            username = record["fields"].get(campo)
            record["fields"][campo] = utenti.get(username)
    try:
        oggetti = list(serializers.deserialize("json", json.dumps(dati)))
    except Exception as errore:
        raise ValueError(f"Contenuto del backup non valido: {errore}") from errore
    return documento, oggetti


def ripristina_backup(contenuto):
    documento, oggetti = _prepara_backup(contenuto)

    cartella = Path(settings.BASE_DIR) / "backups"
    cartella.mkdir(parents=True, exist_ok=True)
    nome = datetime.now().strftime("mira-pre-ripristino-%Y%m%d-%H%M%S.json")
    (cartella / nome).write_text(crea_backup(), encoding="utf-8")

    with transaction.atomic(), connection.constraint_checks_disabled():
        for modello in ORDINE_ELIMINAZIONE:
            modello.objects.all().delete()
        for oggetto in oggetti:
            oggetto.save(save_m2m=True)
        connection.check_constraints()

    return {
        "backup_precedente": nome,
        "record": len(oggetti),
        "creato_il": documento.get("creato_il"),
    }
