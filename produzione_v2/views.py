import csv

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse

from .forms import (
    AbilitazioneOperatoreForm, AllocazioneOrigineForm, AperturaNonConformitaForm,
    AssegnazioneOperatoreForm,
    ChiusuraNonConformitaForm,
    CicloProduzioneForm, DefinizioneControlloForm, LineaProduzioneForm, OrdineProduzioneForm,
    DipendenzaPassaggioForm, PassaggioLineaForm, PrenotazioneMaterialeForm, StazioneLavoroForm,
    BatchRoboQboForm, ChiusuraLottoCommercialeForm, ConsuntivoEtichettaturaForm,
    ImpegnoRisorsaForm, LottoLavorazioneForm, OutputProduzioneForm,
    RiversamentoTankForm, RisorsaProduzioneForm, TankRoboQboForm,
    RegolaControlloCicloForm, TipoUnitaProduzioneForm, TurnoLineaForm,
    UnitaProduzioneForm, ReportProduzioneForm,
)
from .models import AssegnazioneOperatore, CicloProduzione, ConsumoMateriale, FaseProduzione, ImpegnoRisorsa, LineaProduzione, LottoLavorazione, NonConformita, OrdineProduzione, OutputProduzione, StazioneLavoro, TipoUnitaProduzione, UnitaProduzione
from .services import (
    aggiungi_dipendenza, aggiungi_origine_unita, apri_lotto_lavorazione,
    apri_non_conformita, assegna_esito_unita,
    assegna_operatore, avvia_fase, avvia_ordine,
    avvia_unita, chiudi_lotto_commerciale, chiudi_lotto_lavorazione,
    chiudi_non_conformita, crea_unita,
    completa_fase, completa_ordine,
    consuma_materiale, consuma_materiali_prenotati, prepara_ordine,
    prenota_materiale, proponi_codice_lotto_commerciale, registra_controllo,
    registra_consuntivo_etichettatura,
    impegna_risorsa, collega_unita_lotto, registra_output,
    reintegra_materiale, rilascia_risorsa,
    annulla_ordine, riprendi_fase, riprendi_ordine, salta_fase, scarta_materiale,
    sospendi_ordine, termina_assegnazione,
)
from .traceability import CatenaTracciabilita
from .presets import PresetRoboQboInvasettamento
from .material_planning import PianificatoreMaterialiFEFO
from .attention import CentroAttenzioneProduzione
from .operator_queue import CodaLavoroOperatore
from .readiness import ValutatoreProntezzaOrdine
from .reporting import ReportProduzione


def dashboard(request):
    contesto = {
        "ordini": OrdineProduzione.objects.select_related(
            "linea", "prodotto",
        ).prefetch_related("fasi__passaggio__stazione", "fasi__passaggio__dipendenze")[:50],
        "linee": LineaProduzione.objects.prefetch_related("passaggi")[:20],
        "cicli": CicloProduzione.objects.select_related("prodotto", "linea", "ricetta")[:30],
    }
    contesto.update(CentroAttenzioneProduzione().dati())
    return render(request, "produzione_v2/dashboard.html", contesto)


POSTAZIONI_MARMELLATE = {
    "a": {
        "sigla": "A", "nome": "Semilavorati", "colore": "verde",
        "descrizione": "Prepara i semilavorati da ricetta e li rende disponibili a RoboQbo.",
        "stazioni": ("SEMILAVORATI-V2",),
    },
    "b": {
        "sigla": "B", "nome": "RoboQbo", "colore": "arancio",
        "descrizione": "Preleva i materiali, apre il lotto, produce batch e riempie i tank.",
        "stazioni": ("ROBOQBO-V2",),
    },
    "c": {
        "sigla": "C", "nome": "Riempimento e trattamento", "colore": "blu",
        "descrizione": "Invasetta e segue ogni carrello fino a vuoto e lotto definitivo.",
        "stazioni": (
            "INVASETTAMENTO-V2", "PASTORIZZAZIONE-V2", "ABBATTIMENTO-V2",
            "VUOTO-V2", "CHIUSURA-C-V2",
        ),
    },
    "d": {
        "sigla": "D", "nome": "Etichettatura", "colore": "viola",
        "descrizione": "Lavora i lotti definitivi rilasciati da C e registra il consuntivo.",
        "stazioni": ("ETICHETTATURA-V2",),
    },
}


@permission_required("produzione_v2.operare_produzione_v2", raise_exception=True)
def postazioni(request):
    return render(request, "produzione_v2/postazioni.html", {
        "postazioni": POSTAZIONI_MARMELLATE.values(),
    })


@permission_required("produzione_v2.operare_produzione_v2", raise_exception=True)
def postazione_operatore(request, ruolo):
    configurazione = POSTAZIONI_MARMELLATE.get(ruolo.lower())
    if configurazione is None:
        raise ValidationError("Postazione operatore non riconosciuta.")
    fasi = list(FaseProduzione.objects.select_related(
        "ordine__prodotto", "ordine__linea", "passaggio__stazione",
    ).prefetch_related(
        "unita__tipo_definizione", "assegnazioni__operatore",
        "impegni_risorse__risorsa",
    ).filter(
        passaggio__stazione__codice__in=configurazione["stazioni"],
        ordine__stato__in=(
            OrdineProduzione.Stato.PRONTO, OrdineProduzione.Stato.IN_CORSO,
            OrdineProduzione.Stato.SOSPESO, OrdineProduzione.Stato.BLOCCATO_NC,
        ),
    ).order_by("ordine__priorita", "ordine__pianificato_per", "ordine_id", "sequenza"))
    for fase in fasi:
        fase.unita_pronte = [
            unita for unita in fase.unita.all()
            if unita.stato in (UnitaProduzione.Stato.CONFORME, UnitaProduzione.Stato.REINTEGRATA)
        ]
    return render(request, "produzione_v2/postazione_operatore.html", {
        "postazione": configurazione, "ruolo": ruolo.lower(), "fasi": fasi,
    })


