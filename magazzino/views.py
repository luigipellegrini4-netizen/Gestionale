from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    CaricoLottoForm,
    TrasferimentoForm,
    ConsumoForm,
    RicettaForm,
    RigaRicettaForm,
    ProduzioneForm,
    IngredienteProduzioneForm,
    ResiduoProduzioneForm,
    ConfermaProduzioneForm,
    ConfezionamentoForm,
    InscatolamentoForm,
    ProduzioneSemilavoratoForm,
    IngredienteSemilavoratoForm,
    ConfermaProduzioneSemilavoratoForm,
    ArticoloForm,
)

from .services import (
    registra_carico_lotto,
    registra_trasferimento,
    registra_consumo,
    avvia_produzione,
    registra_prelievi_produzione,
    registra_residuo_prelievo_produzione,
    conferma_produzione,
    registra_confezionamento,
    registra_inscatolamento,
    registra_prelievi_semilavorato,
    registra_residuo_prelievo_semilavorato,
    conferma_produzione_semilavorato,
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
)


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


def trasferimento(request):
    if request.method == "POST":
        form = TrasferimentoForm(request.POST)

        if form.is_valid():
            try:
                movimento = registra_trasferimento(
                    lotto=form.cleaned_data["lotto"],
                    quantita=form.cleaned_data["quantita"],
                    ubicazione_origine=form.cleaned_data[
                        "ubicazione_origine"
                    ],
                    ubicazione_destinazione=form.cleaned_data[
                        "ubicazione_destinazione"
                    ],
                    note=form.cleaned_data["note"],
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


def situazione_magazzino(request):
    giacenze = list(
        Giacenza.objects.select_related(
            "lotto__articolo",
            "ubicazione",
        ).filter(
            quantita__gt=0,
        ).order_by(
            "lotto__articolo__descrizione",
            "lotto__codice_lotto",
            "ubicazione__nome",
        )
    )

    lotti = {}

    for giacenza in giacenze:
        lotto = giacenza.lotto

        if lotto.pk not in lotti:
            quantita_totale = sum(
                (
                    g.quantita
                    for g in Giacenza.objects.filter(
                        lotto=lotto,
                    )
                ),
                Decimal("0"),
            )

            quantita_inscatolata = Decimal("0")

            if (
                lotto.articolo.categoria
                == Articolo.Categoria.PRODOTTO_FINITO
            ):
                quantita_inscatolata = sum(
                    (
                        i.quantita_prodotti
                        for i in Inscatolamento.objects.filter(
                            lotto_prodotto=lotto,
                        )
                    ),
                    Decimal("0"),
                )

            lotti[lotto.pk] = {
                "totale": quantita_totale,
                "inscatolata": quantita_inscatolata,
                "sfusa": (
                    quantita_totale
                    - quantita_inscatolata
                ),
            }

        dati = lotti[lotto.pk]

        giacenza.quantita_totale = dati["totale"]
        giacenza.quantita_inscatolata = dati["inscatolata"]
        giacenza.quantita_sfusa = dati["sfusa"]

    return render(
        request,
        "magazzino/situazione_magazzino.html",
        {
            "giacenze": giacenze,
        },
    )


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
    movimenti = Movimento.objects.select_related(
        "lotto__articolo",
        "ubicazione_origine",
        "ubicazione_destinazione",
    ).order_by(
        "-data_ora",
        "-id",
    )

    return render(
        request,
        "magazzino/elenco_movimenti.html",
        {"movimenti": movimenti},
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
            quantita_residua = (
                prelievo.quantita_residua
                if prelievo.quantita_residua is not None
                else Decimal("0")
            )

            quantita_utilizzata = (
                prelievo.quantita_prelevata
                - quantita_residua
            )

            tracciabilita_monte.append(
                {
                    "lotto": prelievo.lotto,
                    "quantita_prelevata": prelievo.quantita_prelevata,
                    "quantita_residua": quantita_residua,
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
            quantita_residua = (
                prelievo.quantita_residua
                if prelievo.quantita_residua is not None
                else Decimal("0")
            )

            quantita_utilizzata = (
                prelievo.quantita_prelevata
                - quantita_residua
            )

            tracciabilita_monte.append(
                {
                    "lotto": prelievo.lotto,
                    "quantita_prelevata": prelievo.quantita_prelevata,
                    "quantita_residua": quantita_residua,
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
        quantita_residua = (
            prelievo.quantita_residua
            if prelievo.quantita_residua is not None
            else Decimal("0")
        )

        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - quantita_residua
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
        quantita_residua = (
            prelievo.quantita_residua
            if prelievo.quantita_residua is not None
            else Decimal("0")
        )

        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - quantita_residua
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
    articoli = (
        Articolo.objects
        .all()
        .order_by(
            "codice",
        )
    )

    for articolo in articoli:
        articolo.giacenza_totale = sum(
            (
                giacenza.quantita
                for giacenza in Giacenza.objects.filter(
                    lotto__articolo=articolo,
                )
            ),
            Decimal("0"),
        )

    return render(
        request,
        "magazzino/elenco_articoli.html",
        {
            "articoli": articoli,
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
    ricette = Ricetta.objects.select_related(
        "articolo",
    ).prefetch_related(
        "righe__articolo",
    ).order_by(
        "articolo__descrizione",
        "versione",
    )

    return render(
        request,
        "magazzino/elenco_ricette.html",
        {
            "ricette": ricette,
        },
    )


def dettaglio_ricetta(request, pk):
    ricetta = Ricetta.objects.select_related(
        "articolo",
    ).prefetch_related(
        "righe__articolo",
    ).get(pk=pk)

    return render(
        request,
        "magazzino/dettaglio_ricetta.html",
        {
            "ricetta": ricetta,
        },
    )


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


def modifica_ricetta(request, pk):
    ricetta = Ricetta.objects.get(pk=pk)

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


def aggiungi_riga_ricetta(request, pk):
    ricetta = Ricetta.objects.get(pk=pk)

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


def modifica_riga_ricetta(request, pk):
    riga = RigaRicetta.objects.select_related(
        "ricetta",
        "ricetta__articolo",
        "articolo",
    ).get(pk=pk)

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


def elimina_riga_ricetta(request, pk):
    riga = RigaRicetta.objects.select_related(
        "ricetta",
    ).get(pk=pk)

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

def elenco_produzioni(request):
    produzioni = (
        Produzione.objects
        .select_related(
            "articolo",
            "lotto",
            "ubicazione_destinazione",
        )
        .order_by(
            "-data_produzione",
            "-id",
        )
    )

    return render(
        request,
        "magazzino/elenco_produzioni.html",
        {
            "produzioni": produzioni,
        },
    )


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
        and request.POST.get("azione") == "registra_residuo"
    ):
        prelievo = get_object_or_404(
            produzione.prelievi,
            pk=request.POST.get("prelievo_id"),
        )

        residuo_form = ResiduoProduzioneForm(
            request.POST,
            prelievo=prelievo,
        )

        if residuo_form.is_valid():
            try:
                registra_residuo_prelievo_produzione(
                    prelievo=prelievo,
                    quantita_residua=residuo_form.cleaned_data[
                        "quantita_residua"
                    ],
                    note=residuo_form.cleaned_data[
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
                    "Residuo registrato correttamente.",
                )

        else:
            messaggi = []

            for errori_campo in residuo_form.errors.values():
                for errore in errori_campo:
                    messaggi.append(str(errore))

            messages.error(
                request,
                " ".join(messaggi)
                or "Residuo non valido.",
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
            residui_mancanti = produzione.prelievi.filter(
                quantita_residua__isnull=True,
            ).exists()

            if residui_mancanti:
                conferma_form.add_error(
                    None,
                    "Prima di confermare la produzione devi registrare "
                    "il residuo di tutti i prelievi.",
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

def elenco_produzioni_semilavorato(request):
    produzioni = (
        ProduzioneSemilavorato.objects
        .select_related(
            "articolo",
            "lotto",
            "ubicazione_destinazione",
        )
        .order_by(
            "-data_produzione",
            "-id",
        )
    )

    return render(
        request,
        "magazzino/elenco_produzioni_semilavorato.html",
        {
            "produzioni": produzioni,
        },
    )


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
        and request.POST.get("azione") == "registra_residuo"
    ):
        prelievo = get_object_or_404(
            produzione.prelievi,
            pk=request.POST.get("prelievo_id"),
        )

        try:
            quantita_residua = Decimal(
                request.POST.get(
                    "quantita_residua",
                    "0",
                )
            )

            registra_residuo_prelievo_semilavorato(
                prelievo=prelievo,
                quantita_residua=quantita_residua,
                note=(
                    f"Residuo produzione semilavorato "
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
                "Residuo registrato correttamente.",
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
            residui_mancanti = produzione.prelievi.filter(
                quantita_residua__isnull=True,
            ).exists()

            if residui_mancanti:
                messages.error(
                    request,
                    "Prima di confermare la produzione devi registrare "
                    "il residuo di tutti i prelievi.",
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

def home(request):
    return render(
        request,
        "magazzino/home.html",
    )