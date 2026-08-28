from django.db import DatabaseError
from django.urls import resolve
from datetime import date, datetime
from decimal import Decimal

from .models import (
    Articolo, Fornitore, Giacenza, Lotto, RegistroOperazione, Ubicazione,
    Ricetta, RigaRicetta, Produzione, ProduzioneSemilavorato, TankProduzione,
    NonConformitaLotto,
)


ETICHETTE = {
    "nuovo_carico": ("Magazzino", "Nuovo carico"),
    "trasferimento": ("Magazzino", "Trasferimento"),
    "consumo": ("Magazzino", "Scarico materiale di consumo"),
    "nuovo_articolo": ("Anagrafiche", "Creazione articolo"),
    "modifica_articolo": ("Anagrafiche", "Modifica articolo"),
    "nuovo_fornitore": ("Anagrafiche", "Creazione fornitore"),
    "modifica_fornitore": ("Anagrafiche", "Modifica fornitore"),
    "nuova_ubicazione": ("Anagrafiche", "Creazione ubicazione"),
    "modifica_ubicazione": ("Anagrafiche", "Modifica ubicazione"),
    "importazione_csv": ("Amministrazione", "Importazione CSV"),
    "nuova_ricetta": ("Ricette", "Creazione ricetta"),
    "modifica_ricetta": ("Ricette", "Modifica ricetta"),
    "aggiungi_riga_ricetta": ("Ricette", "Aggiunta ingrediente"),
    "modifica_riga_ricetta": ("Ricette", "Modifica ingrediente"),
    "elimina_riga_ricetta": ("Ricette", "Eliminazione ingrediente"),
    "nuova_produzione": ("Produzione", "Apertura produzione"),
    "gestione_produzione": ("Produzione", "Operazione produzione"),
    "elimina_produzione": ("Produzione", "Eliminazione produzione"),
    "nuova_produzione_semilavorato": ("Produzione", "Apertura semilavorato"),
    "gestione_produzione_semilavorato": ("Produzione", "Operazione semilavorato"),
    "elimina_produzione_semilavorato": ("Produzione", "Eliminazione semilavorato"),
    "nuovo_confezionamento": ("Packaging", "Confezionamento"),
    "nuovo_inscatolamento": ("Packaging", "Inscatolamento"),
    "gestione_backup": ("Amministrazione", "Ripristino backup"),
    "logout": ("Utente", "Logout"),
    "modifica_tank": ("Produzione", "Modifica tank"),
    "annulla_tank": ("Produzione", "Annullamento tank"),
    "registra_pastorizzazione": ("Produzione", "Verifica pastorizzazione"),
    "registra_verifica_vuoto": ("Produzione", "Verifica sottovuoto"),
    "apri_non_conformita": ("Qualità", "Apertura non conformità lotto"),
    "apri_non_conformita_generale": ("Qualità", "Apertura non conformità"),
    "gestisci_non_conformita": ("Qualità", "Gestione non conformità lotto"),
}

MODELLI_ROTTE = {
    "modifica_articolo": Articolo,
    "modifica_fornitore": Fornitore,
    "modifica_ubicazione": Ubicazione,
    "modifica_ricetta": Ricetta,
    "modifica_riga_ricetta": RigaRicetta,
    "elimina_riga_ricetta": RigaRicetta,
    "gestione_produzione": Produzione,
    "elimina_produzione": Produzione,
    "gestione_produzione_semilavorato": ProduzioneSemilavorato,
    "elimina_produzione_semilavorato": ProduzioneSemilavorato,
    "modifica_tank": TankProduzione,
    "annulla_tank": TankProduzione,
    "apri_non_conformita": Lotto,
    "gestisci_non_conformita": NonConformitaLotto,
}

AZIONI_POST = {
    "apri_tank": "Apertura tank",
    "registra_ingredienti_tank": "Registrazione prelievi tank",
    "registra_scarti_tank": "Registrazione scarti tank",
    "controlla_tank": "Registrazione °Brix e pH",
    "registra_pastorizzazione": "Verifica pastorizzazione",
    "registra_verifica_vuoto": "Verifica sottovuoto",
    "conferma_produzione": "Conferma produzione",
}

ETICHETTE_CAMPI = {
    "articolo": "Articolo",
    "codice": "Codice",
    "codice_lotto": "Codice lotto",
    "ragione_sociale": "Ragione sociale",
    "lotto": "Lotto",
    "giacenza": "Lotto e posizione",
    "fornitore": "Fornitore",
    "ubicazione": "Ubicazione",
    "ubicazione_origine": "Origine",
    "ubicazione_destinazione": "Destinazione",
    "quantita": "Quantità",
    "quantita_richiesta": "Quantità richiesta",
    "quantita_prodotta": "Quantità prodotta",
    "quantita_scarto": "Scarto",
    "data_produzione": "Data produzione",
    "data_arrivo": "Data arrivo",
    "data_scadenza": "Data scadenza",
    "tipo": "Tipo",
    "azione": "Azione",
    "nome": "Nome",
    "descrizione": "Descrizione",
    "note": "Note",
    "file_csv": "File CSV",
    "file_json": "File backup",
}

CAMPI_SENSIBILI = {"csrfmiddlewaretoken", "password", "secret", "token"}


def _json_value(valore):
    if valore is None or isinstance(valore, (str, int, float, bool)):
        return valore
    if isinstance(valore, (date, datetime, Decimal)):
        return str(valore)
    return str(valore)