@permission_required("produzione_v2.operare_produzione_v2", raise_exception=True)
def lavorazione_roboqbo(request, ordine_pk):
    ordine = get_object_or_404(
        OrdineProduzione.objects.select_related("prodotto", "linea"), pk=ordine_pk,
    )
    fase = get_object_or_404(
        ordine.fasi.select_related("passaggio__stazione"),
        passaggio__stazione__codice="ROBOQBO-V2",
    )
    articoli_ammessi = list(ordine.fabbisogni.values_list("articolo_id", flat=True))
    if not articoli_ammessi and ordine.ciclo_id and ordine.ciclo.ricetta_id:
        articoli_ammessi = list(
            ordine.ciclo.ricetta.righe.values_list("articolo_id", flat=True)
        )
    if request.method == "POST":
        azione = request.POST.get("azione")
        try:
            if azione == "avvia_fase":
                avvia_fase(fase, request.user)
                messages.success(request, "RoboQbo avviata: ora puoi aprire il lotto di lavorazione.")
            elif azione == "apri_lotto":
                form = LottoLavorazioneForm(request.POST, prefix="lotto")
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                apri_lotto_lavorazione(
                    ordine, form.cleaned_data["codice"], request.user, form.cleaned_data["note"],
                )
                messages.success(request, "Lotto di lavorazione aperto.")
            elif azione == "prenota_materiale":
                form = PrenotazioneMaterialeForm(
                    request.POST, prefix="materiale", articoli=articoli_ammessi,
                )
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                prenota_materiale(
                    fase, form.cleaned_data["giacenza"], form.cleaned_data["quantita"], request.user,
                )
                messages.success(request, "Materiale aggiunto alla lavorazione.")
            elif azione == "consuma_materiale":
                consumo = get_object_or_404(
                    ConsumoMateriale, pk=request.POST.get("consumo_id"), fase=fase,
                )
                consuma_materiale(consumo, request.user)
                messages.success(request, "Prelievo confermato e giacenza aggiornata.")
            elif azione == "crea_batch":
                form = BatchRoboQboForm(request.POST, prefix="batch")
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                lotto = ordine.lotti_lavorazione.filter(
                    stato=LottoLavorazione.Stato.APERTO,
                ).first()
                if lotto is None:
                    raise ValidationError("Prima di creare un batch, apri il lotto di lavorazione.")
                tipo = fase.stazione.tipi_unita.get(codice="BATCH", attivo=True)
                batch = crea_unita(
                    fase, tipo, form.cleaned_data["codice"], form.cleaned_data["quantita"],
                    request.user,
                )
                collega_unita_lotto(lotto, batch, request.user)
                avvia_unita(batch, request.user)
                messages.success(request, f"Batch {batch.codice} creato e avviato.")
            elif azione == "registra_controlli_batch":
                batch = get_object_or_404(
                    fase.unita, pk=request.POST.get("batch_id"), tipo="BATCH",
                )
                registrati = 0
                for codice, campo in (("PH", "ph"), ("BRIX", "brix")):
                    valore = request.POST.get(campo, "").strip()
                    if valore:
                        definizione = fase.stazione.controlli.get(codice=codice)
                        registra_controllo(fase, definizione, valore, request.user, unita=batch)
                        registrati += 1
                if not registrati:
                    raise ValidationError("Inserisci almeno un controllo.")
                messages.success(request, "Controlli del batch registrati.")
            elif azione == "conferma_batch":
                batch = get_object_or_404(
                    fase.unita, pk=request.POST.get("batch_id"), tipo="BATCH",
                )
                assegna_esito_unita(batch, UnitaProduzione.Stato.CONFORME, request.user)
                messages.success(request, f"Batch {batch.codice} dichiarato conforme.")
            elif azione == "crea_tank":
                form = TankRoboQboForm(request.POST, prefix="tank")
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                tipo = fase.stazione.tipi_unita.get(codice="TANK", attivo=True)
                tank = crea_unita(fase, tipo, form.cleaned_data["codice"], None, request.user)
                messages.success(request, f"Tank {tank.codice} pronto a ricevere i batch.")
            elif azione == "riversa_tank":
                form = RiversamentoTankForm(request.POST, fase=fase, prefix="riversamento")
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                aggiungi_origine_unita(
                    form.cleaned_data["tank"], form.cleaned_data["batch"],
                    form.cleaned_data["quantita"], request.user,
                )
                messages.success(request, "Riversamento registrato e genealogia aggiornata.")
            elif azione == "chiudi_lotto":
                lotto = get_object_or_404(
                    LottoLavorazione, pk=request.POST.get("lotto_id"), ordine=ordine,
                    stato=LottoLavorazione.Stato.APERTO,
                )
                chiudi_lotto_lavorazione(lotto, request.user)
                messages.success(request, "Lotto B chiuso: non accetterà altri batch.")
            else:
                raise ValidationError("Operazione RoboQbo non riconosciuta.")
        except (ValidationError, TipoUnitaProduzione.DoesNotExist) as errore:
            testo = "; ".join(errore.messages) if isinstance(errore, ValidationError) else (
                "Manca la configurazione Batch/Tank: riapplica il preset della linea Marmellate."
            )
            messages.error(request, testo)
        return redirect("produzione_v2:lavorazione_roboqbo", ordine_pk=ordine.pk)

    lotto_aperto = ordine.lotti_lavorazione.filter(
        stato=LottoLavorazione.Stato.APERTO,
    ).first()
    return render(request, "produzione_v2/lavorazione_roboqbo.html", {
        "ordine": ordine, "fase": fase, "lotto_aperto": lotto_aperto,
        "lotti": ordine.lotti_lavorazione.prefetch_related("unita_collegate__unita"),
        "materiali": fase.materiali.select_related("articolo", "lotto", "ubicazione"),
        "batch": fase.unita.filter(tipo="BATCH").prefetch_related("rilevazioni__definizione"),
        "tank": fase.unita.filter(tipo="TANK").prefetch_related(
            "allocazioni_origine__origine",
        ),
        "form_lotto": LottoLavorazioneForm(prefix="lotto"),
        "form_materiale": PrenotazioneMaterialeForm(
            prefix="materiale", articoli=articoli_ammessi,
        ),
        "form_batch": BatchRoboQboForm(prefix="batch"),
        "form_tank": TankRoboQboForm(prefix="tank"),
        "form_riversamento": RiversamentoTankForm(fase=fase, prefix="riversamento"),
    })


