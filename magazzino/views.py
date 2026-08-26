from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import permission_required, user_passes_test
from django.db.models import OuterRef, Q, Subquery, Sum
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, JsonResponse

from .forms import (
    CaricoLottoForm,
    TrasferimentoForm,
    ConsumoForm,
    RicettaForm,
    RigaRicettaForm,
    ProduzioneForm,
    IngredienteProduzioneForm,
    ScartoProduzioneForm,
    ConfermaProduzioneForm,
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
)

from .services import (
    registra_carico_lotto,
    registra_trasferimento,
    registra_consumo,
    avvia_produzione,
    registra_prelievi_produzione,
    registra_scarto_prelievo_produzione,
    conferma_produzione,
    registra_confezionamento,
    registra_inscatolamento,
    registra_prelievi_semilavorato,
    registra_scarto_prelievo_semilavorato,
    conferma_produzione_semilavorato,
    elimina_produzione_bozza,
    elimina_produzione_semilavorato_bozza,
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
                    ubicazione=form.cleaned_data["ubicazione"],
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
                    ubicazione_destinazione=form.cleaned_data[
                        "ubicazione_destinazione"
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
                    "posizione": str(giacenza.ubicazione),
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
        Articolo.objects.all().order_by("descrizione"),
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

    giacenze = Paginator(
        Giacenza.objects.select_related(
            "lotto__articolo",
            "ubicazione",
        ).filter(
            quantita__gt=0,
        ).order_by(
            "lotto__articolo__descrizione",
            "lotto__codice_lotto",
            "ubicazione__nome",
        ),
        50,
    ).get_page(request.GET.get("giacenze_page"))
    giacenze.object_list = list(giacenze.object_list)

    lotto_ids = {
        giacenza.lotto_id for giacenza in giacenze.object_list
    }

    totali_lotto = {
        riga["lotto_id"]: riga["totale"]
        for riga in (
            Giacenza.objects.filter(lotto_id__in=lotto_ids)
            .values("lotto_id")
            .annotate(totale=Sum("quantita"))
        )
    }

    totali_inscatolati = {
        riga["lotto_prodotto_id"]: riga["totale"]
        for riga in (
            Inscatolamento.objects.filter(lotto_prodotto_id__in=lotto_ids)
            .values("lotto_prodotto_id")
            .annotate(totale=Sum("quantita_prodotti"))
        )
    }

    for giacenza in giacenze.object_list:
        lotto = giacenza.lotto
        giacenza.quantita_totale = totali_lotto.get(
            lotto.pk,
            Decimal("0"),
        )
        giacenza.quantita_inscatolata = totali_inscatolati.get(
            lotto.pk,
            Decimal("0"),
        )
        giacenza.quantita_sfusa = (
            giacenza.quantita_totale - giacenza.quantita_inscatolata
        )

    return render(
        request,
        "magazzino/situazione_magazzino.html",
        {
            "articoli": articoli,
            "giacenze": giacenze,
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
                    causale=form.cleaned_data["causale"],
                    note=form.cleaned_data["note"],
                    operatore=request.user,
                )

            except ValueError as e:
                form.add_error(None, str(e))

            else:
                messages.success(
                    request,
                    f"Consumo del lotto "
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
            "quantita_totale": quantita_totale,
            "quantita_inscatolata": quantita_inscatolata,
            "quantita_sfusa": quantita_sfusa,
            "inscatolamenti": inscatolamenti,
            "tracciabilita_monte": tracciabilita_monte,
            "tracciabilita_valle": tracciabilita_valle,
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
            articolo__categoria=Articolo.Categoria.PRODOTTO_NUDO,
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
    data_dal = request.GET.get("data_dal", "").strip()
    data_al = request.GET.get("data_al", "").strip()
    if query:
        logs = logs.filter(
            Q(descrizione__icontains=query)
            | Q(utente__username__icontains=query)
            | Q(percorso__icontains=query)
        )
    if area:
        logs = logs.filter(area=area)
    if azione:
        logs = logs.filter(azione=azione)
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
            "data_dal": data_dal,
            "data_al": data_al,
            "aree": aree,
            "azioni": azioni,
        },
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

    return render(
        request,
        "magazzino/nuova_ricetta.html",
        {
            "form": form,
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

    ingrediente_form = IngredienteProduzioneForm(
        produzione=produzione,
    )

    conferma_form = ConfermaProduzioneForm()

    if (
        request.method == "POST"
        and request.POST.get("azione") == "registra_scarto"
    ):
        prelievo = get_object_or_404(
            produzione.prelievi,
            pk=request.POST.get("prelievo_id"),
        )

        scarto_form = ScartoProduzioneForm(
            request.POST,
            prelievo=prelievo,
        )

        if scarto_form.is_valid():
            try:
                registra_scarto_prelievo_produzione(
                    prelievo=prelievo,
                    quantita_scarto=scarto_form.cleaned_data[
                        "quantita_scarto"
                    ],
                    note=scarto_form.cleaned_data[
                        "note"
                    ],
                )

            except ValueError as errore:
                messages.error(
                    request,
                    str(errore),
                )

            else:
                messages.success(
                    request,
                    "Scarto registrato correttamente.",
                )

        else:
            messaggi = []

            for errori_campo in scarto_form.errors.values():
                for errore in errori_campo:
                    messaggi.append(str(errore))

            messages.error(
                request,
                " ".join(messaggi)
                or "Scarto non valido.",
            )

        return redirect(
            "gestione_produzione",
            pk=produzione.pk,
        )

    if (
        request.method == "POST"
        and request.POST.get("azione") == "aggiungi_ingrediente"
    ):
        ingrediente_form = IngredienteProduzioneForm(
            request.POST,
            produzione=produzione,
        )

        if produzione.stato != Produzione.Stato.BOZZA:
            ingrediente_form.add_error(
                None,
                "La produzione non è più in bozza.",
            )

        elif ingrediente_form.is_valid():
            try:
                prelievi_creati = registra_prelievi_produzione(
                    produzione=produzione,
                    articolo=ingrediente_form.cleaned_data[
                        "articolo"
                    ],
                    quantita_richiesta=ingrediente_form.cleaned_data[
                        "quantita_richiesta"
                    ],
                    note=(
                        f"Prelievo per produzione "
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
                    "gestione_produzione",
                    pk=produzione.pk,
                )

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
            scarti_mancanti = produzione.prelievi.filter(
                quantita_scarto__isnull=True,
            ).exists()

            if scarti_mancanti:
                conferma_form.add_error(
                    None,
                    "Prima di confermare la produzione devi registrare "
                    "lo scarto di tutti i prelievi.",
                )

            elif not produzione.prelievi.exists():
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

    ingredienti_ricetta = []

    if ricetta is not None:
        ingredienti_ricetta = ricetta.righe.select_related(
            "articolo",
        ).all()

    return render(
        request,
        "magazzino/gestione_produzione.html",
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
def nuovo_confezionamento(request):
    confezionamento = None

    if request.method == "POST":
        form = ConfezionamentoForm(request.POST)

        if form.is_valid():
            lotto_origine = form.cleaned_data["lotto_origine"]

            articolo_finito = (
                lotto_origine.articolo.prodotto_finito_collegato
            )

            if articolo_finito is None:
                form.add_error(
                    "lotto_origine",
                    "Il prodotto nudo selezionato non ha "
                    "un prodotto finito collegato.",
                )

            else:
                lotto_etichetta = form.cleaned_data[
                    "lotto_etichetta"
                ]

                consumi = {
                    lotto_etichetta: form.cleaned_data[
                        "quantita_confezionata"
                    ],
                }

                try:
                    confezionamento = registra_confezionamento(
                        lotto_origine=lotto_origine,
                        articolo_finito=articolo_finito,
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
                    form.add_error(
                        None,
                        str(errore),
                    )

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
    return render(
        request,
        "magazzino/home.html",
    )