def _fotografia_oggetto(modello, pk):
    if modello is None or pk is None:
        return None, {}, ""
    oggetto = modello.objects.filter(pk=pk).first()
    if oggetto is None:
        return None, {}, ""
    dati = {}
    for campo in oggetto._meta.concrete_fields:
        if campo.name.lower() in CAMPI_SENSIBILI or campo.name == "password":
            continue
        valore = getattr(oggetto, campo.attname)
        dati[campo.name] = _json_value(valore)
    return oggetto, dati, str(oggetto)[:500]


def _valore_leggibile(campo, valore):
    if not valore:
        return "—"
    modelli = {
        "articolo": Articolo,
        "fornitore": Fornitore,
        "giacenza": Giacenza,
    }
    if campo.startswith("lotto"):
        modello = Lotto
    elif campo.startswith("ubicazione"):
        modello = Ubicazione
    else:
        modello = modelli.get(campo)
    if modello and str(valore).isdigit():
        oggetto = modello.objects.filter(pk=valore).first()
        if oggetto is not None:
            return str(oggetto)
    return str(valore)


def _riepilogo_richiesta(request, match):
    dettagli = {"rotta": match.url_name or "operazione"}
    if match.kwargs:
        dettagli["record"] = match.kwargs
    elementi = []
    for campo, valori in request.POST.lists():
        campo_minuscolo = campo.lower()
        if (
            campo_minuscolo in CAMPI_SENSIBILI
            or campo.startswith("_")
            or campo.endswith(("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"))
        ):
            continue
        valore = ", ".join(_valore_leggibile(campo, v) for v in valori)
        valore = valore[:200]
        etichetta = ETICHETTE_CAMPI.get(campo, campo.replace("_", " ").title())
        dettagli[campo] = valore
        elementi.append(f"{etichetta}: {valore}")
    for campo, file_caricato in request.FILES.items():
        dettagli[campo] = file_caricato.name
        elementi.append(
            f"{ETICHETTE_CAMPI.get(campo, campo)}: {file_caricato.name}"
        )
    if not elementi and match.kwargs:
        elementi.append(
            ", ".join(f"{chiave}: {valore}" for chiave, valore in match.kwargs.items())
        )
    return dettagli, elementi[:12]


def registra_operazione(
    *, utente, azione, area, descrizione, request=None, dettagli=None,
    esito=RegistroOperazione.Esito.RIUSCITA, modello="", record_id="",
    oggetto="", valori_precedenti=None, valori_successivi=None,
    motivazione="", errore="",
):
    ip = None
    metodo = ""
    percorso = ""
    if request is not None:
        ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        ip = ip or request.META.get("REMOTE_ADDR")
        metodo = request.method
        percorso = request.path
    try:
        return RegistroOperazione.objects.create(
            utente=utente if getattr(utente, "is_authenticated", False) else None,
            azione=azione,
            area=area,
            descrizione=descrizione,
            metodo=metodo,
            percorso=percorso,
            indirizzo_ip=ip,
            dettagli=dettagli or {},
            esito=esito,
            modello=modello,
            record_id=str(record_id or ""),
            oggetto=oggetto,
            valori_precedenti=valori_precedenti or {},
            valori_successivi=valori_successivi or {},
            motivazione=motivazione,
            user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
            errore=errore,
        )
    except DatabaseError:
        return None


class RegistroOperazioniMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utente = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        mutazione = request.method in {"POST", "PUT", "PATCH", "DELETE"}
        try:
            match = resolve(request.path_info)
            nome_rotta = match.url_name or "operazione"
        except Exception:
            match = None
            nome_rotta = "operazione"
        modello = MODELLI_ROTTE.get(nome_rotta) if mutazione else None
        pk = match.kwargs.get("pk") if match is not None else None
        oggetto_prima, valori_prima, nome_oggetto = _fotografia_oggetto(modello, pk)
        try:
            response = self.get_response(request)
        except Exception as eccezione:
            if mutazione and utente:
                area, azione = ETICHETTE.get(nome_rotta, ("MIRA", nome_rotta.replace("_", " ").title()))
                registra_operazione(
                    utente=utente, azione=azione, area=area,
                    descrizione=f"{azione} non riuscita", request=request,
                    esito=RegistroOperazione.Esito.ERRORE,
                    modello=modello._meta.label_lower if modello else "",
                    record_id=pk, oggetto=nome_oggetto,
                    valori_precedenti=valori_prima, errore=str(eccezione)[:2000],
                )
            raise
        if not mutazione or not utente:
            return response
        area, azione = ETICHETTE.get(
            nome_rotta,
            ("Amministrazione" if request.path.startswith("/admin/") else "MIRA", nome_rotta.replace("_", " ").title()),
        )
        azione = AZIONI_POST.get(request.POST.get("azione"), azione)
        dettagli, elementi = (
            _riepilogo_richiesta(request, match)
            if match is not None
            else ({"rotta": nome_rotta}, [])
        )
        oggetto_dopo, valori_dopo, nome_dopo = _fotografia_oggetto(modello, pk)
        esito = (
            RegistroOperazione.Esito.RIUSCITA
            if 200 <= response.status_code < 400
            else RegistroOperazione.Esito.RIFIUTATA
        )
        descrizione = azione
        if elementi:
            descrizione = f"{azione} — " + "; ".join(elementi)
        registra_operazione(
            utente=utente,
            azione=azione,
            area=area,
            descrizione=descrizione,
            request=request,
            dettagli=dettagli,
            esito=esito,
            modello=modello._meta.label_lower if modello else "",
            record_id=pk,
            oggetto=nome_dopo or nome_oggetto,
            valori_precedenti=valori_prima,
            valori_successivi=valori_dopo,
            motivazione=(request.POST.get("motivo") or request.POST.get("note") or "")[:2000],
            errore="" if esito == RegistroOperazione.Esito.RIUSCITA else f"HTTP {response.status_code}",
        )
        return response