@permission_required("produzione_v2.operare_produzione_v2", raise_exception=True)
def mie_attivita(request):
    return render(
        request, "produzione_v2/mie_attivita.html",
        CodaLavoroOperatore(request.user).dati(),
    )


@permission_required("produzione_v2.pianificare_produzione_v2", raise_exception=True)
def report_produzione(request):
    form = ReportProduzioneForm(request.GET or None)
    filtri = form.cleaned_data if form.is_valid() else {}
    report = ReportProduzione(filtri)
    ordini = report.ordini()
    return render(request, "produzione_v2/report.html", {
        "form": form, "ordini": ordini, "indicatori": report.indicatori(ordini),
    })


@permission_required("produzione_v2.pianificare_produzione_v2", raise_exception=True)
def esporta_report_produzione(request):
    form = ReportProduzioneForm(request.GET or None)
    if not form.is_valid():
        raise ValidationError("Filtri del report non validi.")
    ordini = ReportProduzione(form.cleaned_data).ordini()
    risposta = HttpResponse(content_type="text/csv; charset=utf-8")
    risposta["Content-Disposition"] = 'attachment; filename="report_produzione_v2.csv"'
    risposta.write("\ufeff")
    righe = csv.writer(risposta, delimiter=";")
    righe.writerow((
        "ORDINE", "DATA", "LINEA", "PRODOTTO", "PIANIFICATO", "PRODOTTO",
        "RESA_%", "AVANZAMENTO_%", "STATO", "NC", "AUDIT_VALIDO",
    ))
    for ordine in ordini:
        audit_valido, _ = ordine.eventi.model.verifica_catena(ordine)
        righe.writerow((
            ordine.codice, ordine.pianificato_per or "", ordine.linea.codice,
            ordine.prodotto.nome_per_produzione, ordine.quantita_pianificata,
            ordine.quantita_prodotta, ordine.resa_percentuale,
            ordine.avanzamento_percentuale, ordine.get_stato_display(),
            ordine.numero_nc, "SI" if audit_valido else "NO",
        ))
    return risposta


@permission_required("produzione_v2.configurare_produzione_v2", raise_exception=True)
def applica_preset_roboqbo_invasettamento(request):
    if request.method != "POST":
        return redirect("produzione_v2:dashboard")
    linea, creati = PresetRoboQboInvasettamento().applica()
    if creati:
        messages.success(request, f"Preset pilota applicato: creati {creati} elementi.")
    else:
        messages.info(request, "Il preset pilota era già completamente configurato.")
    return redirect("produzione_v2:dettaglio_linea", pk=linea.pk)


@permission_required("produzione_v2.configurare_produzione_v2", raise_exception=True)
def nuova_linea(request):
    form = LineaProduzioneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        linea = form.save()
        messages.success(request, "Linea produttiva creata.")
        return redirect("produzione_v2:dettaglio_linea", pk=linea.pk)
    return render(request, "produzione_v2/form.html", {
        "form": form, "titolo": "Nuova linea produttiva",
    })


@permission_required("produzione_v2.configurare_produzione_v2", raise_exception=True)
def nuova_stazione(request):
    form = StazioneLavoroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        stazione = form.save()
        messages.success(request, "Stazione di lavoro creata.")
        return redirect("produzione_v2:dettaglio_stazione", pk=stazione.pk)
    return render(request, "produzione_v2/form.html", {
        "form": form, "titolo": "Nuova stazione di lavoro",
    })


@permission_required("produzione_v2.configurare_produzione_v2", raise_exception=True)
def nuovo_ciclo(request):
    form = CicloProduzioneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ciclo = form.save()
        messages.success(request, "Ciclo produttivo creato.")
        return redirect("produzione_v2:dettaglio_ciclo", pk=ciclo.pk)
    return render(request, "produzione_v2/form.html", {
        "form": form, "titolo": "Nuovo ciclo produttivo",
    })


