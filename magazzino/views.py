from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import permission_required, user_passes_test
from django.db.models import F, OuterRef, Q, Subquery, Sum
from django.utils import timezone
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import HttpResponse, JsonResponse

from .forms import (
    CaricoLottoForm,
    TrasferimentoForm,
    ConsumoForm,
    RicettaForm,
    RigaRicettaForm,
    ProduzioneForm,
    ConfermaProduzioneForm,
    AperturaTankForm,
    ControlloTankForm,
    ModificaTankForm,
    AnnullaTankForm,
    BatchProduzioneForm,
    CarrelloProduzioneForm,
    ChiusuraCarrelloForm,
    ConfezionamentoForm,
    InscatolamentoForm,
    ProduzioneSemilavoratoForm,
    IngredienteSemilavoratoForm,
    ConfermaProduzioneSemilavoratoForm,
    ArticoloForm,
    FornitoreForm,
    UbicazioneForm,
    ImportazioneCSVForm,
    RipristinoBackupForm,
    AperturaNonConformitaLottoForm,
    GestioneNonConformitaLottoForm,
    AperturaNonConformitaGeneraleForm,
)

from .services import (
    registra_carico_lotto,
    registra_trasferimento,
    registra_consumo,
    avvia_produzione,
    registra_prelievi_produzione,
    registra_ingredienti_tank,
    chiudi_preparazione_produzione,
    registra_scarti_tank,
    conferma_produzione,
    apri_tank_produzione,
    registra_controlli_tank,
    registra_pastorizzazione,
    registra_verifica_vuoto,
    modifica_tank_produzione,
    annulla_tank_produzione,
    registra_confezionamento,
    registra_inscatolamento,
    registra_prelievi_semilavorato,
    registra_scarto_prelievo_semilavorato,
    conferma_produzione_semilavorato,
    elimina_produzione_bozza,
    elimina_produzione_semilavorato_bozza,
    apri_non_conformita_lotto,
    gestisci_non_conformita_lotto,
)

from .models import (
    Giacenza,
    Lotto,
    Movimento,
    Ricetta,
    RigaRicetta,
    Articolo,
    Inscatolamento,
    Produzione,
    ProduzioneSemilavorato,
    Fornitore,
    Ubicazione,
    RegistroOperazione,
    TankProduzione,
    BatchProduzione,
    CarrelloProduzione,
    NonConformitaLotto,
)

