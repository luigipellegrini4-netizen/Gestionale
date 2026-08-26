from django.db import DatabaseError
from django.urls import resolve

from .models import Articolo, Fornitore, Giacenza, Lotto, RegistroOperazione, Ubicazione


ETICHETTE = {
    "nuovo_carico": ("Magazzino", "Nuovo carico"),
    "trasferimento": ("Magazzino", "Trasferimento"),
    "consumo": ("Magazzino", "Consumo"),
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


def registra_operazione(*, utente, azione, area, descrizione, request=None, dettagli=None):
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
        )
    except DatabaseError:
        return None


class RegistroOperazioniMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utente = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        response = self.get_response(request)
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return response
        if not utente or response.status_code < 200 or response.status_code >= 400:
            return response
        try:
            match = resolve(request.path_info)
            nome_rotta = match.url_name or "operazione"
        except Exception:
            match = None
            nome_rotta = "operazione"
        area, azione = ETICHETTE.get(
            nome_rotta,
            ("Amministrazione" if request.path.startswith("/admin/") else "MIRA", nome_rotta.replace("_", " ").title()),
        )
        dettagli, elementi = (
            _riepilogo_richiesta(request, match)
            if match is not None
            else ({"rotta": nome_rotta}, [])
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
        )
        return response