def dettaglio_ciclo(request, pk):
    ciclo = get_object_or_404(
        CicloProduzione.objects.select_related("prodotto", "linea", "ricetta"), pk=pk,
    )
    if request.method == "POST" and not request.user.has_perm(
        "produzione_v2.configurare_produzione_v2"
    ):
        raise PermissionDenied
    form = RegolaControlloCicloForm(request.POST or None, ciclo=ciclo)
    if request.method == "POST" and form.is_valid():
        regola = form.save(commit=False)
        regola.ciclo = ciclo
        try:
            regola.full_clean()
            regola.save()
        except (ValidationError, IntegrityError) as errore:
            messaggio = "; ".join(errore.messages) if isinstance(errore, ValidationError) else "Regola già configurata."
            form.add_error(None, messaggio)
        else:
            messages.success(request, "Limiti specifici del ciclo registrati.")
            return redirect("produzione_v2:dettaglio_ciclo", pk=ciclo.pk)
    return render(request, "produzione_v2/dettaglio_ciclo.html", {
        "ciclo": ciclo,
        "regole": ciclo.regole_controllo.select_related("definizione__stazione"),
        "form": form,
    })


def dettaglio_linea(request, pk):
    linea = get_object_or_404(LineaProduzione, pk=pk)
    if request.method == "POST" and not request.user.has_perm(
        "produzione_v2.configurare_produzione_v2"
    ):
        raise PermissionDenied
    azione = request.POST.get("azione") if request.method == "POST" else ""
    form = PassaggioLineaForm(
        request.POST if azione == "aggiungi_passaggio" else None, linea=linea,
    )
    form_dipendenza = DipendenzaPassaggioForm(
        request.POST if azione == "aggiungi_dipendenza" else None, linea=linea,
    )
    form_turno = TurnoLineaForm(request.POST if azione == "aggiungi_turno" else None)
    if request.method == "POST" and azione == "aggiungi_passaggio" and form.is_valid():
        passaggio = form.save(commit=False)
        passaggio.linea = linea
        try:
            passaggio.save()
        except IntegrityError:
            form.add_error(None, "Ordine o stazione già presenti nella linea.")
        else:
            messages.success(request, "Stazione aggiunta al percorso della linea.")
            return redirect("produzione_v2:dettaglio_linea", pk=linea.pk)
    if request.method == "POST" and azione == "aggiungi_dipendenza" and form_dipendenza.is_valid():
        try:
            aggiungi_dipendenza(
                form_dipendenza.cleaned_data["passaggio"],
                form_dipendenza.cleaned_data["predecessore"],
                form_dipendenza.cleaned_data["modalita"],
                form_dipendenza.cleaned_data["quantita_minima_avvio"],
            )
        except (ValidationError, IntegrityError) as errore:
            messaggio = "; ".join(errore.messages) if isinstance(errore, ValidationError) else "Dipendenza già esistente."
            form_dipendenza.add_error(None, messaggio)
        else:
            messages.success(request, "Dipendenza tra stazioni aggiunta.")
            return redirect("produzione_v2:dettaglio_linea", pk=linea.pk)
    if request.method == "POST" and azione == "aggiungi_turno" and form_turno.is_valid():
        turno = form_turno.save(commit=False)
        turno.linea = linea
        try:
            turno.full_clean()
            turno.save()
        except (ValidationError, IntegrityError) as errore:
            messaggio = "; ".join(errore.messages) if isinstance(errore, ValidationError) else "Turno già configurato."
            form_turno.add_error(None, messaggio)
        else:
            messages.success(request, "Turno della linea aggiunto.")
            return redirect("produzione_v2:dettaglio_linea", pk=linea.pk)
    return render(request, "produzione_v2/dettaglio_linea.html", {
        "linea": linea,
        "passaggi": linea.passaggi.select_related("stazione"),
        "form": form,
        "form_dipendenza": form_dipendenza,
        "form_turno": form_turno,
        "turni": linea.turni.all(),
        "dipendenze": linea.passaggi.filter(
            dipendenze__isnull=False,
        ).select_related("stazione").prefetch_related("dipendenze__predecessore__stazione"),
    })