from .csv_import import genera_template_csv, importa_csv
from .backup_db import crea_backup, ripristina_backup
from .audit import registra_operazione


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuovo_carico(request):
    if request.method == "POST":
        form = CaricoLottoForm(request.POST)

        if form.is_valid():
            try:
                lotto, movimento = registra_carico_lotto(
                    articolo=form.cleaned_data["articolo"],
                    codice_lotto=form.cleaned_data["codice_lotto"],
                    fornitore=form.cleaned_data["fornitore"],
                    quantita=form.cleaned_data["quantita"],
                    numero_colli=form.cleaned_data["numero_colli"],
                    unita_acquisto_per_collo=form.cleaned_data[
                        "unita_acquisto_per_collo"
                    ],
                    peso_unita_acquisto=form.cleaned_data[
                        "peso_unita_acquisto"
                    ],
                    fattura=form.cleaned_data["fattura"],
                    ddt=form.cleaned_data["ddt"],
                    ubicazione=form.cleaned_data["ubicazione"],
                    scaffale=form.cleaned_data["scaffale"],
                    piano=form.cleaned_data["piano"],
                    data_arrivo=form.cleaned_data["data_arrivo"],
                    data_scadenza=form.cleaned_data["data_scadenza"],
                    causale=form.cleaned_data["causale"],
                    note=form.cleaned_data["note"],
                    operatore=request.user,
                )

            except ValueError as e:
                form.add_error(None, str(e))

            else:
                messages.success(
                    request,
                    f"Lotto {lotto.codice_lotto} caricato correttamente.",
                )

                return redirect("nuovo_carico")

    else:
        form = CaricoLottoForm()

    return render(
        request,
        "magazzino/nuovo_carico.html",
        {"form": form},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def trasferimento(request):
    if request.method == "POST":
        form = TrasferimentoForm(request.POST)

        if form.is_valid():
            try:
                movimento = registra_trasferimento(
                    lotto=form.cleaned_data["giacenza"].lotto,
                    quantita=form.cleaned_data["quantita"],
                    ubicazione_origine=form.cleaned_data["giacenza"].ubicazione,
                    scaffale_origine=form.cleaned_data["giacenza"].scaffale,
                    piano_origine=form.cleaned_data["giacenza"].piano,
                    ubicazione_destinazione=form.cleaned_data[
                        "ubicazione_destinazione"
                    ],
                    scaffale_destinazione=form.cleaned_data[
                        "scaffale_destinazione"
                    ],
                    piano_destinazione=form.cleaned_data[
                        "piano_destinazione"
                    ],
                    note=form.cleaned_data["note"],
                    operatore=request.user,
                )

            except ValueError as e:
                form.add_error(None, str(e))

            else:
                messages.success(
                    request,
                    f"Trasferimento del lotto "
                    f"{movimento.lotto.codice_lotto} "
                    f"registrato correttamente.",
                )

                return redirect("trasferimento")

    else:
        form = TrasferimentoForm()

    return render(
        request,
        "magazzino/trasferimento.html",
        {"form": form},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def disponibilita_trasferimento(request):
    articolo_id = request.GET.get("articolo")
    if not articolo_id or not articolo_id.isdigit():
        return JsonResponse({"disponibilita": []})

    giacenze = (
        Giacenza.objects.select_related("lotto__articolo", "ubicazione")
        .filter(
            lotto__articolo_id=articolo_id,
            quantita__gt=0,
            ubicazione__attiva=True,
        )
        .order_by("lotto__codice_lotto", "ubicazione__nome")
    )
    return JsonResponse(
        {
            "disponibilita": [
                {
                    "id": giacenza.pk,
                    "lotto": giacenza.lotto.codice_lotto,
                    "posizione": " - ".join(
                        parte
                        for parte in [
                            str(giacenza.ubicazione),
                            (
                                f"Scaffale {giacenza.scaffale}"
                                if giacenza.scaffale else ""
                            ),
                            f"Piano {giacenza.piano}" if giacenza.piano else "",
                        ]
                        if parte
                    ),
                    "ubicazione_id": giacenza.ubicazione_id,
                    "quantita": str(giacenza.quantita),
                    "unita_misura": giacenza.lotto.articolo.unita_misura,
                }
                for giacenza in giacenze
            ]
        }
    )


def situazione_magazzino(request):
    articoli = Paginator(
        Articolo.objects.all().order_by(
            "categoria",
            "descrizione",
            "codice",
        ),
        50,
    ).get_page(request.GET.get("articoli_page"))
    articoli.object_list = list(articoli.object_list)
    articolo_ids = [articolo.pk for articolo in articoli.object_list]

    totali_articolo = {
        riga["lotto__articolo_id"]: riga["totale"]
        for riga in (
            Giacenza.objects.filter(lotto__articolo_id__in=articolo_ids)
            .values("lotto__articolo_id")
            .annotate(totale=Sum("quantita"))
        )
    }

    for articolo in articoli.object_list:
        articolo.giacenza_totale = totali_articolo.get(
            articolo.pk,
            Decimal("0"),
        )

    def raggruppa_per_categoria(elementi, articolo_da_elemento):
        gruppi = []
        for elemento in elementi:
            articolo = articolo_da_elemento(elemento)
            if not gruppi or gruppi[-1]["codice"] != articolo.categoria:
                gruppi.append(
                    {
                        "codice": articolo.categoria,
                        "nome": articolo.get_categoria_display(),
                        "righe": [],
                    }
                )
            gruppi[-1]["righe"].append(elemento)
        return gruppi

    gruppi_articoli = raggruppa_per_categoria(
        articoli.object_list,
        lambda articolo: articolo,
    )
    return render(
        request,
        "magazzino/situazione_magazzino.html",
        {
            "articoli": articoli,
            "gruppi_articoli": gruppi_articoli,
        },
    )

@permission_required("magazzino.operare_magazzino", raise_exception=True)
def consumo(request):
    if request.method == "POST":
        form = ConsumoForm(request.POST)

        if form.is_valid():
            try:
                movimento = registra_consumo(
                    lotto=form.cleaned_data["lotto"],
                    quantita=form.cleaned_data["quantita"],
                    ubicazione_origine=form.cleaned_data[
                        "ubicazione_origine"
                    ],
                    scaffale_origine=form.cleaned_data["scaffale_origine"],
                    piano_origine=form.cleaned_data["piano_origine"],
                    causale=form.cleaned_data["causale"],
                    note=form.cleaned_data["note"],
                    operatore=request.user,
                )

            except ValueError as e:
                form.add_error(None, str(e))

            else:
                messages.success(
                    request,
                    f"Scarico del lotto "
                    f"{movimento.lotto.codice_lotto} "
                    f"registrato correttamente.",
                )

                return redirect("consumo")

    else:
        form = ConsumoForm()

    return render(
        request,
        "magazzino/consumo.html",
        {"form": form},
    )


def elenco_movimenti(request):
    movimenti_queryset = Movimento.objects.select_related(
        "lotto__articolo",
        "ubicazione_origine",
        "ubicazione_destinazione",
        "eseguito_da",
    ).order_by(
        "-data_ora",
        "-id",
    )
    movimenti = Paginator(movimenti_queryset, 50).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "magazzino/elenco_movimenti.html",
        {
            "movimenti": movimenti,
            "page_obj": movimenti,
        },
    )


def ricerca_lotti(request):
    query = request.GET.get("q", "").strip()
    ultimo_movimento = (
        Movimento.objects.filter(lotto_id=OuterRef("pk"))
        .order_by("-data_ora", "-pk")
        .values("data_ora")[:1]
    )
    lotti_queryset = (
        Lotto.objects.select_related("articolo", "fornitore")
        .annotate(
            giacenza_totale=Sum("giacenze__quantita"),
            ultimo_movimento=Subquery(ultimo_movimento),
        )
        .order_by("-data_arrivo", "-data_produzione", "codice_lotto")
    )

    if query:
        lotti_queryset = lotti_queryset.filter(
            Q(codice_lotto__icontains=query)
            | Q(articolo__codice__icontains=query)
            | Q(articolo__descrizione__icontains=query)
            | Q(fornitore__ragione_sociale__icontains=query)
            | Q(fornitore__codice__icontains=query)
        )

    lotti = Paginator(lotti_queryset, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "magazzino/ricerca_lotti.html",
        {
            "lotti": lotti,
            "page_obj": lotti,
            "query": query,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def apri_non_conformita_generale(request):
    if request.method == "POST":
        form = AperturaNonConformitaGeneraleForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["lotto"]:
                try:
                    non_conformita = apri_non_conformita_lotto(
                        lotto=form.cleaned_data["lotto"],
                        giacenza=form.cleaned_data["giacenza"],
                        numero_uda=form.cleaned_data["numero_uda"],
                        motivo=form.cleaned_data["motivo"],
                        note=form.cleaned_data["note_apertura"],
                        operatore=request.user,
                        ambito=form.cleaned_data["ambito"],
                        tipo_nc=form.cleaned_data["tipo_nc"],
                    )
                except ValueError as errore:
                    form.add_error(None, str(errore))
                    non_conformita = None
            else:
                non_conformita = form.save(commit=False)
                non_conformita.aperta_da = request.user
                non_conformita.save()
            if non_conformita is None:
                return render(
                    request,
                    "magazzino/apri_non_conformita_generale.html",
                    {"form": form},
                )
            messages.warning(
                request,
                f"Non conformità NC-{non_conformita.pk} aperta correttamente.",
            )
            return redirect("registro_non_conformita")
    else:
        form = AperturaNonConformitaGeneraleForm()
    return render(
        request,
        "magazzino/apri_non_conformita_generale.html",
        {"form": form},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def ricerca_lotti_non_conformita(request):
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"risultati": []})
    lotti = (
        Lotto.objects.select_related("articolo")
        .filter(giacenze__quantita__gt=0)
        .filter(
            Q(codice_lotto__icontains=query)
            | Q(articolo__codice__icontains=query)
            | Q(articolo__descrizione__icontains=query)
        )
        .annotate(disponibile=Sum("giacenze__quantita"))
        .order_by("codice_lotto")[:20]
    )
    return JsonResponse(
        {
            "risultati": [
                {
                    "id": lotto.pk,
                    "label": (
                        f"{lotto.codice_lotto} — {lotto.articolo.codice} — "
                        f"{lotto.articolo.descrizione} — disponibile "
                        f"{lotto.disponibile} {lotto.articolo.unita_misura}"
                    ),
                }
                for lotto in lotti
            ]
        }
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def posizioni_lotto_non_conformita(request):
    lotto_id = request.GET.get("lotto")
    if not lotto_id or not lotto_id.isdigit():
        return JsonResponse({"posizioni": []})
    giacenze = (
        Giacenza.objects.select_related("ubicazione", "lotto__articolo")
        .filter(lotto_id=lotto_id, quantita__gt=0)
        .order_by("ubicazione__nome", "scaffale", "piano")
    )
    return JsonResponse(
        {
            "posizioni": [
                {
                    "id": giacenza.pk,
                    "label": str(giacenza),
                }
                for giacenza in giacenze
            ]
        }
    )


def registro_non_conformita(request):
    queryset = NonConformitaLotto.objects.select_related(
        "lotto__articolo", "aperta_da", "gestita_da"
    )
    query = (request.GET.get("q") or "").strip()
    stato = request.GET.get("stato") or ""
    ambito = request.GET.get("ambito") or ""
    tipo_nc = request.GET.get("tipo_nc") or ""
    if query:
        filtro = Q(motivo__icontains=query) | Q(decisione__icontains=query)
        if query.isdigit():
            filtro |= Q(pk=int(query))
        queryset = queryset.filter(filtro)
    if stato:
        queryset = queryset.filter(stato=stato)
    if ambito:
        queryset = queryset.filter(ambito=ambito)
    if tipo_nc:
        queryset = queryset.filter(tipo_nc=tipo_nc)
    pagina = Paginator(queryset, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "magazzino/registro_non_conformita.html",
        {
            "non_conformita": pagina,
            "page_obj": pagina,
            "query": query,
            "stato": stato,
            "ambito": ambito,
            "tipo_nc": tipo_nc,
            "stati": NonConformitaLotto.Stato.choices,
            "ambiti": NonConformitaLotto.Ambito.choices,
            "tipi_nc": NonConformitaLotto.Tipo.choices,
        },
    )


def dettaglio_non_conformita(request, pk):
    non_conformita = get_object_or_404(
        NonConformitaLotto.objects.select_related(
            "lotto__articolo", "ubicazione_origine", "aperta_da", "gestita_da"
        ),
        pk=pk,
    )
    return render(
        request,
        "magazzino/dettaglio_non_conformita.html",
        {"non_conformita": non_conformita},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def apri_non_conformita(request, pk):
    lotto = get_object_or_404(
        Lotto.objects.select_related("articolo", "fornitore"), pk=pk
    )
    if request.method == "POST":
        form = AperturaNonConformitaLottoForm(request.POST, lotto=lotto)
        if form.is_valid():
            try:
                non_conformita = apri_non_conformita_lotto(
                    lotto=lotto,
                    giacenza=form.cleaned_data["giacenza"],
                    numero_uda=form.cleaned_data["numero_uda"],
                    motivo=form.cleaned_data["motivo"],
                    note=form.cleaned_data["note"],
                    operatore=request.user,
                    ambito=form.cleaned_data["ambito"],
                    tipo_nc=form.cleaned_data["tipo_nc"],
                )
            except ValueError as errore:
                form.add_error(None, str(errore))
            else:
                messages.warning(
                    request,
                    f"Non conformità NC-{non_conformita.pk} aperta: "
                    f"{non_conformita.numero_uda_quarantena} UDA in quarantena.",
                )
                return redirect("dettaglio_lotto", pk=lotto.pk)
    else:
        form = AperturaNonConformitaLottoForm(lotto=lotto)
    return render(
        request,
        "magazzino/apri_non_conformita.html",
        {"lotto": lotto, "form": form},
    )


@permission_required("magazzino.gestire_non_conformita", raise_exception=True)
def gestisci_non_conformita(request, pk):
    non_conformita = get_object_or_404(
        NonConformitaLotto.objects.select_related(
            "lotto__articolo", "ubicazione_origine", "aperta_da", "gestita_da"
        ),
        pk=pk,
    )
    if non_conformita.stato == NonConformitaLotto.Stato.CHIUSA:
        messages.info(request, "La non conformità è già stata chiusa.")
        return redirect("registro_non_conformita")
    if request.method == "POST":
        form = GestioneNonConformitaLottoForm(
            request.POST, non_conformita=non_conformita
        )
        if form.is_valid():
            for campo in (
                "analisi_cause", "azione_risoluzione", "responsabile_azione",
                "data_inizio_gestione", "azione_immediata", "scadenza_prevista",
                "esito_efficacia", "verifica_efficacia", "data_verifica",
            ):
                setattr(non_conformita, campo, form.cleaned_data[campo])
            non_conformita.stato = NonConformitaLotto.Stato.IN_LAVORAZIONE
            non_conformita.gestita_da = request.user
            non_conformita.save()

            if request.POST.get("azione") == "salva":
                messages.success(request, "Lavorazione della NC salvata.")
                return redirect("registro_non_conformita")
            if form.cleaned_data["esito_efficacia"] == NonConformitaLotto.EsitoEfficacia.NON_EFFICACE:
                form.add_error(
                    "esito_efficacia",
                    "Una NC con verifica non efficace deve rimanere in lavorazione.",
                )
            else:
                try:
                    if non_conformita.numero_uda_quarantena:
                        gestisci_non_conformita_lotto(
                            non_conformita=non_conformita,
                            numero_uda_scartate=form.cleaned_data["numero_uda_scartate"],
                            numero_uda_reintegrate=form.cleaned_data["numero_uda_reintegrate"],
                            decisione=form.cleaned_data["decisione"],
                            responsabile=request.user,
                        )
                    else:
                        non_conformita.stato = NonConformitaLotto.Stato.CHIUSA
                        non_conformita.data_chiusura = timezone.now()
                        non_conformita.save(update_fields=["stato", "data_chiusura"])
                except ValueError as errore:
                    form.add_error(None, str(errore))
                else:
                    messages.success(request, "Non conformità chiusa correttamente.")
                    return redirect("registro_non_conformita")
    else:
        form = GestioneNonConformitaLottoForm(
            non_conformita=non_conformita,
            initial={
                campo: getattr(non_conformita, campo)
                for campo in (
                    "analisi_cause", "azione_risoluzione", "responsabile_azione",
                    "data_inizio_gestione", "azione_immediata", "scadenza_prevista",
                    "esito_efficacia", "verifica_efficacia", "data_verifica",
                    "numero_uda_scartate", "numero_uda_reintegrate", "decisione",
                )
            },
        )
    return render(
        request,
        "magazzino/gestisci_non_conformita.html",
        {"non_conformita": non_conformita, "form": form},
    )


def dettaglio_lotto(request, pk):
    lotto = get_object_or_404(
        Lotto.objects.select_related(
            "articolo",
            "fornitore",
        ),
        pk=pk,
    )

    giacenze = (
        Giacenza.objects
        .filter(
            lotto=lotto,
            quantita__gt=0,
        )
        .select_related(
            "ubicazione",
        )
        .order_by(
            "ubicazione__nome",
        )
    )

    movimenti = (
        Movimento.objects
        .filter(
            lotto=lotto,
        )
        .select_related(
            "ubicazione_origine",
            "ubicazione_destinazione",
        )
        .order_by(
            "-data_ora",
            "-id",
        )
    )

    non_conformita = lotto.non_conformita.select_related(
        "ubicazione_origine",
        "aperta_da",
        "gestita_da",
    ).all()

    quantita_totale = sum(
        (
            giacenza.quantita
            for giacenza in giacenze
        ),
        Decimal("0"),
    )

    inscatolamenti = []

    quantita_inscatolata = Decimal("0")
    quantita_sfusa = quantita_totale

    if lotto.articolo.categoria == Articolo.Categoria.PRODOTTO_FINITO:
        inscatolamenti = (
            Inscatolamento.objects
            .filter(
                lotto_prodotto=lotto,
            )
            .select_related(
                "lotto_imballo__articolo",
            )
            .order_by(
                "data_inscatolamento",
                "id",
            )
        )

        quantita_inscatolata = sum(
            (
                inscatolamento.quantita_prodotti
                for inscatolamento in inscatolamenti
            ),
            Decimal("0"),
        )

        quantita_sfusa = (
            quantita_totale
            - quantita_inscatolata
        )

    # ========================================================
    # TRACCIABILITÀ A MONTE
    # Da quali lotti deriva questo lotto
    # ========================================================

    tracciabilita_monte = []

    produzione = (
        Produzione.objects
        .filter(
            lotto=lotto,
            stato=Produzione.Stato.CONFERMATA,
        )
        .prefetch_related("tank")
        .first()
    )

    if produzione is not None:
        prelievi = (
            produzione.prelievi
            .select_related(
                "lotto__articolo",
                "ubicazione_origine",
            )
            .order_by(
                "id",
            )
        )

        for prelievo in prelievi:
            quantita_scarto = (
                prelievo.quantita_scarto
                if prelievo.quantita_scarto is not None
                else Decimal("0")
            )

            quantita_utilizzata = (
                prelievo.quantita_prelevata
                - quantita_scarto
            )

            tracciabilita_monte.append(
                {
                    "lotto": prelievo.lotto,
                    "quantita_prelevata": prelievo.quantita_prelevata,
                    "quantita_scarto": quantita_scarto,
                    "quantita_utilizzata": quantita_utilizzata,
                    "ubicazione": prelievo.ubicazione_origine,
                    "tipo_produzione": "Prodotto nudo",
                }
            )

    produzioni_semilavorato = (
        ProduzioneSemilavorato.objects
        .filter(
            lotto=lotto,
            stato=ProduzioneSemilavorato.Stato.CONFERMATA,
        )
        .prefetch_related(
            "prelievi__lotto__articolo",
            "prelievi__ubicazione_origine",
        )
    )

    for produzione_semilavorato in produzioni_semilavorato:
        for prelievo in produzione_semilavorato.prelievi.all():
            quantita_scarto = (
                prelievo.quantita_scarto
                if prelievo.quantita_scarto is not None
                else Decimal("0")
            )

            quantita_utilizzata = (
                prelievo.quantita_prelevata
                - quantita_scarto
            )

            tracciabilita_monte.append(
                {
                    "lotto": prelievo.lotto,
                    "quantita_prelevata": prelievo.quantita_prelevata,
                    "quantita_scarto": quantita_scarto,
                    "quantita_utilizzata": quantita_utilizzata,
                    "ubicazione": prelievo.ubicazione_origine,
                    "tipo_produzione": "Semilavorato",
                }
            )

    # ========================================================
    # TRACCIABILITÀ A VALLE
    # In quali lotti è stato utilizzato questo lotto
    # ========================================================

    tracciabilita_valle = []

    prelievi_produzione = (
        lotto.prelievi_produzione
        .filter(
            produzione__stato=Produzione.Stato.CONFERMATA,
            produzione__lotto__isnull=False,
        )
        .select_related(
            "produzione__articolo",
            "produzione__lotto",
            "ubicazione_origine",
        )
        .order_by(
            "produzione__data_produzione",
            "id",
        )
    )

    for prelievo in prelievi_produzione:
        quantita_scarto = (
            prelievo.quantita_scarto
            if prelievo.quantita_scarto is not None
            else Decimal("0")
        )

        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - quantita_scarto
        )

        tracciabilita_valle.append(
            {
                "lotto": prelievo.produzione.lotto,
                "articolo": prelievo.produzione.articolo,
                "quantita_utilizzata": quantita_utilizzata,
                "tipo_produzione": "Prodotto nudo",
            }
        )

    prelievi_semilavorato = (
        lotto.prelievi_produzione_semilavorato
        .filter(
            produzione__stato=ProduzioneSemilavorato.Stato.CONFERMATA,
            produzione__lotto__isnull=False,
        )
        .select_related(
            "produzione__articolo",
            "produzione__lotto",
            "ubicazione_origine",
        )
        .order_by(
            "produzione__data_produzione",
            "id",
        )
    )

    for prelievo in prelievi_semilavorato:
        quantita_scarto = (
            prelievo.quantita_scarto
            if prelievo.quantita_scarto is not None
            else Decimal("0")
        )

        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - quantita_scarto
        )

        tracciabilita_valle.append(
            {
                "lotto": prelievo.produzione.lotto,
                "articolo": prelievo.produzione.articolo,
                "quantita_utilizzata": quantita_utilizzata,
                "tipo_produzione": "Semilavorato",
            }
        )

    return render(
        request,
        "magazzino/dettaglio_lotto.html",
        {
            "lotto": lotto,
            "giacenze": giacenze,
            "movimenti": movimenti,
            "non_conformita": non_conformita,
            "quantita_totale": quantita_totale,
            "quantita_inscatolata": quantita_inscatolata,
            "quantita_sfusa": quantita_sfusa,
            "inscatolamenti": inscatolamenti,
            "tracciabilita_monte": tracciabilita_monte,
            "tracciabilita_valle": tracciabilita_valle,
            "produzione": produzione,
            "tank_produzione": produzione.tank.all() if produzione else [],
        },
    )


def elenco_articoli(request):
    articoli_queryset = (
        Articolo.objects
        .annotate(
            giacenza_totale=Sum(
                "lotti__giacenze__quantita",
                default=Decimal("0"),
            )
        )
        .order_by(
            "codice",
        )
    )

    articoli = Paginator(articoli_queryset, 50).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "magazzino/elenco_articoli.html",
        {
            "articoli": articoli,
            "page_obj": articoli,
        },
    )


def dettaglio_articolo(request, pk):
    articolo = get_object_or_404(
        Articolo,
        pk=pk,
    )

    giacenze = (
        Giacenza.objects
        .filter(
            lotto__articolo=articolo,
            quantita__gt=0,
        )
        .select_related(
            "lotto",
            "ubicazione",
        )
        .order_by(
            "lotto__codice_lotto",
            "ubicazione__nome",
        )
    )

    giacenza_totale = sum(
        (
            giacenza.quantita
            for giacenza in giacenze
        ),
        Decimal("0"),
    )

    lotti = (
        Lotto.objects
        .filter(
            articolo=articolo,
        )
        .annotate(
            giacenza_attuale=Sum(
                "giacenze__quantita",
                default=Decimal("0"),
            ),
        )
        .order_by(
            "-data_produzione",
            "-data_arrivo",
            "-id",
        )
    )

    return render(
        request,
        "magazzino/dettaglio_articolo.html",
        {
            "articolo": articolo,
            "giacenze": giacenze,
            "giacenza_totale": giacenza_totale,
            "lotti": lotti,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuovo_articolo(request):
    if request.method == "POST":
        form = ArticoloForm(request.POST)

        if form.is_valid():
            articolo = form.save()

            messages.success(
                request,
                "Articolo creato correttamente.",
            )

            return redirect(
                "dettaglio_articolo",
                pk=articolo.pk,
            )

    else:
        form = ArticoloForm()

    return render(
        request,
        "magazzino/nuovo_articolo.html",
        {
            "form": form,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_articolo(request, pk):
    articolo = get_object_or_404(
        Articolo,
        pk=pk,
    )

    if request.method == "POST":
        form = ArticoloForm(
            request.POST,
            instance=articolo,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Articolo modificato correttamente.",
            )

            return redirect(
                "dettaglio_articolo",
                pk=articolo.pk,
            )

    else:
        form = ArticoloForm(
            instance=articolo,
        )

    return render(
        request,
        "magazzino/modifica_articolo.html",
        {
            "form": form,
            "articolo": articolo,
        },
    )


def elenco_ricette(request):
    ricette_queryset = Ricetta.objects.select_related(
        "articolo",
    ).prefetch_related(
        "righe__articolo",
    ).order_by(
        "articolo__descrizione",
        "versione",
    )
    ricette_prodotti = Paginator(
        ricette_queryset.filter(
            articolo__categoria=Articolo.Categoria.PRODOTTO_FINITO,
        ),
        50,
    ).get_page(request.GET.get("prodotti_page"))
    ricette_semilavorati = Paginator(
        ricette_queryset.filter(
            articolo__categoria=Articolo.Categoria.SEMILAVORATO,
        ),
        50,
    ).get_page(request.GET.get("semilavorati_page"))

    return render(
        request,
        "magazzino/elenco_ricette.html",
        {
            "ricette_prodotti": ricette_prodotti,
            "ricette_semilavorati": ricette_semilavorati,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def elenco_fornitori(request):
    fornitori = Paginator(
        Fornitore.objects.all().order_by("codice"), 50
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "magazzino/elenco_fornitori.html",
        {"fornitori": fornitori, "page_obj": fornitori},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuovo_fornitore(request):
    form = FornitoreForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fornitore creato correttamente.")
        return redirect("elenco_fornitori")
    return render(
        request,
        "magazzino/anagrafica_form.html",
        {"form": form, "titolo": "Nuovo fornitore", "ritorno": "elenco_fornitori"},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_fornitore(request, pk):
    fornitore = get_object_or_404(Fornitore, pk=pk)
    form = FornitoreForm(request.POST or None, instance=fornitore)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fornitore aggiornato correttamente.")
        return redirect("elenco_fornitori")
    return render(
        request,
        "magazzino/anagrafica_form.html",
        {"form": form, "titolo": "Modifica fornitore", "ritorno": "elenco_fornitori"},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def elenco_ubicazioni(request):
    ubicazioni = Paginator(
        Ubicazione.objects.all().order_by("nome"), 50
    ).get_page(request.GET.get("page"))
    return render(
        request,
        "magazzino/elenco_ubicazioni.html",
        {"ubicazioni": ubicazioni, "page_obj": ubicazioni},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuova_ubicazione(request):
    form = UbicazioneForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ubicazione creata correttamente.")
        return redirect("elenco_ubicazioni")
    return render(
        request,
        "magazzino/anagrafica_form.html",
        {"form": form, "titolo": "Nuova ubicazione", "ritorno": "elenco_ubicazioni"},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_ubicazione(request, pk):
    ubicazione = get_object_or_404(Ubicazione, pk=pk)
    form = UbicazioneForm(request.POST or None, instance=ubicazione)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ubicazione aggiornata correttamente.")
        return redirect("elenco_ubicazioni")
    return render(
        request,
        "magazzino/anagrafica_form.html",
        {"form": form, "titolo": "Modifica ubicazione", "ritorno": "elenco_ubicazioni"},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def importazione_csv(request):
    risultato = None
    form = ImportazioneCSVForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            risultato = importa_csv(
                form.cleaned_data["tipo"],
                form.cleaned_data["file_csv"].read(),
            )
        except ValueError as errore:
            risultato = {
                "errori": [str(errore)],
                "creati": 0,
                "aggiornati": 0,
            }
        if not risultato["errori"]:
            messages.success(
                request,
                f"Importazione completata: {risultato['creati']} creati, "
                f"{risultato['aggiornati']} aggiornati.",
            )
            return redirect("importazione_csv")
    return render(
        request,
        "magazzino/importazione_csv.html",
        {"form": form, "risultato": risultato},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def template_csv(request, tipo):
    try:
        contenuto = genera_template_csv(tipo)
    except KeyError:
        return HttpResponse("Tipo non valido.", status=404)
    response = HttpResponse(contenuto, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="template-{tipo}.csv"'
    return response


@user_passes_test(lambda user: user.is_superuser)
def gestione_backup(request):
    form = RipristinoBackupForm(request.POST or None, request.FILES or None)
    risultato = None
    if request.method == "POST" and form.is_valid():
        try:
            risultato = ripristina_backup(
                form.cleaned_data["file_json"].read()
            )
        except ValueError as errore:
            form.add_error("file_json", str(errore))
        else:
            messages.success(
                request,
                f"Backup ripristinato: {risultato['record']} record. "
                f"Copia precedente: {risultato['backup_precedente']}.",
            )
            return redirect("gestione_backup")
    return render(
        request,
        "magazzino/gestione_backup.html",
        {"form": form, "risultato": risultato},
    )


@user_passes_test(lambda user: user.is_superuser)
def esporta_backup(request):
    registra_operazione(
        utente=request.user,
        azione="Esportazione backup",
        area="Amministrazione",
        descrizione="Esportazione completa dei dati gestionali",
        request=request,
    )
    contenuto = crea_backup()
    nome = datetime.now().strftime("mira-backup-%Y%m%d-%H%M%S.json")
    response = HttpResponse(
        contenuto,
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="{nome}"'
    return response


@user_passes_test(lambda user: user.is_superuser)
def registro_operazioni(request):
    logs = RegistroOperazione.objects.select_related("utente")
    query = request.GET.get("q", "").strip()
    area = request.GET.get("area", "").strip()
    azione = request.GET.get("azione", "").strip()
    esito = request.GET.get("esito", "").strip()
    data_dal = request.GET.get("data_dal", "").strip()
    data_al = request.GET.get("data_al", "").strip()
    if query:
        logs = logs.filter(
            Q(descrizione__icontains=query)
            | Q(utente__username__icontains=query)
            | Q(percorso__icontains=query)
            | Q(azione__icontains=query)
            | Q(area__icontains=query)
            | Q(modello__icontains=query)
            | Q(record_id__icontains=query)
            | Q(oggetto__icontains=query)
            | Q(motivazione__icontains=query)
        )
    if area:
        logs = logs.filter(area=area)
    if azione:
        logs = logs.filter(azione=azione)
    if esito:
        logs = logs.filter(esito=esito)
    if data_dal:
        logs = logs.filter(data_ora__date__gte=data_dal)
    if data_al:
        logs = logs.filter(data_ora__date__lte=data_al)
    aree = RegistroOperazione.objects.order_by("area").values_list(
        "area", flat=True
    ).distinct()
    azioni = RegistroOperazione.objects.order_by("azione").values_list(
        "azione", flat=True
    ).distinct()
    pagina = Paginator(logs, 100).get_page(request.GET.get("page"))
    return render(
        request,
        "magazzino/registro_operazioni.html",
        {
            "logs": pagina,
            "page_obj": pagina,
            "query": query,
            "area_selezionata": area,
            "azione_selezionata": azione,
            "esito_selezionato": esito,
            "esiti": RegistroOperazione.Esito.choices,
            "data_dal": data_dal,
            "data_al": data_al,
            "aree": aree,
            "azioni": azioni,
        },
    )


@user_passes_test(lambda user: user.is_superuser)
def dettaglio_registro_operazione(request, pk):
    log = get_object_or_404(RegistroOperazione.objects.select_related("utente"), pk=pk)
    campi = sorted(set(log.valori_precedenti) | set(log.valori_successivi))
    confronto = [
        {
            "campo": campo,
            "prima": log.valori_precedenti.get(campo),
            "dopo": log.valori_successivi.get(campo),
        }
        for campo in campi
    ]
    return render(
        request,
        "magazzino/dettaglio_registro_operazione.html",
        {"log": log, "confronto": confronto},
    )


def dettaglio_ricetta(request, pk):
    ricetta = get_object_or_404(
        Ricetta.objects.select_related(
            "articolo",
        ).prefetch_related(
            "righe__articolo",
        ),
        pk=pk,
    )

    return render(
        request,
        "magazzino/dettaglio_ricetta.html",
        {
            "ricetta": ricetta,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuova_ricetta(request):
    if request.method == "POST":
        form = RicettaForm(request.POST)

        if form.is_valid():
            ricetta = form.save()

            messages.success(
                request,
                "Ricetta creata correttamente.",
            )

            return redirect(
                "dettaglio_ricetta",
                pk=ricetta.pk,
            )

    else:
        form = RicettaForm()

    prodotti_ricetta = [
        {
            "id": articolo.pk,
            "categoria": articolo.categoria,
            "etichetta": f"{articolo.codice} - {articolo.nome_per_produzione}",
        }
        for articolo in Articolo.objects.filter(
            attivo=True,
            categoria__in=[
                Articolo.Categoria.SEMILAVORATO,
                Articolo.Categoria.PRODOTTO_FINITO,
            ],
        ).order_by("codice")
    ]

    return render(
        request,
        "magazzino/nuova_ricetta.html",
        {
            "form": form,
            "prodotti_ricetta": prodotti_ricetta,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_ricetta(request, pk):
    ricetta = get_object_or_404(Ricetta, pk=pk)

    if request.method == "POST":
        form = RicettaForm(
            request.POST,
            instance=ricetta,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Ricetta modificata correttamente.",
            )

            return redirect(
                "dettaglio_ricetta",
                pk=ricetta.pk,
            )

    else:
        form = RicettaForm(
            instance=ricetta,
        )

    return render(
        request,
        "magazzino/modifica_ricetta.html",
        {
            "form": form,
            "ricetta": ricetta,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def aggiungi_riga_ricetta(request, pk):
    ricetta = get_object_or_404(Ricetta, pk=pk)

    if request.method == "POST":
        form = RigaRicettaForm(request.POST)

        if form.is_valid():
            riga = form.save(
                commit=False,
            )

            riga.ricetta = ricetta

            try:
                riga.save()

            except Exception as e:
                form.add_error(
                    None,
                    str(e),
                )

            else:
                messages.success(
                    request,
                    "Ingrediente aggiunto correttamente.",
                )

                return redirect(
                    "dettaglio_ricetta",
                    pk=ricetta.pk,
                )

    else:
        form = RigaRicettaForm()

    return render(
        request,
        "magazzino/aggiungi_riga_ricetta.html",
        {
            "form": form,
            "ricetta": ricetta,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_riga_ricetta(request, pk):
    riga = get_object_or_404(
        RigaRicetta.objects.select_related(
            "ricetta",
            "ricetta__articolo",
            "articolo",
        ),
        pk=pk,
    )

    ricetta = riga.ricetta

    if request.method == "POST":
        form = RigaRicettaForm(
            request.POST,
            instance=riga,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Ingrediente modificato correttamente.",
            )

            return redirect(
                "dettaglio_ricetta",
                pk=ricetta.pk,
            )

    else:
        form = RigaRicettaForm(
            instance=riga,
        )

    return render(
        request,
        "magazzino/modifica_riga_ricetta.html",
        {
            "form": form,
            "riga": riga,
            "ricetta": ricetta,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def elimina_riga_ricetta(request, pk):
    riga = get_object_or_404(
        RigaRicetta.objects.select_related("ricetta"),
        pk=pk,
    )

    ricetta = riga.ricetta

    if request.method == "POST":
        riga.delete()

        messages.success(
            request,
            "Ingrediente eliminato correttamente.",
        )

        return redirect(
            "dettaglio_ricetta",
            pk=ricetta.pk,
        )

    return render(
        request,
        "magazzino/elimina_riga_ricetta.html",
        {
            "riga": riga,
            "ricetta": ricetta,
        },
    )


# ============================================================
# PRODUZIONE MARMELLATE / PRODOTTO NUDO
# ============================================================

def elenco_produzioni(request, tipo="produzione"):

    if tipo == "semilavorato":
        produzioni_queryset = (
            ProduzioneSemilavorato.objects
            .select_related(
                "articolo",
                "lotto",
                "ubicazione_destinazione",
            )
            .prefetch_related(
                "prelievi",
            )
            .order_by(
                "-data_produzione",
                "-id",
            )
        )

        titolo = "Produzioni semilavorati"
        nuova_produzione_url = "nuova_produzione_semilavorato"
        gestione_url = "gestione_produzione_semilavorato"
        elimina_url = "elimina_produzione_semilavorato"

    else:
        produzioni_queryset = (
            Produzione.objects
            .select_related(
                "articolo",
                "lotto",
                "ubicazione_destinazione",
            )
            .prefetch_related(
                "prelievi",
            )
            .order_by(
                "-data_produzione",
                "-id",
            )
        )

        titolo = "Produzioni marmellate"
        nuova_produzione_url = "nuova_produzione"
        gestione_url = "gestione_produzione"
        elimina_url = "elimina_produzione"

    produzioni = Paginator(produzioni_queryset, 50).get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "magazzino/elenco_produzioni.html",
        {
            "produzioni": produzioni,
            "tipo": tipo,
            "titolo": titolo,
            "nuova_produzione_url": nuova_produzione_url,
            "gestione_url": gestione_url,
            "elimina_url": elimina_url,
            "page_obj": produzioni,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuova_produzione(request):
    if request.method == "POST":
        form = ProduzioneForm(request.POST)

        if form.is_valid():
            articolo = form.cleaned_data["articolo"]

            ricetta = (
                articolo.ricette
                .filter(attiva=True)
                .prefetch_related("righe__articolo")
                .first()
            )

            if ricetta is None:
                form.add_error(
                    "articolo",
                    "Il prodotto selezionato non ha una ricetta attiva.",
                )

            elif not ricetta.righe.exists():
                form.add_error(
                    "articolo",
                    "La ricetta del prodotto non contiene ingredienti.",
                )

            else:
                try:
                    produzione = avvia_produzione(
                        articolo=articolo,
                        data_produzione=form.cleaned_data[
                            "data_produzione"
                        ],
                        note=form.cleaned_data["note"],
                    )
                    produzione.numero_batch_previsti = form.cleaned_data["numero_batch_previsti"]
                    produzione.lotto_provvisorio = (
                        form.cleaned_data["lotto_provvisorio"].strip()
                        or (form.cleaned_data["data_produzione"] + timedelta(days=1)).strftime("%y%m%d")
                    )
                    produzione.save(update_fields=["numero_batch_previsti", "lotto_provvisorio"])

                except ValueError as errore:
                    form.add_error(
                        None,
                        str(errore),
                    )

                else:
                    messages.success(
                        request,
                        "Produzione aperta correttamente.",
                    )

                    return redirect(
                        "gestione_produzione",
                        pk=produzione.pk,
                    )

    else:
        form = ProduzioneForm()

    return render(
        request,
        "magazzino/nuova_produzione.html",
        {
            "form": form,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def modifica_tank(request, pk):
    tank = get_object_or_404(TankProduzione.objects.select_related("produzione"), pk=pk)
    if request.method == "POST":
        form = ModificaTankForm(request.POST, instance=tank)
        if form.is_valid():
            try:
                modifica_tank_produzione(
                    tank,
                    form.cleaned_data["numero_batch"],
                    form.cleaned_data["gradi_brix"],
                    form.cleaned_data["ph"],
                )
            except ValueError as errore:
                form.add_error(None, str(errore))
            else:
                messages.success(request, f"Tank {tank.numero} modificato correttamente.")
                return redirect("gestione_produzione", pk=tank.produzione_id)
    else:
        form = ModificaTankForm(instance=tank)
    return render(request, "magazzino/modifica_tank.html", {"tank": tank, "form": form})


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def annulla_tank(request, pk):
    tank = get_object_or_404(TankProduzione.objects.select_related("produzione"), pk=pk)
    if request.method == "POST":
        form = AnnullaTankForm(request.POST)
        if form.is_valid():
            try:
                annulla_tank_produzione(tank, form.cleaned_data["motivo"], request.user)
            except ValueError as errore:
                form.add_error(None, str(errore))
            else:
                messages.success(request, f"Tank {tank.numero} annullato e conservato nello storico.")
                return redirect("gestione_produzione", pk=tank.produzione_id)
    else:
        form = AnnullaTankForm()
    return render(request, "magazzino/annulla_tank.html", {"tank": tank, "form": form})


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def gestione_produzione(request, pk):
    produzione = get_object_or_404(
        Produzione.objects
        .select_related(
            "articolo",
            "lotto",
            "ubicazione_destinazione",
        )
        .prefetch_related(
            "prelievi__lotto__articolo",
            "prelievi__ubicazione_origine",
            "tank__prelievi",
            "articolo__ricette__righe__articolo",
        ),
        pk=pk,
    )

    ricetta = (
        produzione.articolo.ricette
        .filter(attiva=True)
        .prefetch_related(
            "righe__articolo",
        )
        .first()
    )

    conferma_form = ConfermaProduzioneForm(initial={"lotto_definitivo": produzione.lotto_provvisorio})
    apertura_tank_form = AperturaTankForm()
    controllo_tank_form = ControlloTankForm()
    batch_form = BatchProduzioneForm()
    carrello_form = CarrelloProduzioneForm(produzione=produzione)
    chiusura_carrello_form = ChiusuraCarrelloForm()
    tank_corrente = produzione.tank.filter(
        annullato=False,
        gradi_brix__isnull=True,
    ).order_by("numero").first()
    produzione_url = reverse("gestione_produzione", kwargs={"pk": produzione.pk})

    if request.method == "POST" and request.POST.get("azione") == "chiudi_preparazione":
        if produzione.fase != Produzione.Fase.PREPARAZIONE:
            messages.error(request, "La preparazione è già stata chiusa.")
        elif ricetta is None:
            messages.error(request, "Il prodotto non ha una ricetta attiva.")
        else:
            try:
                righe = list(ricetta.righe.select_related("articolo").filter(ingrediente_prodotto=True))
                quantita = {r.articolo_id: Decimal(request.POST[f"quantita_{r.articolo_id}"].replace(",", ".")) for r in righe}
                note = {r.articolo_id: request.POST.get(f"note_prelievo_{r.articolo_id}", "") for r in righe}
                chiudi_preparazione_produzione(produzione, quantita, note, request.user)
            except (KeyError, InvalidOperation, ValueError) as errore:
                messages.error(request, str(errore) or "Quantità non valide.")
            else:
                messages.success(request, "Preparazione chiusa: prelievi e lotti sono stati registrati.")
        return redirect(f"{produzione_url}#roboqubo")

    if request.method == "POST" and request.POST.get("azione") == "registra_batch":
        batch_form = BatchProduzioneForm(request.POST)
        if produzione.fase != Produzione.Fase.ROBOQUBO:
            batch_form.add_error(None, "La produzione non è nella fase RoboQubo.")
        elif produzione.batch.count() >= produzione.numero_batch_previsti:
            batch_form.add_error(None, "Sono già stati registrati tutti i batch previsti.")
        elif batch_form.is_valid():
            BatchProduzione.objects.create(
                produzione=produzione, numero=produzione.batch.count() + 1,
                registrato_da=request.user, **batch_form.cleaned_data,
            )
            messages.success(request, "Batch registrato correttamente.")
            return redirect(f"{produzione_url}#roboqubo")

    if request.method == "POST" and request.POST.get("azione") == "crea_tank_da_batch":
        ids = request.POST.getlist("batch_ids")
        batch_selezionati = produzione.batch.filter(pk__in=ids, tank__isnull=True)
        if produzione.tank.filter(annullato=False, data_ora_controlli__isnull=True).exists():
            messages.error(request, "Chiudi il tank aperto registrando pH e °Brix prima di crearne un altro.")
        elif not ids or batch_selezionati.count() != len(ids):
            messages.error(request, "Seleziona almeno un batch disponibile.")
        else:
            ultimo = produzione.tank.order_by("-numero").first()
            nuovo_tank = TankProduzione.objects.create(
                produzione=produzione, numero=(ultimo.numero + 1 if ultimo else 1),
                numero_batch=batch_selezionati.count(),
            )
            batch_selezionati.update(tank=nuovo_tank)
            messages.success(request, f"Tank {nuovo_tank.numero} creato e collegato ai batch selezionati.")
        return redirect(f"{produzione_url}#controlli-tank")

    if request.method == "POST" and request.POST.get("azione") == "chiudi_roboqubo":
        if produzione.batch.count() != produzione.numero_batch_previsti:
            messages.error(request, "Registra tutti i batch previsti prima di chiudere RoboQubo.")
        elif produzione.batch.filter(tank__isnull=True).exists():
            messages.error(request, "Tutti i batch devono essere collegati a un tank.")
        elif produzione.tank.filter(annullato=False, data_ora_controlli__isnull=True).exists():
            messages.error(request, "Registra pH e °Brix di tutti i tank.")
        else:
            produzione.fase = Produzione.Fase.INVASETTAMENTO
            produzione.roboqubo_chiuso_il = timezone.now()
            produzione.save(update_fields=["fase", "roboqubo_chiuso_il"])
            messages.success(request, "Fase RoboQubo conclusa.")
        return redirect(f"{produzione_url}#invasettamento")

    if request.method == "POST" and request.POST.get("azione") == "conferma_moca":
        produzione.moca_igienizzati = True
        produzione.moca_igienizzati_il = timezone.now()
        produzione.moca_igienizzati_da = request.user
        produzione.save(update_fields=["moca_igienizzati", "moca_igienizzati_il", "moca_igienizzati_da"])
        messages.success(request, "Pulizia e igienizzazione degli imballaggi MOCA registrata.")
        return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST" and request.POST.get("azione") == "apri_carrello":
        carrello_form = CarrelloProduzioneForm(request.POST, produzione=produzione)
        if not produzione.moca_igienizzati:
            carrello_form.add_error(None, "Conferma prima pulizia e igienizzazione MOCA.")
        elif carrello_form.is_valid():
            CarrelloProduzione.objects.create(
                produzione=produzione, numero=produzione.carrelli.count() + 1,
                registrato_da=request.user, **carrello_form.cleaned_data,
            )
            messages.success(request, "Carrello e seconda pastorizzazione registrati.")
            return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST" and request.POST.get("azione") == "chiudi_carrello":
        carrello = get_object_or_404(produzione.carrelli, pk=request.POST.get("carrello_id"), chiuso_il__isnull=True)
        chiusura_carrello_form = ChiusuraCarrelloForm(request.POST)
        if chiusura_carrello_form.is_valid():
            for campo, valore in chiusura_carrello_form.cleaned_data.items():
                setattr(carrello, campo, valore)
            carrello.shock_vuoto_registrato_il = timezone.now()
            carrello.chiuso_il = timezone.now()
            carrello.save()
            produzione.pastorizzazione_completata = True
            produzione.vuoto_controllato = True
            produzione.data_ora_pastorizzazione = carrello.pastorizzazione_registrata_il
            produzione.data_ora_verifica_vuoto = carrello.shock_vuoto_registrato_il
            produzione.save(update_fields=[
                "pastorizzazione_completata", "vuoto_controllato",
                "data_ora_pastorizzazione", "data_ora_verifica_vuoto",
            ])
            messages.success(request, f"Carrello {carrello.numero} chiuso correttamente.")
            return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST" and request.POST.get("azione") == "apri_tank":
        apertura_tank_form = AperturaTankForm(request.POST)
        if apertura_tank_form.is_valid():
            try:
                apri_tank_produzione(
                    produzione,
                    apertura_tank_form.cleaned_data["numero_batch"],
                )
            except ValueError as errore:
                apertura_tank_form.add_error(None, str(errore))
            else:
                messages.success(request, "Tank aperto correttamente.")
                return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST" and request.POST.get("azione") == "controlla_tank":
        controllo_tank_form = ControlloTankForm(request.POST)
        if tank_corrente is None:
            controllo_tank_form.add_error(None, "Non c'è un tank aperto.")
        elif controllo_tank_form.is_valid():
            try:
                registra_controlli_tank(
                    tank_corrente,
                    controllo_tank_form.cleaned_data["gradi_brix"],
                    controllo_tank_form.cleaned_data["ph"],
                )
            except ValueError as errore:
                controllo_tank_form.add_error(None, str(errore))
            else:
                messages.success(request, "Controlli del tank registrati.")
                return redirect(f"{produzione_url}#roboqubo")

    if request.method == "POST" and request.POST.get("azione") == "registra_pastorizzazione":
        try:
            registra_pastorizzazione(produzione)
        except ValueError as errore:
            messages.error(request, str(errore))
        else:
            messages.success(request, "Pastorizzazione registrata con data e ora.")
        return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST" and request.POST.get("azione") == "registra_verifica_vuoto":
        try:
            registra_verifica_vuoto(produzione)
        except ValueError as errore:
            messages.error(request, str(errore))
        else:
            messages.success(request, "Verifica sottovuoto registrata con data e ora.")
        return redirect("gestione_produzione", pk=produzione.pk)

    if (
        request.method == "POST"
        and request.POST.get("azione") == "registra_scarti_tank"
    ):
        if tank_corrente is None:
            messages.error(request, "Non c'è un tank aperto.")
        else:
            try:
                prelievi_da_completare = tank_corrente.prelievi.filter(
                    quantita_scarto__isnull=True
                )
                scarti_per_prelievo = {
                    prelievo.pk: Decimal(
                        request.POST[f"scarto_{prelievo.pk}"].strip().replace(",", ".")
                    )
                    for prelievo in prelievi_da_completare
                }
                note_per_prelievo = {
                    prelievo.pk: request.POST.get(f"note_scarto_{prelievo.pk}", "").strip()
                    for prelievo in prelievi_da_completare
                }
                registrati = registra_scarti_tank(
                    produzione,
                    tank_corrente,
                    scarti_per_prelievo,
                    note_per_prelievo,
                )
            except (InvalidOperation, KeyError, ValueError) as errore:
                messages.error(request, str(errore) or "Scarti non validi.")
            else:
                messages.success(request, f"Registrati {len(registrati)} scarti del tank.")
                return redirect("gestione_produzione", pk=produzione.pk)

    if (
        request.method == "POST"
        and request.POST.get("azione") == "registra_ingredienti_tank"
    ):
        if produzione.stato != Produzione.Stato.BOZZA:
            messages.error(request, "La produzione non è più in bozza.")
        elif tank_corrente is None:
            messages.error(request, "Apri un tank prima dei prelievi.")
        elif ricetta is None:
            messages.error(request, "Il prodotto non ha una ricetta attiva.")
        else:
            try:
                quantita_per_articolo = {
                    riga.articolo_id: Decimal(
                        request.POST[f"quantita_{riga.articolo_id}"]
                        .strip()
                        .replace(",", ".")
                    )
                    for riga in ricetta.righe.filter(
                        ingrediente_prodotto=True
                    )
                }
                note_per_articolo = {
                    riga.articolo_id: request.POST.get(
                        f"note_prelievo_{riga.articolo_id}", ""
                    ).strip()
                    for riga in ricetta.righe.filter(ingrediente_prodotto=True)
                }
                prelievi_creati = registra_ingredienti_tank(
                    produzione=produzione,
                    tank=tank_corrente,
                    quantita_per_articolo=quantita_per_articolo,
                    note_per_articolo=note_per_articolo,
                    note=f"Prelievi Tank {tank_corrente.numero}",
                    operatore=request.user,
                )
            except (InvalidOperation, KeyError, ValueError) as errore:
                messages.error(request, str(errore) or "Quantità non valide.")
            else:
                messages.success(
                    request,
                    f"Tutti gli ingredienti del tank sono stati prelevati "
                    f"da {len(prelievi_creati)} lotto/i.",
                )
                return redirect("gestione_produzione", pk=produzione.pk)

    if (
        request.method == "POST"
        and request.POST.get("azione") == "conferma_produzione"
    ):
        conferma_form = ConfermaProduzioneForm(
            request.POST
        )

        if produzione.stato != Produzione.Stato.BOZZA:
            conferma_form.add_error(
                None,
                "La produzione non è più in bozza.",
            )

        elif conferma_form.is_valid():
            produzione.lotto_provvisorio = conferma_form.cleaned_data["lotto_definitivo"].strip()
            produzione.save(update_fields=["lotto_provvisorio"])
            prelievi_validi = produzione.prelievi.filter(
                Q(tank__isnull=True) | Q(tank__annullato=False)
            )
            scarti_mancanti = prelievi_validi.filter(
                quantita_scarto__isnull=True,
            ).exists()

            if scarti_mancanti:
                conferma_form.add_error(
                    None,
                    "Prima di confermare la produzione devi registrare "
                    "lo scarto di tutti i prelievi.",
                )

            elif not prelievi_validi.exists():
                conferma_form.add_error(
                    None,
                    "Non è possibile confermare una produzione "
                    "senza prelievi.",
                )

            else:
                try:
                    produzione = conferma_produzione(
                        produzione=produzione,
                        quantita_prodotta=conferma_form.cleaned_data[
                            "quantita_prodotta"
                        ],
                        quantita_ottenuta_kg=conferma_form.cleaned_data[
                            "quantita_ottenuta_kg"
                        ],
                        note=conferma_form.cleaned_data[
                            "note"
                        ],
                        operatore=request.user,
                    )

                except ValueError as errore:
                    conferma_form.add_error(
                        None,
                        str(errore),
                    )

                else:
                    messages.success(
                        request,
                        f"Produzione confermata. "
                        f"Lotto {produzione.lotto.codice_lotto} "
                        f"creato correttamente.",
                    )

                    return redirect(
                        "gestione_produzione",
                        pk=produzione.pk,
                    )

    prelievi = produzione.prelievi.all().order_by(
        "id",
    )
    scarti_tank_mancanti = (
        tank_corrente.prelievi.filter(quantita_scarto__isnull=True).exists()
        if tank_corrente is not None
        else False
    )
    tank_pronto_controlli = (
        tank_corrente is not None
        and tank_corrente.prelievi.exists()
        and not scarti_tank_mancanti
    )

    ingredienti_ricetta = []
    contenitore_formato = None

    if ricetta is not None:
        moltiplicatore = (
            produzione.numero_batch_previsti
            if produzione.fase == Produzione.Fase.PREPARAZIONE
            else (tank_corrente.numero_batch if tank_corrente else 1)
        )
        ingredienti_ricetta = [
            {
                "riga": riga,
                "quantita_prevista": riga.quantita * moltiplicatore,
                "quantita_input": format(riga.quantita * moltiplicatore, "f"),
            }
            for riga in ricetta.righe.select_related("articolo").filter(
                ingrediente_prodotto=True
            )
        ]
        contenitore_formato = next(
            (
                riga.articolo
                for riga in ricetta.righe.select_related("articolo").filter(
                    ingrediente_prodotto=False,
                    articolo__categoria=Articolo.Categoria.MOCA,
                    articolo__formato__isnull=False,
                    articolo__unita_formato__in=[
                        Articolo.UnitaFormato.G,
                        Articolo.UnitaFormato.KG,
                    ],
                ).order_by("id")
            ),
            None,
        )

    return render(
        request,
        "magazzino/gestione_produzione.html",
        {
            "produzione": produzione,
            "ricetta": ricetta,
            "ingredienti_ricetta": ingredienti_ricetta,
            "prelievi": prelievi,
            "scarti_tank_mancanti": scarti_tank_mancanti,
            "tank_pronto_controlli": tank_pronto_controlli,
            "conferma_form": conferma_form,
            "tank": produzione.tank.all(),
            "tank_corrente": tank_corrente,
            "apertura_tank_form": apertura_tank_form,
            "controllo_tank_form": controllo_tank_form,
            "batch_form": batch_form,
            "carrello_form": carrello_form,
            "chiusura_carrello_form": chiusura_carrello_form,
            "batch_non_assegnati": produzione.batch.filter(tank__isnull=True),
            "batch_registrati": produzione.batch.select_related("tank").all(),
            "carrelli": produzione.carrelli.all(),
            "contenitore_formato": contenitore_formato,
            "formato_contenitore_kg": (
                format(contenitore_formato.formato_kg, "f")
                if contenitore_formato is not None
                else ""
            ),
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def invasettamento_produzione(request, pk):
    produzione = get_object_or_404(
        Produzione.objects.select_related("articolo", "lotto", "moca_igienizzati_da")
        .prefetch_related("tank__batch", "carrelli__tank"), pk=pk,
    )
    carrello_form = CarrelloProduzioneForm(produzione=produzione)
    chiusura_form = ChiusuraCarrelloForm()
    conferma_form = ConfermaProduzioneForm(
        initial={"lotto_definitivo": produzione.lotto_provvisorio},
    )
    url = reverse("invasettamento_produzione", kwargs={"pk": produzione.pk})

    if request.method == "POST" and request.POST.get("azione") == "conferma_moca":
        produzione.moca_igienizzati = True
        produzione.moca_igienizzati_il = timezone.now()
        produzione.moca_igienizzati_da = request.user
        produzione.save(update_fields=["moca_igienizzati", "moca_igienizzati_il", "moca_igienizzati_da"])
        messages.success(request, "Igienizzazione MOCA registrata. Ora apri il primo carrello.")
        return redirect(f"{url}#nuovo-carrello")

    if request.method == "POST" and request.POST.get("azione") == "apri_carrello":
        carrello_form = CarrelloProduzioneForm(request.POST, produzione=produzione)
        if not produzione.moca_igienizzati:
            carrello_form.add_error(None, "Conferma prima pulizia e igienizzazione MOCA.")
        elif carrello_form.is_valid():
            CarrelloProduzione.objects.create(
                produzione=produzione, numero=produzione.carrelli.count() + 1,
                registrato_da=request.user, **carrello_form.cleaned_data,
            )
            messages.success(request, "Pastorizzazione registrata. Completa shock termico e vuoto.")
            return redirect(f"{url}#carrello-aperto")

    if request.method == "POST" and request.POST.get("azione") == "chiudi_carrello":
        carrello = get_object_or_404(
            produzione.carrelli, pk=request.POST.get("carrello_id"), chiuso_il__isnull=True,
        )
        chiusura_form = ChiusuraCarrelloForm(request.POST)
        if chiusura_form.is_valid():
            for campo, valore in chiusura_form.cleaned_data.items():
                setattr(carrello, campo, valore)
            carrello.shock_vuoto_registrato_il = timezone.now()
            carrello.chiuso_il = timezone.now()
            carrello.save()
            produzione.pastorizzazione_completata = True
            produzione.vuoto_controllato = True
            produzione.data_ora_pastorizzazione = carrello.pastorizzazione_registrata_il
            produzione.data_ora_verifica_vuoto = carrello.shock_vuoto_registrato_il
            produzione.save(update_fields=[
                "pastorizzazione_completata", "vuoto_controllato",
                "data_ora_pastorizzazione", "data_ora_verifica_vuoto",
            ])
            messages.success(request, f"Carrello {carrello.numero} chiuso. Puoi aprire il successivo.")
            return redirect(f"{url}#nuovo-carrello")

    if request.method == "POST" and request.POST.get("azione") == "conferma_produzione":
        conferma_form = ConfermaProduzioneForm(request.POST)
        if produzione.stato != Produzione.Stato.BOZZA:
            conferma_form.add_error(None, "La produzione è già stata confermata.")
        elif produzione.fase != Produzione.Fase.INVASETTAMENTO:
            conferma_form.add_error(None, "Concludi prima la fase RoboQubo.")
        elif conferma_form.is_valid():
            produzione.lotto_provvisorio = conferma_form.cleaned_data["lotto_definitivo"].strip()
            produzione.save(update_fields=["lotto_provvisorio"])
            try:
                produzione = conferma_produzione(
                    produzione=produzione,
                    quantita_prodotta=conferma_form.cleaned_data["quantita_prodotta"],
                    quantita_ottenuta_kg=conferma_form.cleaned_data["quantita_ottenuta_kg"],
                    note=conferma_form.cleaned_data["note"],
                    operatore=request.user,
                )
            except ValueError as errore:
                conferma_form.add_error(None, str(errore))
            else:
                messages.success(
                    request,
                    f"Produzione confermata e lotto {produzione.lotto.codice_lotto} creato.",
                )
                return redirect(f"{url}#produzione-conclusa")

    return render(request, "magazzino/invasettamento_produzione.html", {
        "produzione": produzione,
        "tank_disponibili": produzione.tank.filter(
            annullato=False,
            data_ora_controlli__isnull=False,
            carrelli__isnull=True,
        ).order_by("numero"),
        "carrelli": produzione.carrelli.all(),
        "carrelli_aperti": produzione.carrelli.filter(chiuso_il__isnull=True).exists(),
        "carrello_form": carrello_form,
        "chiusura_carrello_form": chiusura_form,
        "conferma_form": conferma_form,
    })


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuovo_confezionamento(request):
    confezionamento = None

    if request.method == "POST":
        form = ConfezionamentoForm(request.POST)

        if form.is_valid():
            lotto_origine = form.cleaned_data["lotto_origine"]
            lotto_etichetta = form.cleaned_data["lotto_etichetta"]
            consumi = {
                lotto_etichetta: form.cleaned_data["quantita_confezionata"],
            }

            try:
                confezionamento = registra_confezionamento(
                        lotto_origine=lotto_origine,
                        articolo_finito=lotto_origine.articolo,
                        quantita_confezionata=form.cleaned_data[
                            "quantita_confezionata"
                        ],
                        consumi=consumi,
                        ubicazione_origine=form.cleaned_data[
                            "ubicazione_origine"
                        ],
                        ubicazione_destinazione=form.cleaned_data[
                            "ubicazione_destinazione"
                        ],
                        data_confezionamento=form.cleaned_data[
                            "data_confezionamento"
                        ],
                        note=form.cleaned_data["note"],
                        operatore=request.user,
                )

            except ValueError as errore:
                form.add_error(None, str(errore))

            else:
                messages.success(
                        request,
                        f"Confezionamento del lotto "
                        f"{confezionamento.lotto_origine.codice_lotto} "
                        f"registrato correttamente.",
                )

                return render(
                        request,
                        "magazzino/nuovo_confezionamento.html",
                        {
                            "form": ConfezionamentoForm(),
                            "confezionamento": confezionamento,
                            "confezionamento_completato": True,
                        },
                )

    else:
        form = ConfezionamentoForm()

    return render(
        request,
        "magazzino/nuovo_confezionamento.html",
        {
            "form": form,
            "confezionamento": confezionamento,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuovo_inscatolamento(request):
    inscatolamento = None

    if request.method == "POST":
        form = InscatolamentoForm(request.POST)

        if form.is_valid():
            try:
                inscatolamento = registra_inscatolamento(
                    lotto_prodotto=form.cleaned_data[
                        "lotto_prodotto"
                    ],
                    lotto_imballo=form.cleaned_data[
                        "lotto_imballo"
                    ],
                    quantita_prodotti=form.cleaned_data[
                        "quantita_prodotti"
                    ],
                    ubicazione_prodotto=form.cleaned_data[
                        "ubicazione_prodotto"
                    ],
                    ubicazione_imballo=form.cleaned_data[
                        "ubicazione_imballo"
                    ],
                    data_inscatolamento=form.cleaned_data[
                        "data_inscatolamento"
                    ],
                    note=form.cleaned_data[
                        "note"
                    ],
                    operatore=request.user,
                )

            except ValueError as errore:
                form.add_error(
                    None,
                    str(errore),
                )

            else:
                messages.success(
                    request,
                    "Inscatolamento registrato correttamente.",
                )

                return render(
                    request,
                    "magazzino/nuovo_inscatolamento.html",
                    {
                        "form": InscatolamentoForm(),
                        "inscatolamento": inscatolamento,
                        "inscatolamento_completato": True,
                    },
                )

    else:
        form = InscatolamentoForm()

    return render(
        request,
        "magazzino/nuovo_inscatolamento.html",
        {
            "form": form,
            "inscatolamento": inscatolamento,
        },
    )


# ============================================================
# PRODUZIONE SEMILAVORATI
# ============================================================


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def nuova_produzione_semilavorato(request):
    if request.method == "POST":
        form = ProduzioneSemilavoratoForm(request.POST)

        if form.is_valid():
            produzione = ProduzioneSemilavorato.objects.create(
                articolo=form.cleaned_data["articolo"],
                data_produzione=form.cleaned_data["data_produzione"],
                stato=ProduzioneSemilavorato.Stato.BOZZA,
                note=form.cleaned_data["note"],
            )

            messages.success(
                request,
                "Produzione semilavorato aperta correttamente.",
            )

            return redirect(
                "gestione_produzione_semilavorato",
                pk=produzione.pk,
            )

    else:
        form = ProduzioneSemilavoratoForm()

    return render(
        request,
        "magazzino/nuova_produzione_semilavorato.html",
        {
            "form": form,
        },
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def gestione_produzione_semilavorato(request, pk):
    produzione = get_object_or_404(
        ProduzioneSemilavorato.objects
        .select_related(
            "articolo",
            "lotto",
            "ubicazione_destinazione",
        )
        .prefetch_related(
            "prelievi__lotto__articolo",
            "prelievi__ubicazione_origine",
        ),
        pk=pk,
    )

    ingrediente_form = IngredienteSemilavoratoForm(
        produzione=produzione,
    )

    conferma_form = ConfermaProduzioneSemilavoratoForm()

    if (
        request.method == "POST"
        and request.POST.get("azione") == "registra_scarto"
    ):
        prelievo = get_object_or_404(
            produzione.prelievi,
            pk=request.POST.get("prelievo_id"),
        )

        try:
            quantita_scarto = Decimal(
                request.POST.get(
                    "quantita_scarto",
                    "0",
                )
            )

            registra_scarto_prelievo_semilavorato(
                prelievo=prelievo,
                quantita_scarto=quantita_scarto,
                note=(
                    f"Scarto produzione semilavorato "
                    f"{produzione.pk}"
                ),
            )

        except (ValueError, TypeError) as errore:
            messages.error(
                request,
                str(errore),
            )

        else:
            messages.success(
                request,
                "Scarto registrato correttamente.",
            )

        return redirect(
            "gestione_produzione_semilavorato",
            pk=produzione.pk,
        )

    if (
        request.method == "POST"
        and request.POST.get("azione") == "conferma_produzione"
    ):
        conferma_form = ConfermaProduzioneSemilavoratoForm(
            request.POST
        )

        if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
            conferma_form.add_error(
                None,
                "La produzione non è più in bozza.",
            )

        elif conferma_form.is_valid():
            scarti_mancanti = produzione.prelievi.filter(
                quantita_scarto__isnull=True,
            ).exists()

            if scarti_mancanti:
                messages.error(
                    request,
                    "Prima di confermare la produzione devi registrare "
                    "lo scarto di tutti i prelievi.",
                )

                return redirect(
                    "gestione_produzione_semilavorato",
                    pk=produzione.pk,
                )

            try:
                produzione = conferma_produzione_semilavorato(
                    produzione=produzione,
                    quantita_prodotta=conferma_form.cleaned_data[
                        "quantita_prodotta"
                    ],
                    ubicazione_destinazione=conferma_form.cleaned_data[
                        "ubicazione_destinazione"
                    ],
                    note=conferma_form.cleaned_data[
                        "note"
                    ],
                    operatore=request.user,
                )

            except ValueError as errore:
                conferma_form.add_error(
                    None,
                    str(errore),
                )

            else:
                messages.success(
                    request,
                    f"Produzione confermata. "
                    f"Lotto {produzione.lotto.codice_lotto} "
                    f"creato correttamente.",
                )

                return redirect(
                    "gestione_produzione_semilavorato",
                    pk=produzione.pk,
                )

    if (
        request.method == "POST"
        and request.POST.get("azione") == "aggiungi_ingrediente"
    ):
        ingrediente_form = IngredienteSemilavoratoForm(
            request.POST,
            produzione=produzione,
        )

        if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
            ingrediente_form.add_error(
                None,
                "La produzione non è più in bozza.",
            )

        elif ingrediente_form.is_valid():
            try:
                prelievi_creati = registra_prelievi_semilavorato(
                    produzione=produzione,
                    articolo=ingrediente_form.cleaned_data[
                        "articolo"
                    ],
                    quantita_richiesta=ingrediente_form.cleaned_data[
                        "quantita_richiesta"
                    ],
                    note=(
                        f"Prelievo per produzione semilavorato "
                        f"{produzione.pk}"
                    ),
                    operatore=request.user,
                )

            except ValueError as errore:
                ingrediente_form.add_error(
                    None,
                    str(errore),
                )

            else:
                messages.success(
                    request,
                    f"Prelievo registrato correttamente "
                    f"su {len(prelievi_creati)} lotto/i.",
                )

                return redirect(
                    "gestione_produzione_semilavorato",
                    pk=produzione.pk,
                )

    prelievi = produzione.prelievi.all().order_by(
        "id",
    )

    ricetta = (
        produzione.articolo.ricette
        .filter(
            attiva=True,
        )
        .prefetch_related(
            "righe__articolo",
        )
        .first()
    )

    ingredienti_ricetta = []

    if ricetta is not None:
        ingredienti_ricetta = (
            ricetta.righe
            .select_related(
                "articolo",
            )
            .all()
        )

    return render(
        request,
        "magazzino/gestione_produzione_semilavorato.html",
        {
            "produzione": produzione,
            "ricetta": ricetta,
            "ingredienti_ricetta": ingredienti_ricetta,
            "prelievi": prelievi,
            "ingrediente_form": ingrediente_form,
            "conferma_form": conferma_form,
        },
    )

@permission_required("magazzino.operare_magazzino", raise_exception=True)
def elimina_produzione(request, pk):
    produzione = get_object_or_404(
        Produzione.objects.select_related("articolo", "lotto"),
        pk=pk,
    )
    if produzione.stato != Produzione.Stato.BOZZA:
        messages.error(request, "È possibile eliminare solo le produzioni in bozza.")
        return redirect("gestione_produzione", pk=produzione.pk)

    if request.method == "POST":
        elimina_produzione_bozza(produzione, operatore=request.user)
        messages.success(request, "Produzione in bozza eliminata correttamente.")
        return redirect("elenco_produzioni")

    return render(
        request,
        "magazzino/elimina_produzione.html",
        {"produzione": produzione, "tipo": "produzione"},
    )


@permission_required("magazzino.operare_magazzino", raise_exception=True)
def elimina_produzione_semilavorato(request, pk):
    produzione = get_object_or_404(
        ProduzioneSemilavorato.objects.select_related("articolo", "lotto"),
        pk=pk,
    )
    if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
        messages.error(
            request,
            "È possibile eliminare solo le produzioni semilavorato in bozza.",
        )
        return redirect("gestione_produzione_semilavorato", pk=produzione.pk)

    if request.method == "POST":
        elimina_produzione_semilavorato_bozza(
            produzione,
            operatore=request.user,
        )
        messages.success(
            request,
            "Produzione semilavorato in bozza eliminata correttamente.",
        )
        return redirect("elenco_produzioni_semilavorato")

    return render(
        request,
        "magazzino/elimina_produzione.html",
        {"produzione": produzione, "tipo": "semilavorato"},
    )


def home(request):
    oggi = timezone.localdate()
    limite_scadenza = oggi + timedelta(days=30)
    articoli_sotto_scorta = (
        Articolo.objects.annotate(
            giacenza_attuale=Sum(
                "lotti__giacenze__quantita",
                default=Decimal("0"),
            )
        )
        .filter(
            attivo=True,
            scorta_minima__gt=0,
            giacenza_attuale__lte=F("scorta_minima"),
        )
        .order_by("codice")
    )
    lotti_in_scadenza = (
        Lotto.objects.select_related("articolo")
        .filter(
            data_scadenza__gte=oggi,
            data_scadenza__lte=limite_scadenza,
            giacenze__quantita__gt=0,
        )
        .distinct()
        .order_by("data_scadenza", "codice_lotto")
    )
    produzioni_bozza = Produzione.objects.filter(
        stato=Produzione.Stato.BOZZA
    ).count()
    semilavorati_bozza = ProduzioneSemilavorato.objects.filter(
        stato=ProduzioneSemilavorato.Stato.BOZZA
    ).count()
    movimenti_oggi = Movimento.objects.filter(data_ora__date=oggi).count()

    return render(
        request,
        "magazzino/home.html",
        {
            "numero_sotto_scorta": articoli_sotto_scorta.count(),
            "numero_lotti_scadenza": lotti_in_scadenza.count(),
            "numero_produzioni_bozza": produzioni_bozza + semilavorati_bozza,
            "movimenti_oggi": movimenti_oggi,
            "articoli_sotto_scorta": articoli_sotto_scorta[:5],
            "lotti_in_scadenza": lotti_in_scadenza[:5],
            "oggi": oggi,
            "limite_scadenza": limite_scadenza,
        },
    )
