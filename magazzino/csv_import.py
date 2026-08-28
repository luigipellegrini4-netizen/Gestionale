import csv
import io

from django.db import transaction

from .forms import ArticoloForm, FornitoreForm, UbicazioneForm
from .models import Articolo, Fornitore, Ubicazione


CONFIGURAZIONI_CSV = {
    "fornitori": {
        "headers": [
            "codice", "ragione_sociale", "partita_iva", "telefono",
            "email", "indirizzo", "attivo", "note",
        ],
        "model": Fornitore,
        "form": FornitoreForm,
        "key": "codice",
    },
    "ubicazioni": {
        "headers": [
            "nome", "tipo_magazzino", "scaffale", "piano", "attiva",
        ],
        "model": Ubicazione,
        "form": UbicazioneForm,
        "key": "nome",
    },
    "articoli": {
        "headers": [
            "codice", "descrizione", "nome_produzione", "categoria", "unita_misura",
            "quantita_per_confezione", "formato", "unita_formato",
            "scorta_minima",
            "tipo_packaging",
            "pezzi_per_imballo", "attivo",
            "note",
        ],
        "model": Articolo,
        "form": ArticoloForm,
        "key": "codice",
    },
}


def genera_template_csv(tipo):
    configurazione = CONFIGURAZIONI_CSV[tipo]
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(configurazione["headers"])
    return "\ufeff" + output.getvalue()


def _normalizza_booleano(valore):
    valore = valore.strip().lower()
    if valore in {"1", "true", "vero", "si", "sì", "yes"}:
        return "true"
    if valore in {"0", "false", "falso", "no"}:
        return "false"
    return valore


def _errori_form(form):
    errori = []
    for campo, messaggi in form.errors.items():
        etichetta = form.fields[campo].label if campo in form.fields else campo
        errori.extend(f"{etichetta}: {messaggio}" for messaggio in messaggi)
    return errori


def importa_csv(tipo, contenuto):
    if tipo not in CONFIGURAZIONI_CSV:
        raise ValueError("Tipo di importazione non valido.")
    try:
        testo = contenuto.decode("utf-8-sig")
    except UnicodeDecodeError as errore:
        raise ValueError("Il file deve essere codificato in UTF-8.") from errore

    configurazione = CONFIGURAZIONI_CSV[tipo]
    reader = csv.DictReader(io.StringIO(testo), delimiter=";")
    if reader.fieldnames != configurazione["headers"]:
        attese = ";".join(configurazione["headers"])
        raise ValueError(f"Intestazioni CSV non valide. Usa: {attese}")

    righe_preparate = []
    errori = []
    chiavi_viste = set()
    for numero_riga, riga in enumerate(reader, start=2):
        if not any((valore or "").strip() for valore in riga.values()):
            continue
        dati = {chiave: (valore or "").strip() for chiave, valore in riga.items()}
        chiave = dati[configurazione["key"]]
        if not chiave:
            errori.append(f"Riga {numero_riga}: campo chiave obbligatorio.")
            continue
        chiave_normalizzata = chiave.casefold()
        if chiave_normalizzata in chiavi_viste:
            errori.append(f"Riga {numero_riga}: chiave duplicata '{chiave}'.")
            continue
        chiavi_viste.add(chiave_normalizzata)

        campo_attivo = "attiva" if tipo == "ubicazioni" else "attivo"
        dati[campo_attivo] = _normalizza_booleano(dati[campo_attivo])
        if tipo == "articoli":
            dati["quantita_per_confezione"] = dati[
                "quantita_per_confezione"
            ].replace(",", ".")
            dati["formato"] = dati["formato"].replace(",", ".")
            dati["scorta_minima"] = dati["scorta_minima"].replace(",", ".")

        esistente = configurazione["model"].objects.filter(
            **{f"{configurazione['key']}__iexact": chiave}
        ).first()
        form = configurazione["form"](dati, instance=esistente)
        if not form.is_valid():
            errori.extend(
                f"Riga {numero_riga}: {errore}" for errore in _errori_form(form)
            )
        else:
            righe_preparate.append((form, esistente is None))

    if not righe_preparate and not errori:
        errori.append("Il file non contiene righe da importare.")
    if errori:
        return {"errori": errori, "creati": 0, "aggiornati": 0}

    creati = 0
    aggiornati = 0
    with transaction.atomic():
        for form, nuovo in righe_preparate:
            form.save()
            if nuovo:
                creati += 1
            else:
                aggiornati += 1
    return {"errori": [], "creati": creati, "aggiornati": aggiornati}