def dettaglio_stazione(request, pk):
    stazione = get_object_or_404(StazioneLavoro, pk=pk)
    if request.method == "POST" and not request.user.has_perm(
        "produzione_v2.configurare_produzione_v2"
    ):
        raise PermissionDenied
    azione = request.POST.get("azione") if request.method == "POST" else ""
    form = DefinizioneControlloForm(request.POST if azione == "aggiungi_controllo" else None)
    form_tipo_unita = TipoUnitaProduzioneForm(
        request.POST if azione == "aggiungi_tipo_unita" else None,
    )
    form_abilitazione = AbilitazioneOperatoreForm(
        request.POST if azione == "aggiungi_abilitazione" else None,
    )
    form_risorsa = RisorsaProduzioneForm(
        request.POST if azione == "aggiungi_risorsa" else None,
    )
    if request.method == "POST" and azione == "aggiungi_controllo" and form.is_valid():
        controllo = form.save(commit=False)
        controllo.stazione = stazione
        try:
            controllo.save()
        except IntegrityError:
            form.add_error("codice", "Codice controllo già usato in questa stazione.")
        else:
            messages.success(request, "Controllo aggiunto alla stazione.")
            return redirect("produzione_v2:dettaglio_stazione", pk=stazione.pk)
    if request.method == "POST" and azione == "aggiungi_tipo_unita" and form_tipo_unita.is_valid():
        tipo = form_tipo_unita.save(commit=False)
        tipo.stazione = stazione
        try:
            tipo.save()
        except IntegrityError:
            form_tipo_unita.add_error("codice", "Codice già utilizzato nella stazione.")
        else:
            messages.success(request, "Tipo di unità aggiunto alla stazione.")
            return redirect("produzione_v2:dettaglio_stazione", pk=stazione.pk)
    if request.method == "POST" and azione == "aggiungi_abilitazione" and form_abilitazione.is_valid():
        abilitazione = form_abilitazione.save(commit=False)
        abilitazione.stazione = stazione
        try:
            abilitazione.save()
        except IntegrityError:
            form_abilitazione.add_error("operatore", "Operatore già abilitato alla stazione.")
        else:
            messages.success(request, "Abilitazione operatore registrata.")
            return redirect("produzione_v2:dettaglio_stazione", pk=stazione.pk)
    if request.method == "POST" and azione == "aggiungi_risorsa" and form_risorsa.is_valid():
        risorsa = form_risorsa.save(commit=False)
        risorsa.stazione = stazione
        try:
            risorsa.save()
        except IntegrityError:
            form_risorsa.add_error("codice", "Codice risorsa già utilizzato.")
        else:
            messages.success(request, "Risorsa produttiva aggiunta.")
            return redirect("produzione_v2:dettaglio_stazione", pk=stazione.pk)
    return render(request, "produzione_v2/dettaglio_stazione.html", {
        "stazione": stazione, "controlli": stazione.controlli.all(), "form": form,
        "tipi_unita": stazione.tipi_unita.all(), "form_tipo_unita": form_tipo_unita,
        "abilitazioni": stazione.abilitazioni_operatori.select_related("operatore"),
        "form_abilitazione": form_abilitazione,
        "risorse": stazione.risorse.all(), "form_risorsa": form_risorsa,
    })


@permission_required("produzione_v2.pianificare_produzione_v2", raise_exception=True)
def nuovo_ordine(request):
    form = OrdineProduzioneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ordine = form.save(commit=False)
        ordine.creato_da = request.user
        ordine.save()
        messages.success(request, "Ordine produttivo creato in stato pianificato.")
        return redirect("produzione_v2:dettaglio_ordine", pk=ordine.pk)
    return render(request, "produzione_v2/form.html", {
        "form": form, "titolo": "Nuovo ordine di produzione",
    })


