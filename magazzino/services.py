from decimal import Decimal
from datetime import date

from django.db import transaction

from .models import (
    Lotto,
    Giacenza,
    Movimento,
    Ubicazione,
    Produzione,
    PrelievoProduzione,
    Confezionamento,
    ConsumoConfezionamento,
    Inscatolamento,
)


@transaction.atomic
def registra_carico(
    lotto,
    quantita,
    ubicazione,
    causale="Carico",
    note="",
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if not isinstance(ubicazione, Ubicazione):
        raise ValueError("L'ubicazione non è valida.")
    if not ubicazione.attiva:
        raise ValueError("L'ubicazione non è attiva.")
    if not isinstance(lotto, Lotto):
        raise ValueError("Il lotto non è valido.")
    giacenza, _ = Giacenza.objects.get_or_create(
        lotto=lotto,
        ubicazione=ubicazione,
        defaults={"quantita": Decimal("0")},
    )
    giacenza.quantita += quantita
    giacenza.save(update_fields=["quantita"])
    movimento = Movimento.objects.create(
        tipo=Movimento.Tipo.CARICO,
        lotto=lotto,
        quantita=quantita,
        ubicazione_destinazione=ubicazione,
        causale=causale,
        note=note,
    )
    return movimento


@transaction.atomic
def registra_carico_lotto(
    articolo,
    codice_lotto,
    fornitore,
    quantita,
    ubicazione,
    data_arrivo=None,
    data_scadenza=None,
    causale="Carico",
    note="",
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if not articolo.attivo:
        raise ValueError("L'articolo non è attivo.")
    if fornitore is not None and not fornitore.attivo:
        raise ValueError("Il fornitore non è attivo.")
    if not ubicazione.attiva:
        raise ValueError("L'ubicazione non è attiva.")
    if Lotto.objects.filter(
        articolo=articolo,
        codice_lotto=codice_lotto,
    ).exists():
        raise ValueError(
            f"Il lotto {codice_lotto} per l'articolo "
            f"{articolo.codice} esiste già."
        )
    lotto = Lotto.objects.create(
        articolo=articolo,
        codice_lotto=codice_lotto,
        tipo=Lotto.Tipo.ACQUISTO,
        fornitore=fornitore,
        data_arrivo=data_arrivo,
        data_scadenza=data_scadenza,
        quantita_iniziale=quantita,
        note=note,
    )
    movimento = registra_carico(
        lotto=lotto,
        quantita=quantita,
        ubicazione=ubicazione,
        causale=causale,
        note=note,
    )
    return lotto, movimento


@transaction.atomic
def registra_trasferimento(
    lotto,
    quantita,
    ubicazione_origine,
    ubicazione_destinazione,
    note="",
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if ubicazione_origine == ubicazione_destinazione:
        raise ValueError(
            "L'ubicazione di origine e destinazione devono essere diverse."
        )
    if not ubicazione_origine.attiva:
        raise ValueError("L'ubicazione di origine non è attiva.")
    if not ubicazione_destinazione.attiva:
        raise ValueError("L'ubicazione di destinazione non è attiva.")
    giacenza_origine = Giacenza.objects.filter(
        lotto=lotto,
        ubicazione=ubicazione_origine,
    ).first()
    if giacenza_origine is None or giacenza_origine.quantita < quantita:
        raise ValueError(
            "Quantità insufficiente nell'ubicazione di origine."
        )
    giacenza_destinazione, _ = Giacenza.objects.get_or_create(
        lotto=lotto,
        ubicazione=ubicazione_destinazione,
        defaults={"quantita": Decimal("0")},
    )
    giacenza_origine.quantita -= quantita
    giacenza_origine.save(update_fields=["quantita"])
    giacenza_destinazione.quantita += quantita
    giacenza_destinazione.save(update_fields=["quantita"])
    movimento = Movimento.objects.create(
        tipo=Movimento.Tipo.TRASFERIMENTO,
        lotto=lotto,
        quantita=quantita,
        ubicazione_origine=ubicazione_origine,
        ubicazione_destinazione=ubicazione_destinazione,
        causale="Trasferimento",
        note=note,
    )
    return movimento


@transaction.atomic
def registra_consumo(
    lotto,
    quantita,
    ubicazione_origine,
    causale="Consumo",
    note="",
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if not ubicazione_origine.attiva:
        raise ValueError("L'ubicazione di origine non è attiva.")
    giacenza = Giacenza.objects.filter(
        lotto=lotto,
        ubicazione=ubicazione_origine,
    ).first()
    if giacenza is None or giacenza.quantita < quantita:
        raise ValueError(
            "Quantità insufficiente nell'ubicazione di origine."
        )
    giacenza.quantita -= quantita
    giacenza.save(update_fields=["quantita"])
    movimento = Movimento.objects.create(
        tipo=Movimento.Tipo.CONSUMO,
        lotto=lotto,
        quantita=quantita,
        ubicazione_origine=ubicazione_origine,
        ubicazione_destinazione=None,
        causale=causale,
        note=note,
    )
    return movimento


def genera_codice_lotto_produzione(articolo, data_produzione):
    base = data_produzione.strftime("%y%m%d")
    codice = base
    progressivo = 0

    articoli_da_controllare = [articolo]

    if (
        articolo.categoria == articolo.Categoria.PRODOTTO_NUDO
        and articolo.prodotto_finito_collegato is not None
    ):
        articoli_da_controllare.append(
            articolo.prodotto_finito_collegato
        )

    while Lotto.objects.filter(
        articolo__in=articoli_da_controllare,
        codice_lotto=codice,
    ).exists():
        progressivo += 1

        if progressivo <= 26:
            suffisso = chr(64 + progressivo)
        else:
            primo = (progressivo - 1) // 26
            secondo = (progressivo - 1) % 26 + 1

            suffisso = (
                chr(64 + primo)
                + chr(64 + secondo)
            )

        codice = f"{suffisso}{base}"

    return codice


@transaction.atomic
def avvia_produzione(
    articolo,
    data_produzione=None,
    note="",
):
    if not articolo.attivo:
        raise ValueError("L'articolo non è attivo.")

    if articolo.categoria != articolo.Categoria.PRODOTTO_NUDO:
        raise ValueError(
            "La produzione deve riferirsi a un prodotto nudo."
        )

    if data_produzione is None:
        data_produzione = date.today()

    ricetta = (
        articolo.ricette
        .filter(attiva=True)
        .prefetch_related("righe__articolo")
        .first()
    )

    if ricetta is None:
        raise ValueError(
            f"L'articolo {articolo.codice} non ha una ricetta attiva."
        )

    if not ricetta.righe.exists():
        raise ValueError(
            f"La ricetta {ricetta.nome} non contiene ingredienti."
        )

    return Produzione.objects.create(
        articolo=articolo,
        data_produzione=data_produzione,
        stato=Produzione.Stato.BOZZA,
        note=note,
    )


def _articolo_ammesso_in_produzione(produzione, articolo):
    if articolo.categoria == articolo.Categoria.MOCA:
        return True

    ricetta = (
        produzione.articolo.ricette
        .filter(attiva=True)
        .order_by("id")
        .first()
    )

    if ricetta is None:
        return False

    return ricetta.righe.filter(articolo=articolo).exists()


@transaction.atomic
def registra_prelievi_produzione(
    produzione,
    articolo,
    quantita_richiesta,
    note="",
):
    if not isinstance(produzione, Produzione):
        raise ValueError("La produzione non è valida.")

    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError(
            "È possibile registrare prelievi solo "
            "su una produzione in bozza."
        )

    if not articolo.attivo:
        raise ValueError("L'articolo non è attivo.")

    categorie_ammesse = {
        articolo.Categoria.MATERIA_PRIMA,
        articolo.Categoria.SEMILAVORATO,
        articolo.Categoria.MOCA,
    }

    if articolo.categoria not in categorie_ammesse:
        raise ValueError(
            "L'articolo selezionato non può essere prelevato "
            "per questa produzione."
        )

    if not _articolo_ammesso_in_produzione(produzione, articolo):
        raise ValueError(
            f"L'articolo {articolo.codice} non appartiene alla ricetta "
            "e non è un materiale MOCA."
        )

    risultato = proponi_prelievi_articolo(
        articolo,
        quantita_richiesta,
    )

    if not risultato["completa"]:
        raise ValueError(
            f"Quantità insufficiente per {articolo.codice}: "
            f"richiesti {risultato['quantita_richiesta']}, "
            f"disponibili {risultato['quantita_disponibile']}, "
            f"mancano {risultato['quantita_mancante']}."
        )

    prelievi = []

    for riga in risultato["righe"]:
        giacenza = (
            Giacenza.objects
            .select_for_update()
            .get(
                lotto=riga["lotto"],
                ubicazione=riga["ubicazione"],
            )
        )

        quantita_prelevata = riga["quantita_proposta"]

        if giacenza.quantita < quantita_prelevata:
            raise ValueError(
                f"La giacenza del lotto "
                f"{giacenza.lotto.codice_lotto} è cambiata. "
                "Ripetere la proposta di prelievo."
            )

        giacenza.quantita -= quantita_prelevata
        giacenza.save(update_fields=["quantita"])

        Movimento.objects.create(
            tipo=Movimento.Tipo.CONSUMO,
            lotto=giacenza.lotto,
            quantita=quantita_prelevata,
            ubicazione_origine=giacenza.ubicazione,
            ubicazione_destinazione=None,
            causale="Prelievo produzione marmellata",
            note=note,
        )

        prelievo = PrelievoProduzione.objects.create(
            produzione=produzione,
            lotto=giacenza.lotto,
            ubicazione_origine=giacenza.ubicazione,
            quantita_prelevata=quantita_prelevata,
            quantita_scarto=None,
            note=note,
        )

        prelievi.append(prelievo)

    return prelievi


@transaction.atomic
def registra_scarto_prelievo_produzione(
    prelievo,
    quantita_scarto,
    note="",
):
    if not isinstance(prelievo, PrelievoProduzione):
        raise ValueError(
            "Il prelievo non è valido."
        )

    if prelievo.produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError(
            "Lo scarto può essere registrato solo "
            "per una produzione in bozza."
        )

    quantita_scarto = Decimal(
        str(quantita_scarto)
    )

    if quantita_scarto < 0:
        raise ValueError(
            "La quantità di scarto non può essere negativa."
        )

    if quantita_scarto > prelievo.quantita_prelevata:
        raise ValueError(
            "La quantità di scarto non può essere maggiore "
            "della quantità prelevata."
        )

    if prelievo.quantita_scarto is not None:
        raise ValueError(
            "Lo scarto di questo prelievo è già stato registrato."
        )

    prelievo.quantita_scarto = quantita_scarto

    if note:
        prelievo.note = note

    prelievo.save(
        update_fields=[
            "quantita_scarto",
            "note",
        ]
    )

    return prelievo


@transaction.atomic
def conferma_produzione(
    produzione,
    quantita_prodotta,
    ubicazione_destinazione=None,
    note="",
):
    if not isinstance(produzione, Produzione):
        raise ValueError("La produzione non è valida.")

    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione non è in bozza.")

    if produzione.lotto is not None:
        raise ValueError(
            "La produzione ha già un lotto associato."
        )

    quantita_prodotta = Decimal(str(quantita_prodotta))

    if quantita_prodotta <= 0:
        raise ValueError(
            "La quantità prodotta deve essere maggiore di zero."
        )

    if not produzione.prelievi.exists():
        raise ValueError(
            "Non sono stati registrati prelievi per questa produzione."
        )

    scarti_mancanti = produzione.prelievi.filter(
        quantita_scarto__isnull=True,
    ).exists()

    if scarti_mancanti:
        raise ValueError(
            "Prima di confermare la produzione devi registrare "
            "lo scarto di tutti i prelievi."
        )

    ricetta = (
        produzione.articolo.ricette
        .filter(attiva=True)
        .prefetch_related("righe__articolo")
        .first()
    )

    if ricetta is None:
        raise ValueError(
            f"L'articolo {produzione.articolo.codice} "
            "non ha una ricetta attiva."
        )

    prelievi = list(
        produzione.prelievi.select_related("lotto__articolo")
    )

    utilizzo_per_articolo = {}
    for prelievo in prelievi:
        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - prelievo.quantita_scarto
        )
        articolo_id = prelievo.lotto.articolo_id
        utilizzo_per_articolo[articolo_id] = (
            utilizzo_per_articolo.get(articolo_id, Decimal("0"))
            + quantita_utilizzata
        )

    ingredienti_mancanti = []
    for riga in ricetta.righe.select_related("articolo").all():
        if utilizzo_per_articolo.get(riga.articolo_id, Decimal("0")) <= 0:
            ingredienti_mancanti.append(
                f"{riga.articolo.codice} - {riga.articolo.descrizione}"
            )

    if ingredienti_mancanti:
        raise ValueError(
            "Non è possibile confermare la produzione. "
            "Mancano prelievi effettivamente utilizzati per: "
            + ", ".join(ingredienti_mancanti)
            + "."
        )

    if ubicazione_destinazione is None:
        ubicazione_destinazione = (
            Ubicazione.objects
            .filter(
                tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING,
                attiva=True,
            )
            .order_by("id")
            .first()
        )

    if ubicazione_destinazione is None:
        raise ValueError(
            "Non esiste un'ubicazione attiva per il Magazzino Packaging."
        )

    if not ubicazione_destinazione.attiva:
        raise ValueError(
            "L'ubicazione di destinazione non è attiva."
        )

    if (
        ubicazione_destinazione.tipo_magazzino
        != Ubicazione.TipoMagazzino.PACKAGING
    ):
        raise ValueError(
            "La destinazione deve essere un'ubicazione Packaging."
        )

    codice_lotto = genera_codice_lotto_produzione(
        produzione.articolo,
        produzione.data_produzione,
    )

    lotto = Lotto.objects.create(
        articolo=produzione.articolo,
        codice_lotto=codice_lotto,
        tipo=Lotto.Tipo.PRODUZIONE,
        data_produzione=produzione.data_produzione,
        quantita_iniziale=quantita_prodotta,
        note=note,
    )

    Giacenza.objects.create(
        lotto=lotto,
        ubicazione=ubicazione_destinazione,
        quantita=quantita_prodotta,
    )

    Movimento.objects.create(
        tipo=Movimento.Tipo.PRODUZIONE,
        lotto=lotto,
        quantita=quantita_prodotta,
        ubicazione_origine=None,
        ubicazione_destinazione=ubicazione_destinazione,
        causale="Produzione marmellata - prodotto nudo",
        note=note,
    )

    produzione.lotto = lotto
    produzione.quantita_prodotta = quantita_prodotta
    produzione.ubicazione_destinazione = ubicazione_destinazione
    produzione.stato = Produzione.Stato.CONFERMATA

    if note:
        produzione.note = note

    produzione.save(
        update_fields=[
            "lotto",
            "quantita_prodotta",
            "ubicazione_destinazione",
            "stato",
            "note",
        ]
    )

    return produzione


@transaction.atomic
def registra_produzione(
    articolo,
    quantita_prodotta,
    consumi,
    data_produzione=None,
    note="",
):
    """Compatibilità temporanea con le vecchie view.

    Il nuovo flusso operativo usa avvia_produzione(),
    registra_prelievi_produzione(), registra_residuo_prelievo_produzione()
    e conferma_produzione().
    """
    produzione = avvia_produzione(
        articolo=articolo,
        data_produzione=data_produzione,
        note=note,
    )

    for articolo_consumato, quantita in consumi.items():
        prelievi = registra_prelievi_produzione(
            produzione=produzione,
            articolo=articolo_consumato,
            quantita_richiesta=quantita,
            note=note,
        )
        for prelievo in prelievi:
            registra_scarto_prelievo_produzione(
                prelievo=prelievo,
                quantita_scarto=Decimal("0"),
                note=note,
            )

    return conferma_produzione(
        produzione=produzione,
        quantita_prodotta=quantita_prodotta,
        note=note,
    )


@transaction.atomic
def registra_confezionamento(
    lotto_origine,
    articolo_finito,
    quantita_confezionata,
    consumi,
    ubicazione_origine,
    ubicazione_destinazione,
    data_confezionamento=None,
    note="",
):
    quantita_confezionata = Decimal(str(quantita_confezionata))

    if quantita_confezionata <= 0:
        raise ValueError(
            "La quantità confezionata deve essere maggiore di zero."
        )

    if lotto_origine.articolo.categoria != lotto_origine.articolo.Categoria.PRODOTTO_NUDO:
        raise ValueError(
            "Il lotto di origine deve appartenere a un prodotto nudo."
        )

    if articolo_finito.categoria != articolo_finito.Categoria.PRODOTTO_FINITO:
        raise ValueError(
            "L'articolo di destinazione deve essere un prodotto finito."
        )

    if not articolo_finito.attivo:
        raise ValueError(
            "Il prodotto finito non è attivo."
        )

    if not ubicazione_origine.attiva:
        raise ValueError(
            "L'ubicazione di origine non è attiva."
        )

    if not ubicazione_destinazione.attiva:
        raise ValueError(
            "L'ubicazione di destinazione non è attiva."
        )

    if ubicazione_destinazione.tipo_magazzino != Ubicazione.TipoMagazzino.PRODOTTI_FINITI:
        raise ValueError(
            "L'ubicazione di destinazione deve essere un magazzino prodotti finiti."
        )

    if data_confezionamento is None:
        data_confezionamento = date.today()

    giacenza_origine = (
        Giacenza.objects
        .select_for_update()
        .filter(
            lotto=lotto_origine,
            ubicazione=ubicazione_origine,
        )
        .first()
    )

    if (
        giacenza_origine is None
        or giacenza_origine.quantita < quantita_confezionata
    ):
        raise ValueError(
            "Quantità insufficiente di prodotto nudo."
        )

    consumi_preparati = []

    for lotto_packaging, quantita in consumi.items():
        quantita = Decimal(str(quantita))

        if quantita <= 0:
            raise ValueError(
                f"La quantità per {lotto_packaging.articolo.codice} "
                "deve essere maggiore di zero."
            )

        if lotto_packaging.articolo.categoria != lotto_packaging.articolo.Categoria.PACKAGING:
            raise ValueError(
                f"L'articolo {lotto_packaging.articolo.codice} "
                "non è un materiale di packaging."
            )

        giacenze = list(
            Giacenza.objects
            .select_related(
                "lotto",
                "ubicazione",
            )
            .select_for_update()
            .filter(
                lotto=lotto_packaging,
                quantita__gt=0,
                ubicazione__attiva=True,
            )
            .order_by(
                "ubicazione_id",
            )
        )

        totale_disponibile = sum(
            (
                giacenza.quantita
                for giacenza in giacenze
            ),
            Decimal("0"),
        )

        if totale_disponibile < quantita:
            raise ValueError(
                f"Quantità insufficiente per "
                f"{lotto_packaging.articolo.codice}: "
                f"richiesti {quantita}, "
                f"disponibili {totale_disponibile}."
            )

        consumi_preparati.append(
            {
                "lotto": lotto_packaging,
                "quantita": quantita,
                "giacenze": giacenze,
            }
        )

    codice_lotto = lotto_origine.codice_lotto

    lotto_finito = (
        Lotto.objects
        .filter(
            articolo=articolo_finito,
            codice_lotto=codice_lotto,
        )
        .first()
    )

    if lotto_finito is None:
        lotto_finito = Lotto.objects.create(
            articolo=articolo_finito,
            codice_lotto=codice_lotto,
            tipo=Lotto.Tipo.PRODUZIONE,
            data_produzione=lotto_origine.data_produzione,
            quantita_iniziale=quantita_confezionata,
            note=note,
        )

    confezionamento = Confezionamento.objects.create(
        lotto_origine=lotto_origine,
        articolo_finito=articolo_finito,
        lotto_finito=lotto_finito,
        quantita_confezionata=quantita_confezionata,
        data_confezionamento=data_confezionamento,
        note=note,
    )

    giacenza_origine.quantita -= quantita_confezionata
    giacenza_origine.save(
        update_fields=["quantita"]
    )

    Movimento.objects.create(
        tipo=Movimento.Tipo.PACKAGING,
        lotto=lotto_origine,
        quantita=quantita_confezionata,
        ubicazione_origine=ubicazione_origine,
        ubicazione_destinazione=None,
        causale="Prodotto nudo confezionato",
        note=note,
    )

    giacenza_finito, _ = Giacenza.objects.get_or_create(
        lotto=lotto_finito,
        ubicazione=ubicazione_destinazione,
        defaults={
            "quantita": Decimal("0"),
        },
    )

    giacenza_finito.quantita += quantita_confezionata
    giacenza_finito.save(
        update_fields=["quantita"]
    )

    Movimento.objects.create(
        tipo=Movimento.Tipo.PACKAGING,
        lotto=lotto_finito,
        quantita=quantita_confezionata,
        ubicazione_origine=None,
        ubicazione_destinazione=ubicazione_destinazione,
        causale="Prodotto finito da confezionamento",
        note=note,
    )

    for dati in consumi_preparati:
        quantita_da_consumare = dati["quantita"]

        for giacenza in dati["giacenze"]:
            if quantita_da_consumare <= 0:
                break

            quantita_consumata = min(
                giacenza.quantita,
                quantita_da_consumare,
            )

            if quantita_consumata <= 0:
                continue

            giacenza.quantita -= quantita_consumata
            giacenza.save(
                update_fields=["quantita"]
            )

            Movimento.objects.create(
                tipo=Movimento.Tipo.PACKAGING,
                lotto=giacenza.lotto,
                quantita=quantita_consumata,
                ubicazione_origine=giacenza.ubicazione,
                ubicazione_destinazione=None,
                causale="Consumo materiale packaging",
                note=note,
            )

            ConsumoConfezionamento.objects.create(
                confezionamento=confezionamento,
                lotto=giacenza.lotto,
                ubicazione=giacenza.ubicazione,
                quantita_utilizzata=quantita_consumata,
            )

            quantita_da_consumare -= quantita_consumata

    return confezionamento

@transaction.atomic
def registra_inscatolamento(
    lotto_prodotto,
    lotto_imballo,
    quantita_prodotti,
    ubicazione_prodotto,
    ubicazione_imballo,
    data_inscatolamento=None,
    note="",
):
    quantita_prodotti = Decimal(str(quantita_prodotti))

    if quantita_prodotti <= 0:
        raise ValueError(
            "La quantità da inscatolare deve essere maggiore di zero."
        )

    if lotto_prodotto.articolo.categoria != lotto_prodotto.articolo.Categoria.PRODOTTO_FINITO:
        raise ValueError(
            "Il lotto da inscatolare deve appartenere a un prodotto finito."
        )

    if lotto_imballo.articolo.categoria != lotto_imballo.articolo.Categoria.PACKAGING:
        raise ValueError(
            "Il lotto imballo deve appartenere a un articolo packaging."
        )

    if lotto_imballo.articolo.tipo_packaging not in [
        lotto_imballo.articolo.TipoPackaging.SCATOLA,
        lotto_imballo.articolo.TipoPackaging.COFANETTO,
    ]:
        raise ValueError(
            "Il materiale selezionato non è una scatola o un cofanetto."
        )

    pezzi_per_imballo = lotto_imballo.articolo.pezzi_per_imballo

    if pezzi_per_imballo is None or pezzi_per_imballo <= 0:
        raise ValueError(
            "Il materiale di imballo non ha un numero valido "
            "di pezzi per imballo."
        )

    pezzi_per_imballo = Decimal(str(pezzi_per_imballo))

    if quantita_prodotti % pezzi_per_imballo != 0:
        raise ValueError(
            f"La quantità da inscatolare deve essere un multiplo "
            f"di {pezzi_per_imballo}."
        )

    quantita_imballi = quantita_prodotti / pezzi_per_imballo

    if data_inscatolamento is None:
        data_inscatolamento = date.today()

    giacenza_prodotto = (
        Giacenza.objects
        .select_for_update()
        .filter(
            lotto=lotto_prodotto,
            ubicazione=ubicazione_prodotto,
        )
        .first()
    )

    if giacenza_prodotto is None:
        raise ValueError(
            "Il prodotto finito non è presente "
            "nell'ubicazione selezionata."
        )

    gia_inscatolati = sum(
        (
            inscatolamento.quantita_prodotti
            for inscatolamento in lotto_prodotto.inscatolamenti.all()
        ),
        Decimal("0"),
    )

    quantita_sfusa = (
        giacenza_prodotto.quantita
        - gia_inscatolati
    )

    if quantita_sfusa < quantita_prodotti:
        raise ValueError(
            f"Quantità sfusa insufficiente. "
            f"Disponibili {quantita_sfusa}, "
            f"richiesti {quantita_prodotti}."
        )

    giacenza_imballo = (
        Giacenza.objects
        .select_for_update()
        .filter(
            lotto=lotto_imballo,
            ubicazione=ubicazione_imballo,
        )
        .first()
    )

    if (
        giacenza_imballo is None
        or giacenza_imballo.quantita < quantita_imballi
    ):
        disponibile = (
            giacenza_imballo.quantita
            if giacenza_imballo is not None
            else Decimal("0")
        )

        raise ValueError(
            f"Imballi insufficienti. "
            f"Richiesti {quantita_imballi}, "
            f"disponibili {disponibile}."
        )

    inscatolamento = Inscatolamento.objects.create(
        lotto_prodotto=lotto_prodotto,
        lotto_imballo=lotto_imballo,
        quantita_prodotti=quantita_prodotti,
        quantita_imballi=quantita_imballi,
        pezzi_per_imballo=int(pezzi_per_imballo),
        data_inscatolamento=data_inscatolamento,
        note=note,
    )

    giacenza_imballo.quantita -= quantita_imballi
    giacenza_imballo.save(
        update_fields=["quantita"]
    )

    Movimento.objects.create(
        tipo=Movimento.Tipo.PACKAGING,
        lotto=lotto_imballo,
        quantita=quantita_imballi,
        ubicazione_origine=ubicazione_imballo,
        ubicazione_destinazione=None,
        causale="Consumo imballo per inscatolamento",
        note=note,
    )

    return inscatolamento

def proponi_prelievi_articolo(
    articolo,
    quantita_richiesta,
):
    quantita_richiesta = Decimal(str(quantita_richiesta))

    if quantita_richiesta <= 0:
        raise ValueError(
            "La quantità richiesta deve essere maggiore di zero."
        )

    if not articolo.attivo:
        raise ValueError(
            "L'articolo non è attivo."
        )

    giacenze = list(
        Giacenza.objects
        .select_related(
            "lotto",
            "ubicazione",
        )
        .filter(
            lotto__articolo=articolo,
            quantita__gt=0,
            ubicazione__attiva=True,
        )
    )

    if articolo.criterio_rotazione == articolo.CriterioRotazione.FEFO:
        giacenze.sort(
            key=lambda g: (
                g.lotto.data_scadenza is None,
                g.lotto.data_scadenza or date.max,
                g.lotto.data_arrivo
                or g.lotto.data_produzione
                or date.max,
                g.lotto.id,
                g.ubicazione.id,
            )
        )

    elif articolo.criterio_rotazione == articolo.CriterioRotazione.FIFO:
        giacenze.sort(
            key=lambda g: (
                g.lotto.data_arrivo
                or g.lotto.data_produzione
                or date.max,
                g.lotto.id,
                g.ubicazione.id,
            )
        )

    else:
        giacenze.sort(
            key=lambda g: (
                g.lotto.id,
                g.ubicazione.id,
            )
        )

    quantita_disponibile = sum(
        (
            giacenza.quantita
            for giacenza in giacenze
        ),
        Decimal("0"),
    )

    quantita_da_proporre = quantita_richiesta
    proposta = []

    for giacenza in giacenze:
        if quantita_da_proporre <= 0:
            break

        quantita_proposta = min(
            giacenza.quantita,
            quantita_da_proporre,
        )

        proposta.append(
            {
                "lotto": giacenza.lotto,
                "ubicazione": giacenza.ubicazione,
                "disponibile": giacenza.quantita,
                "quantita_proposta": quantita_proposta,
            }
        )

        quantita_da_proporre -= quantita_proposta

    return {
        "articolo": articolo,
        "criterio": articolo.criterio_rotazione,
        "quantita_richiesta": quantita_richiesta,
        "quantita_disponibile": quantita_disponibile,
        "quantita_mancante": max(
            Decimal("0"),
            quantita_richiesta - quantita_disponibile,
        ),
        "completa": quantita_disponibile >= quantita_richiesta,
        "righe": proposta,
    }

@transaction.atomic
def registra_prelievi_semilavorato(
    produzione,
    articolo,
    quantita_richiesta,
    note="",
):
    from .models import (
        ProduzioneSemilavorato,
        PrelievoProduzioneSemilavorato,
    )

    if not isinstance(produzione, ProduzioneSemilavorato):
        raise ValueError(
            "La produzione semilavorato non è valida."
        )

    if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
        raise ValueError(
            "È possibile registrare prelievi solo "
            "su una produzione in bozza."
        )

    risultato = proponi_prelievi_articolo(
        articolo,
        quantita_richiesta,
    )

    if not risultato["completa"]:
        raise ValueError(
            f"Quantità insufficiente per "
            f"{articolo.codice}: "
            f"richiesti {risultato['quantita_richiesta']}, "
            f"disponibili {risultato['quantita_disponibile']}, "
            f"mancano {risultato['quantita_mancante']}."
        )

    prelievi = []

    for riga in risultato["righe"]:
        giacenza = (
            Giacenza.objects
            .select_for_update()
            .get(
                lotto=riga["lotto"],
                ubicazione=riga["ubicazione"],
            )
        )

        quantita_prelevata = riga["quantita_proposta"]

        if giacenza.quantita < quantita_prelevata:
            raise ValueError(
                f"La giacenza del lotto "
                f"{giacenza.lotto.codice_lotto} "
                "è cambiata. Ripetere la proposta di prelievo."
            )

        giacenza.quantita -= quantita_prelevata
        giacenza.save(
            update_fields=["quantita"]
        )

        Movimento.objects.create(
            tipo=Movimento.Tipo.CONSUMO,
            lotto=giacenza.lotto,
            quantita=quantita_prelevata,
            ubicazione_origine=giacenza.ubicazione,
            ubicazione_destinazione=None,
            causale="Prelievo produzione semilavorato",
            note=note,
        )

        prelievo = PrelievoProduzioneSemilavorato.objects.create(
            produzione=produzione,
            lotto=giacenza.lotto,
            ubicazione_origine=giacenza.ubicazione,
            quantita_prelevata=quantita_prelevata,
            quantita_scarto=None,
            note=note,
        )

        prelievi.append(prelievo)

    return prelievi


@transaction.atomic
def registra_scarto_prelievo_semilavorato(
    prelievo,
    quantita_scarto,
    note="",
):
    from .models import (
        PrelievoProduzioneSemilavorato,
        ProduzioneSemilavorato,
    )

    if not isinstance(
        prelievo,
        PrelievoProduzioneSemilavorato,
    ):
        raise ValueError(
            "Il prelievo non è valido."
        )

    if (
        prelievo.produzione.stato
        != ProduzioneSemilavorato.Stato.BOZZA
    ):
        raise ValueError(
            "Lo scarto può essere registrato solo "
            "per una produzione in bozza."
        )

    quantita_scarto = Decimal(
        str(quantita_scarto)
    )

    if quantita_scarto < 0:
        raise ValueError(
            "La quantità di scarto non può essere negativa."
        )

    if quantita_scarto > prelievo.quantita_prelevata:
        raise ValueError(
            "La quantità di scarto non può essere maggiore "
            "della quantità prelevata."
        )

    if prelievo.quantita_scarto is not None:
        raise ValueError(
            "Lo scarto di questo prelievo è già stato registrato."
        )

    prelievo.quantita_scarto = quantita_scarto

    if note:
        prelievo.note = note

    prelievo.save(
        update_fields=[
            "quantita_scarto",
            "note",
        ]
    )

    return prelievo


@transaction.atomic
def conferma_produzione_semilavorato(
    produzione,
    quantita_prodotta,
    ubicazione_destinazione,
    note="",
):
    from .models import ProduzioneSemilavorato

    if not isinstance(produzione, ProduzioneSemilavorato):
        raise ValueError(
            "La produzione semilavorato non è valida."
        )

    if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
        raise ValueError(
            "La produzione semilavorato non è in bozza."
        )

    if produzione.lotto is not None:
        raise ValueError(
            "La produzione ha già un lotto associato."
        )

    if not produzione.prelievi.exists():
        raise ValueError(
            "Non sono stati registrati prelievi "
            "per questa produzione."
        )

    scarti_mancanti = produzione.prelievi.filter(
        quantita_scarto__isnull=True,
    ).exists()

    if scarti_mancanti:
        raise ValueError(
            "Prima di confermare la produzione devi registrare "
            "lo scarto di tutti i prelievi."
        )

    quantita_prodotta = Decimal(
        str(quantita_prodotta)
    )

    if quantita_prodotta <= 0:
        raise ValueError(
            "La quantità prodotta deve essere maggiore di zero."
        )

    if not ubicazione_destinazione.attiva:
        raise ValueError(
            "L'ubicazione di destinazione non è attiva."
        )

    if (
        ubicazione_destinazione.tipo_magazzino
        != Ubicazione.TipoMagazzino.SEMILAVORATI
    ):
        raise ValueError(
            "La destinazione deve essere "
            "un'ubicazione semilavorati."
        )

    codice_lotto = genera_codice_lotto_produzione(
        produzione.articolo,
        produzione.data_produzione,
    )

    lotto = Lotto.objects.create(
        articolo=produzione.articolo,
        codice_lotto=codice_lotto,
        tipo=Lotto.Tipo.PRODUZIONE,
        data_produzione=produzione.data_produzione,
        quantita_iniziale=quantita_prodotta,
        note=note,
    )

    Giacenza.objects.create(
        lotto=lotto,
        ubicazione=ubicazione_destinazione,
        quantita=quantita_prodotta,
    )

    Movimento.objects.create(
        tipo=Movimento.Tipo.PRODUZIONE,
        lotto=lotto,
        quantita=quantita_prodotta,
        ubicazione_origine=None,
        ubicazione_destinazione=ubicazione_destinazione,
        causale="Produzione semilavorato",
        note=note,
    )

    produzione.lotto = lotto
    produzione.quantita_prodotta = quantita_prodotta
    produzione.ubicazione_destinazione = ubicazione_destinazione
    produzione.stato = ProduzioneSemilavorato.Stato.CONFERMATA

    if note:
        produzione.note = note

    produzione.save(
        update_fields=[
            "lotto",
            "quantita_prodotta",
            "ubicazione_destinazione",
            "stato",
            "note",
        ]
    )

    return produzione