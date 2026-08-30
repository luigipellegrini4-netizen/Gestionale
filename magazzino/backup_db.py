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
    BatchProduzione, CarrelloProduzione, NonConformitaLotto,
    LottoUscitaProduzione, MaterialeSospesoNonConformita,
)


FORMATO = "MIRA_BACKUP"
VERSIONE = 1
MODELLI = [
    Fornitore, Ubicazione, Articolo, Lotto, NonConformitaLotto,
    Giacenza, Movimento, Ricetta,
    RigaRicetta, Produzione, TankProduzione, PrelievoProduzione,
    BatchProduzione, MaterialeSospesoNonConformita,
    LottoUscitaProduzione, CarrelloProduzione,
    ProduzioneSemilavorato,
    PrelievoProduzioneSemilavorato, Confezionamento,
    ConsumoConfezionamento, Inscatolamento,
    RegistroOperazione,
]
MODELLI_AMMESSI = {modello._meta.label_lower for modello in MODELLI}
MODELLI_PER_ETICHETTA = {
    modello._meta.label_lower: modello for modello in MODELLI
}
ORDINE_ELIMINAZIONE = [
    RegistroOperazione, MaterialeSospesoNonConformita,
    CarrelloProduzione, BatchProduzione, TankProduzione,
    LottoUscitaProduzione, NonConformitaLotto,
    ConsumoConfezionamento, Inscatolamento, Confezionamento,
    PrelievoProduzioneSemilavorato, PrelievoProduzione,
    ProduzioneSemilavorato, Produzione,
    RigaRicetta, Ricetta, Movimento,
    Giacenza, Lotto, Articolo, Ubicazione, Fornitore,
]


def svuota_dati_magazzino():
    """Elimina i dati MIRA conservando autenticazione, utenti e permessi."""
    conteggi = {
        modello._meta.label_lower: modello.objects.count()
        for modello in ORDINE_ELIMINAZIONE
    }
    with transaction.atomic():
        # Le produzioni derivate e le NC formano collegamenti PROTECT circolari,
        # tutti opzionali: li sciogliamo prima della cancellazione.
        Produzione.objects.update(derivata_da=None, bloccata_da_nc=None)
        NonConformitaLotto.objects.update(produzione=None, batch=None)
        for modello in ORDINE_ELIMINAZIONE:
            modello.objects.all().delete()
    return conteggi

CAMPI_UTENTE = {
    Movimento._meta.label_lower: ("eseguito_da",),
    RegistroOperazione._meta.label_lower: ("utente",),
    Produzione._meta.label_lower: ("moca_igienizzati_da",),
    TankProduzione._meta.label_lower: ("annullato_da",),
    BatchProduzione._meta.label_lower: ("registrato_da",),
    CarrelloProduzione._meta.label_lower: ("registrato_da",),
    NonConformitaLotto._meta.label_lower: ("aperta_da", "gestita_da"),
}


def crea_backup():
    records = []
    conteggi = {}
    utenti = dict(
        get_user_model().objects.values_list("pk", "username")
    )
    for modello in MODELLI:
        queryset = modello.objects.all().order_by("pk")
        dati = json.loads(serializers.serialize("json", queryset))
        if modello._meta.label_lower in CAMPI_UTENTE:
            for record in dati:
                for campo in CAMPI_UTENTE[modello._meta.label_lower]:
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
    if any(not isinstance(record, dict) for record in dati):
        raise ValueError("La sezione dati contiene record non validi.")
    if any(record.get("model") not in MODELLI_AMMESSI for record in dati):
        raise ValueError("Il backup contiene modelli non ammessi.")

    utenti = dict(
        get_user_model().objects.values_list("username", "pk")
    )
    for record in dati:
        fields = record.get("fields")
        if not isinstance(fields, dict):
            raise ValueError(
                f"Il record {record.get('model', 'sconosciuto')} non contiene campi validi."
            )
        modello = MODELLI_PER_ETICHETTA[record["model"]]
        campi_correnti = {
            campo.name
            for campo in modello._meta.get_fields()
            if campo.concrete and not campo.auto_created and not campo.primary_key
        }
        # Compatibilità in avanti: i vecchi backup possono contenere campi
        # eliminati intenzionalmente dalle versioni successive di MIRA.
        record["fields"] = {
            nome: valore for nome, valore in fields.items()
            if nome in campi_correnti
        }
        if record["model"] == TankProduzione._meta.label_lower:
            vecchio_lotto_uscita = record["fields"].pop("lotto_uscita", None)
            record["fields"].setdefault(
                "stato_invasettamento",
                "INVASETTATO" if vecchio_lotto_uscita else "DISPONIBILE",
            )
        if record["model"] in CAMPI_UTENTE:
            for campo in CAMPI_UTENTE[record["model"]]:
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

    try:
        with transaction.atomic(), connection.constraint_checks_disabled():
            # I collegamenti tra produzione, NC e produzione derivata sono
            # opzionali ma PROTECT: devono essere sciolti prima di svuotare.
            Produzione.objects.update(derivata_da=None, bloccata_da_nc=None)
            NonConformitaLotto.objects.update(produzione=None, batch=None)
            for modello in ORDINE_ELIMINAZIONE:
                modello.objects.all().delete()
            for oggetto in oggetti:
                oggetto.save(save_m2m=True)
            connection.check_constraints()
    except Exception as errore:
        raise ValueError(
            f"Ripristino non riuscito; il database non è stato modificato: {errore}"
        ) from errore

    return {
        "backup_precedente": nome,
        "record": len(oggetti),
        "creato_il": documento.get("creato_il"),
    }