def dettaglio_ordine(request, pk):
    ordine = get_object_or_404(
        OrdineProduzione.objects.select_related("linea", "prodotto"), pk=pk,
    )
    if request.method == "POST":
        azione = request.POST.get("azione")
        azioni_pianificazione = {"prepara", "avvia_ordine", "annulla_ordine"}
        azioni_qualita = {"apri_nc", "chiudi_nc"}
        permesso = (
            "produzione_v2.pianificare_produzione_v2"
            if azione in azioni_pianificazione
            else "produzione_v2.gestire_qualita_v2"
            if azione in azioni_qualita
            else "produzione_v2.operare_produzione_v2"
        )
        if not request.user.has_perm(permesso):
            raise PermissionDenied
        try:
            if azione == "prepara":
                prepara_ordine(ordine, request.user)
                messages.success(request, "Ordine preparato e fasi generate.")
            elif azione == "avvia_ordine":
                avvia_ordine(ordine, request.user)
                messages.success(request, "Ordine avviato.")
            elif azione == "avvia_fase":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                avvia_fase(fase, request.user)
                messages.success(request, "Fase avviata.")
            elif azione == "salta_fase":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                salta_fase(fase, request.POST.get("motivo"), request.user)
                messages.warning(request, "Fase facoltativa saltata.")
            elif azione == "assegna_operatore":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                form_operatore = AssegnazioneOperatoreForm(request.POST, fase=fase)
                if not form_operatore.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_operatore.errors.values()
                            for messaggio in messaggi
                        )
                    )
                assegna_operatore(fase, form_operatore.cleaned_data["operatore"], request.user)
                messages.success(request, "Operatore assegnato alla fase.")
            elif azione == "termina_assegnazione":
                assegnazione = get_object_or_404(
                    AssegnazioneOperatore, pk=request.POST.get("assegnazione_id"),
                    fase__ordine=ordine,
                )
                termina_assegnazione(assegnazione, request.user)
                messages.success(request, "Assegnazione operatore terminata.")
            elif azione == "impegna_risorsa":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                form_impegno = ImpegnoRisorsaForm(request.POST, fase=fase)
                if not form_impegno.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_impegno.errors.values()
                            for messaggio in messaggi
                        )
                    )
                impegna_risorsa(fase, form_impegno.cleaned_data["risorsa"], request.user)
                messages.success(request, "Risorsa assegnata alla fase.")
            elif azione == "rilascia_risorsa":
                impegno = get_object_or_404(
                    ImpegnoRisorsa, pk=request.POST.get("impegno_id"), fase__ordine=ordine,
                )
                rilascia_risorsa(impegno, request.user)
                messages.success(request, "Risorsa rilasciata.")
            elif azione == "registra_controlli":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                for definizione in fase.passaggio.stazione.controlli.all():
                    chiave = f"controllo_{definizione.pk}"
                    valore = request.POST.get(chiave, "").strip()
                    if valore or definizione.obbligatorio:
                        registra_controllo(fase, definizione, valore, request.user)
                messages.success(request, "Controlli registrati.")
            elif azione == "completa_fase":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                completa_fase(fase, request.user)
                messages.success(request, "Fase completata.")
            elif azione == "crea_unita":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                form_unita = UnitaProduzioneForm(request.POST, fase=fase)
                if not form_unita.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_unita.errors.values()
                            for messaggio in messaggi
                        )
                    )
                unita_creata = crea_unita(
                    fase, form_unita.cleaned_data["tipo"], form_unita.cleaned_data["codice"],
                    form_unita.cleaned_data["quantita"], request.user,
                    origine=form_unita.cleaned_data["origine"],
                    quantita_origine=form_unita.cleaned_data["quantita_origine"],
                )
                lotto_aperto = ordine.lotti_lavorazione.filter(
                    stato=LottoLavorazione.Stato.APERTO,
                ).first()
                if lotto_aperto and fase.stazione.codice == "ROBOQBO-V2":
                    collega_unita_lotto(lotto_aperto, unita_creata, request.user)
                messages.success(request, "Unità produttiva creata.")
            elif azione == "aggiungi_origine_unita":
                form = AllocazioneOrigineForm(request.POST, ordine=ordine)
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                aggiungi_origine_unita(
                    form.cleaned_data["destinazione"], form.cleaned_data["origine"],
                    form.cleaned_data["quantita"], request.user,
                )
                messages.success(request, "Ulteriore origine collegata e quantità tracciata.")
            elif azione == "apri_lotto_lavorazione":
                form = LottoLavorazioneForm(request.POST)
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                apri_lotto_lavorazione(
                    ordine, form.cleaned_data["codice"], request.user,
                    form.cleaned_data["note"],
                )
                messages.success(request, "Lotto temporaneo di B aperto.")
            elif azione == "chiudi_lotto_lavorazione":
                lotto = get_object_or_404(
                    LottoLavorazione, pk=request.POST.get("lotto_id"), ordine=ordine,
                )
                chiudi_lotto_lavorazione(lotto, request.user)
                messages.success(request, "Lotto temporaneo di B chiuso.")
            elif azione == "chiudi_lotto_commerciale":
                form = ChiusuraLottoCommercialeForm(request.POST, ordine=ordine)
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                lotto = chiudi_lotto_commerciale(
                    ordine, form.cleaned_data["lotti_lavorazione"],
                    form.cleaned_data["vasetti_conformi"],
                    form.cleaned_data["vasetti_scartati"],
                    form.cleaned_data["capsule_scartate"], request.user,
                    codice=form.cleaned_data["codice"],
                    motivazione_eccezione=form.cleaned_data["motivazione_eccezione"],
                )
                messages.success(request, f"Lotto definitivo {lotto.codice} assegnato da C.")
            elif azione == "registra_consuntivo_etichettatura":
                form = ConsuntivoEtichettaturaForm(request.POST, ordine=ordine)
                if not form.is_valid():
                    raise ValidationError("; ".join(
                        str(m) for errori in form.errors.values() for m in errori
                    ))
                registra_consuntivo_etichettatura(
                    form.cleaned_data["lotto_commerciale"],
                    form.cleaned_data["vasetti_conformi"],
                    form.cleaned_data["vasetti_scartati"],
                    form.cleaned_data["etichette_scartate"], request.user,
                )
                messages.success(request, "Consuntivo di etichettatura registrato.")
            elif azione == "avvia_unita":
                unita = get_object_or_404(UnitaProduzione, pk=request.POST.get("unita_id"), ordine=ordine)
                avvia_unita(unita, request.user)
                messages.success(request, "Unità avviata.")
            elif azione == "esito_unita":
                unita = get_object_or_404(UnitaProduzione, pk=request.POST.get("unita_id"), ordine=ordine)
                assegna_esito_unita(unita, request.POST.get("esito"), request.user)
                messages.success(request, "Esito dell'unità registrato.")
            elif azione == "registra_output":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                form_output = OutputProduzioneForm(request.POST, fase=fase)
                if not form_output.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_output.errors.values()
                            for messaggio in messaggi
                        )
                    )
                registra_output(
                    fase=fase, articolo=form_output.cleaned_data["articolo"],
                    codice_lotto=form_output.cleaned_data["codice_lotto"],
                    quantita=form_output.cleaned_data["quantita"],
                    ubicazione=form_output.cleaned_data["ubicazione"],
                    operatore=request.user, unita=form_output.cleaned_data["unita"],
                    scaffale=form_output.cleaned_data["scaffale"],
                    piano=form_output.cleaned_data["piano"], note=form_output.cleaned_data["note"],
                )
                messages.success(request, "Output caricato nel magazzino e lotto creato.")
            elif azione == "prenota_materiale":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                form_materiale = PrenotazioneMaterialeForm(request.POST)
                if not form_materiale.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_materiale.errors.values()
                            for messaggio in messaggi
                        )
                    )
                prenota_materiale(
                    fase, form_materiale.cleaned_data["giacenza"],
                    form_materiale.cleaned_data["quantita"], request.user,
                )
                messages.success(request, "Materiale prenotato senza modificare la giacenza.")
            elif azione == "prenota_fefo":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                prenotazioni = PianificatoreMaterialiFEFO(fase).prenota(request.user)
                messages.success(
                    request, f"Prenotazione FEFO completata su {len(prenotazioni)} lotti/posizioni.",
                )
            elif azione in {"consuma_materiale", "reintegra_materiale", "scarta_materiale"}:
                consumo = get_object_or_404(
                    ConsumoMateriale, pk=request.POST.get("consumo_id"), ordine=ordine,
                )
                operazioni = {
                    "consuma_materiale": (consuma_materiale, "Materiale consumato e scaricato."),
                    "reintegra_materiale": (reintegra_materiale, "Materiale reintegrato in magazzino."),
                    "scarta_materiale": (scarta_materiale, "Materiale registrato come scartato."),
                }
                funzione, conferma = operazioni[azione]
                funzione(consumo, request.user)
                messages.success(request, conferma)
            elif azione == "consuma_tutti_materiali":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                consumati = consuma_materiali_prenotati(fase, request.user)
                messages.success(
                    request, f"Confermati {len(consumati)} consumi di materiale.",
                )
            elif azione == "apri_nc":
                form_nc = AperturaNonConformitaForm(request.POST, ordine=ordine)
                if not form_nc.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_nc.errors.values()
                            for messaggio in messaggi
                        )
                    )
                apri_non_conformita(
                    ordine, form_nc.cleaned_data["motivo"], request.user,
                    fase=form_nc.cleaned_data["fase"], unita=form_nc.cleaned_data["unita"],
                    consumo=form_nc.cleaned_data["consumo"],
                )
                messages.warning(request, "Non conformità aperta: ordine bloccato.")
            elif azione == "chiudi_nc":
                nc = get_object_or_404(
                    NonConformita, pk=request.POST.get("nc_id"), ordine=ordine,
                )
                form_chiusura_nc = ChiusuraNonConformitaForm(request.POST)
                if not form_chiusura_nc.is_valid():
                    raise ValidationError(
                        "; ".join(
                            str(messaggio)
                            for messaggi in form_chiusura_nc.errors.values()
                            for messaggio in messaggi
                        )
                    )
                chiudi_non_conformita(
                    nc, form_chiusura_nc.cleaned_data["esito"],
                    form_chiusura_nc.cleaned_data["azione"], request.user,
                )
                messages.success(request, "Non conformità chiusa e flusso aggiornato.")
            elif azione == "completa_ordine":
                ordine_aggiornato = completa_ordine(ordine, request.user)
                if ordine_aggiornato.stato == OrdineProduzione.Stato.COMPLETATO:
                    messages.success(request, "Ordine completato.")
                else:
                    messages.warning(
                        request, "Resa fuori specifica: aperta una non conformità.",
                    )
            elif azione == "sospendi_ordine":
                sospendi_ordine(ordine, request.POST.get("motivo"), request.user)
                messages.warning(request, "Ordine sospeso; risorse e operatori sono stati rilasciati.")
            elif azione == "riprendi_ordine":
                riprendi_ordine(ordine, request.user)
                messages.success(request, "Ordine ripreso. Riassegna risorse e operatori se necessari.")
            elif azione == "riprendi_fase":
                fase = get_object_or_404(ordine.fasi, pk=request.POST.get("fase_id"))
                riprendi_fase(fase, request.user)
                messages.success(request, "Fase ripresa.")
            elif azione == "annulla_ordine":
                annulla_ordine(ordine, request.POST.get("motivo"), request.user)
                messages.warning(request, "Ordine annullato.")
            else:
                messages.error(request, "Operazione V2 non riconosciuta.")
        except ValidationError as errore:
            messages.error(request, "; ".join(errore.messages))
        return redirect("produzione_v2:dettaglio_ordine", pk=ordine.pk)

    fasi = ordine.fasi.select_related("passaggio__stazione").prefetch_related(
        "passaggio__stazione__controlli", "passaggio__stazione__tipi_unita",
        "rilevazioni__definizione", "unita__tipo_definizione", "unita__origine",
        "output__articolo", "output__lotto", "output__ubicazione", "output__unita",
        "assegnazioni__operatore",
        "impegni_risorse__risorsa",
    )
    fasi = list(fasi)
    for fase in fasi:
        fase.form_unita = UnitaProduzioneForm(fase=fase)
        fase.form_output = OutputProduzioneForm(fase=fase)
        fase.form_operatore = AssegnazioneOperatoreForm(fase=fase)
        fase.form_risorsa = ImpegnoRisorsaForm(fase=fase)
        if fase.stato == FaseProduzione.Stato.IN_CORSO and ordine.ciclo_id:
            fase.proposte_fefo, fase.mancanti_fefo = PianificatoreMaterialiFEFO(fase).calcola()
    audit_valido, audit_eventi = ordine.eventi.model.verifica_catena(ordine)
    problemi_prontezza = (
        ValutatoreProntezzaOrdine(ordine).valuta()
        if ordine.stato == OrdineProduzione.Stato.PRONTO else []
    )
    return render(request, "produzione_v2/dettaglio_ordine.html", {
        "ordine": ordine, "fasi": fasi,
        "form_materiale": PrenotazioneMaterialeForm(),
        "form_nc": AperturaNonConformitaForm(ordine=ordine),
        "form_chiusura_nc": ChiusuraNonConformitaForm(),
        "form_allocazione_origine": AllocazioneOrigineForm(ordine=ordine),
        "form_lotto_lavorazione": LottoLavorazioneForm(),
        "form_lotto_commerciale": ChiusuraLottoCommercialeForm(
            ordine=ordine, codice_proposto=proponi_codice_lotto_commerciale(),
        ),
        "form_consuntivo_etichettatura": ConsuntivoEtichettaturaForm(ordine=ordine),
        "lotti_lavorazione": ordine.lotti_lavorazione.prefetch_related("unita_collegate__unita"),
        "lotti_commerciali": ordine.lotti_commerciali.prefetch_related(
            "origini_lavorazione__lotto_lavorazione",
        ),
        "non_conformita": ordine.non_conformita.select_related(
            "fase__passaggio__stazione", "unita", "consumo__articolo",
            "rilevazione__definizione",
        ),
        "fabbisogni": ordine.fabbisogni.select_related("articolo", "fase"),
        "audit_valido": audit_valido, "audit_eventi": audit_eventi,
        "problemi_prontezza": problemi_prontezza,
    })


def _dati_tracciabilita(ordine):
    return {
        "ordine": ordine,
        "materiali": ordine.materiali.select_related(
            "fase__passaggio__stazione", "articolo", "lotto", "ubicazione",
        ).order_by("fase__sequenza", "creato_il"),
        "unita": ordine.unita.select_related(
            "fase__passaggio__stazione", "tipo_definizione", "origine",
        ).order_by("fase__sequenza", "creata_il"),
        "output": ordine.output.select_related(
            "fase__passaggio__stazione", "articolo", "lotto", "unita", "ubicazione",
        ).order_by("fase__sequenza", "creato_il"),
        "non_conformita": ordine.non_conformita.select_related(
            "fase__passaggio__stazione", "unita", "consumo__articolo", "consumo__lotto",
            "rilevazione__definizione",
        ).order_by("aperta_il"),
    }


def tracciabilita_ordine(request, pk):
    ordine = get_object_or_404(
        OrdineProduzione.objects.select_related("linea", "prodotto", "ciclo"), pk=pk,
    )
    contesto = _dati_tracciabilita(ordine)
    contesto["audit_valido"], contesto["audit_eventi"] = ordine.eventi.model.verifica_catena(
        ordine,
    )
    return render(request, "produzione_v2/tracciabilita_ordine.html", contesto)


def esporta_tracciabilita_ordine(request, pk):
    ordine = get_object_or_404(
        OrdineProduzione.objects.select_related("linea", "prodotto"), pk=pk,
    )
    dati = _dati_tracciabilita(ordine)
    risposta = HttpResponse(content_type="text/csv; charset=utf-8")
    risposta["Content-Disposition"] = (
        f'attachment; filename="tracciabilita_{ordine.codice}.csv"'
    )
    risposta.write("\ufeff")
    righe = csv.writer(risposta, delimiter=";")
    righe.writerow(("TIPO", "FASE", "ARTICOLO/TIPO", "LOTTO/CODICE", "QUANTITA", "STATO", "COLLEGAMENTO"))
    for materiale in dati["materiali"]:
        righe.writerow((
            "MATERIALE", materiale.fase.sequenza, materiale.articolo.codice,
            materiale.lotto.codice_lotto if materiale.lotto else "",
            materiale.quantita, materiale.get_stato_display(),
            f"{materiale.ubicazione or ''} / {materiale.scaffale} / {materiale.piano}",
        ))
    for unita in dati["unita"]:
        righe.writerow((
            "UNITA", unita.fase.sequenza,
            unita.tipo_definizione.nome if unita.tipo_definizione else unita.tipo,
            unita.codice, unita.quantita or "", unita.get_stato_display(),
            unita.origine.codice if unita.origine else "",
        ))
    for prodotto in dati["output"]:
        righe.writerow((
            "OUTPUT", prodotto.fase.sequenza, prodotto.articolo.codice,
            prodotto.codice_lotto, prodotto.quantita, prodotto.get_stato_display(),
            prodotto.unita.codice if prodotto.unita else "",
        ))
    for nc in dati["non_conformita"]:
        collegamento = nc.unita.codice if nc.unita else (
            nc.consumo.lotto.codice_lotto if nc.consumo and nc.consumo.lotto else ""
        )
        righe.writerow((
            "NC", nc.fase.sequenza if nc.fase else "", nc.codice, "", "",
            nc.get_stato_display(), " / ".join(filter(None, (
                collegamento, nc.get_decisione_flusso_display(),
            ))),
        ))
    return risposta


def ricerca_tracciabilita(request):
    termine = request.GET.get("lotto", "").strip()
    consumi = ConsumoMateriale.objects.none()
    output = OutputProduzione.objects.none()
    ordini = OrdineProduzione.objects.none()
    catena = None
    if termine:
        consumi = ConsumoMateriale.objects.filter(
            lotto__codice_lotto__icontains=termine,
        ).select_related(
            "lotto", "articolo", "ordine__prodotto", "fase__passaggio__stazione",
        ).order_by("lotto__codice_lotto", "ordine__codice")[:100]
        output = OutputProduzione.objects.filter(
            codice_lotto__icontains=termine,
        ).select_related(
            "lotto", "articolo", "ordine__prodotto", "fase__passaggio__stazione",
        ).order_by("codice_lotto", "ordine__codice")[:100]
        ordini_ids = set(consumi.values_list("ordine_id", flat=True))
        ordini_ids.update(output.values_list("ordine_id", flat=True))
        ordini = OrdineProduzione.objects.filter(
            pk__in=ordini_ids,
        ).select_related("prodotto", "linea")
        catena = CatenaTracciabilita(termine).calcola()
    return render(request, "produzione_v2/ricerca_tracciabilita.html", {
        "termine": termine, "consumi": consumi, "output": output, "ordini": ordini,
        "catena": catena,
    })
