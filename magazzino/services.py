from decimal import Decimal, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    Articolo,
    Lotto,
    Giacenza,
    Movimento,
    NonConformitaLotto,
    BatchProduzione,
    MaterialeSospesoNonConformita,
    LottoUscitaProduzione,
    Ubicazione,
    Produzione,
    TankProduzione,
    PrelievoProduzione,
    Confezionamento,
    ConsumoConfezionamento,
    Inscatolamento,
)


def calcola_quantita_teorica_ricetta(produzione, numero_batch=None):
    """Quantità di prodotto prevista: ingredienti di un batch × batch della lavorazione."""
    ricetta = produzione.articolo.ricette.filter(attiva=True).first()
    if ricetta is None:
        raise ValueError(
            f"L'articolo {produzione.articolo.codice} non ha una ricetta attiva."
        )
    quantita_per_batch = sum(
        ricetta.righe.filter(ingrediente_prodotto=True).values_list("quantita", flat=True),
        Decimal("0"),
    )
    batch = produzione.numero_batch_previsti if numero_batch is None else numero_batch
    return (quantita_per_batch * Decimal(batch)).quantize(Decimal("0.001"))


@transaction.atomic
def concludi_invasettamento_senza_nuovo_lotto(produzione):
    """Conclude una fase i cui tank sono già confluiti in lotti di uscita."""
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione è già stata conclusa.")
    if produzione.stato_roboqubo != Produzione.StatoRoboqubo.CONCLUSA:
        raise ValueError("RoboQubo deve essere concluso prima dell’invasettamento.")
    if produzione.tank.filter(
        annullato=False, data_ora_controlli__isnull=False,
        stato_invasettamento=TankProduzione.StatoInvasettamento.DISPONIBILE,
    ).exists():
        raise ValueError("Ci sono ancora tank da invasettare.")
    if produzione.carrelli.filter(lotto_uscita__isnull=True).exists():
        raise ValueError("Ci sono ancora carrelli da associare alla chiusura.")

    uscite = list(produzione.lotti_uscita.select_related("lotto"))
    if not uscite:
        raise ValueError("Non risultano lotti di invasettamento già registrati.")
    quantita_prodotta = sum(
        (Decimal(uscita.numero_vasetti_buoni or 0) for uscita in uscite), Decimal("0"),
    )
    quantita_ottenuta = sum(
        (uscita.quantita_ottenuta_kg or Decimal("0") for uscita in uscite), Decimal("0"),
    )
    quantita_teorica = calcola_quantita_teorica_ricetta(produzione)
    # Il riferimento riepilogativo è valorizzato soltanto quando il lotto è
    # realmente unico; con più uscite la fonte è l'elenco lotti_uscita.
    produzione.lotto = uscite[0].lotto if len(uscite) == 1 else None
    produzione.quantita_prodotta = quantita_prodotta
    produzione.quantita_ottenuta_kg = quantita_ottenuta
    pesi_netti = {u.peso_netto_vasetto_g for u in uscite if u.peso_netto_vasetto_g is not None}
    produzione.peso_netto_vasetto_g = pesi_netti.pop() if len(pesi_netti) == 1 else None
    produzione.quantita_teorica_kg = quantita_teorica
    produzione.resa_percentuale = (
        quantita_ottenuta / quantita_teorica * Decimal("100")
        if quantita_teorica > 0 else None
    )
    produzione.pezzi_difettosi_finali = sum(u.numero_vasetti_scartati for u in uscite)
    produzione.capsule_difettose_finali = sum(u.numero_capsule_difettose for u in uscite)
    produzione.difetti_registrati_il = timezone.now()
    produzione.fase = Produzione.Fase.COMPLETATA
    produzione.stato = Produzione.Stato.CONFERMATA
    produzione.stato_invasettamento = Produzione.StatoInvasettamento.CONCLUSO
    produzione.invasettamento_congelato = False
    produzione.save(update_fields=[
        "lotto", "quantita_prodotta", "quantita_ottenuta_kg", "peso_netto_vasetto_g",
        "quantita_teorica_kg", "resa_percentuale", "pezzi_difettosi_finali",
        "capsule_difettose_finali", "difetti_registrati_il", "fase", "stato",
        "stato_invasettamento", "invasettamento_congelato",
    ])
    return produzione


@transaction.atomic
def conferma_lotto_parziale_produzione(
    produzione,
    codice_lotto,
    quantita_prodotta,
    peso_netto_vasetto_g,
    pezzi_difettosi_finali,
    capsule_difettose_finali,
    note,
    operatore,
):
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA or not produzione.invasettamento_congelato:
        raise ValueError("Il lotto parziale è consentito solo per una produzione congelata da NC.")
    tank = produzione.tank.filter(
        annullato=False, data_ora_controlli__isnull=False,
        stato_invasettamento=TankProduzione.StatoInvasettamento.DISPONIBILE,
    )
    carrelli = produzione.carrelli.filter(chiuso_il__isnull=False, lotto_uscita__isnull=True)
    if not tank.exists():
        raise ValueError("Non ci sono tank completati ancora da invasettare.")
    if not carrelli.exists():
        raise ValueError("Non ci sono carrelli completati per questo lotto.")
    if produzione.carrelli.filter(chiuso_il__isnull=True).exists():
        raise ValueError("Completa tutti i carrelli aperti.")

    quantita_prodotta = int(quantita_prodotta)
    scarti = int(pezzi_difettosi_finali)
    peso = Decimal(str(peso_netto_vasetto_g))
    quantita_ottenuta = (Decimal(quantita_prodotta + scarti) * peso / Decimal("1000")).quantize(Decimal("0.001"))
    batch_nei_tank = sum((t.numero_batch for t in tank), 0)
    quantita_teorica = calcola_quantita_teorica_ricetta(
        produzione, numero_batch=batch_nei_tank,
    )
    resa = (
        quantita_ottenuta / quantita_teorica * Decimal("100")
        if quantita_teorica > 0 else None
    )
    if Lotto.objects.filter(articolo=produzione.articolo, codice_lotto=codice_lotto).exists():
        raise ValueError("Il numero lotto indicato è già utilizzato per questo articolo.")

    ricetta = produzione.articolo.ricette.filter(attiva=True).prefetch_related("righe__articolo").first()
    if ricetta is None:
        raise ValueError("Il prodotto non ha una ricetta attiva.")
    vasetti_totali = Decimal(quantita_prodotta + scarti)
    for riga in ricetta.righe.select_related("articolo").filter(
        ingrediente_prodotto=False, articolo__categoria=Articolo.Categoria.MOCA,
    ):
        for prelievo in registra_prelievi_produzione(
            produzione=produzione,
            articolo=riga.articolo,
            quantita_richiesta=vasetti_totali * riga.quantita,
            note=f"MOCA lotto definitivo parziale {codice_lotto}: {riga.articolo.codice}",
            operatore=operatore,
        ):
            registra_scarto_prelievo_produzione(prelievo, Decimal("0"))

    ubicazione = Ubicazione.objects.filter(
        tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING, attiva=True,
    ).order_by("id").first()
    if ubicazione is None:
        raise ValueError("Non esiste un'ubicazione attiva per il Magazzino Packaging.")
    lotto = Lotto.objects.create(
        articolo=produzione.articolo,
        codice_lotto=codice_lotto,
        tipo=Lotto.Tipo.PRODUZIONE,
        fase=Lotto.Fase.INVASETTATO,
        data_produzione=timezone.localdate(),
        quantita_iniziale=quantita_prodotta,
        note=note,
    )
    Giacenza.objects.create(lotto=lotto, ubicazione=ubicazione, quantita=quantita_prodotta)
    Movimento.objects.create(
        tipo=Movimento.Tipo.PRODUZIONE,
        lotto=lotto,
        quantita=quantita_prodotta,
        ubicazione_destinazione=ubicazione,
        causale="Produzione parziale chiusa durante NC RoboQubo",
        note=note,
        eseguito_da=operatore,
    )
    uscita = LottoUscitaProduzione.objects.create(
        produzione=produzione,
        lotto=lotto,
        non_conformita=produzione.non_conformita.exclude(stato=NonConformitaLotto.Stato.CHIUSA).first(),
        provvisorio=False,
        motivo_separazione="Chiusura definitiva dell'invasettato disponibile durante NC RoboQubo",
        numero_vasetti_buoni=quantita_prodotta,
        numero_vasetti_scartati=scarti,
        numero_capsule_difettose=int(capsule_difettose_finali),
        peso_netto_vasetto_g=peso,
        quantita_ottenuta_kg=quantita_ottenuta,
        quantita_teorica_kg=quantita_teorica,
        resa_percentuale=resa,
        note=note,
    )
    tank.update(
        stato_invasettamento=TankProduzione.StatoInvasettamento.INVASETTATO,
        invasettato_il=timezone.now(),
    )
    carrelli.update(lotto_uscita=uscita)
    produzione.moca_igienizzati = False
    produzione.moca_igienizzati_il = None
    produzione.moca_igienizzati_da = None
    produzione.stato_invasettamento = Produzione.StatoInvasettamento.CONGELATO
    produzione.save(update_fields=[
        "moca_igienizzati", "moca_igienizzati_il", "moca_igienizzati_da",
        "stato_invasettamento",
    ])
    return uscita


@transaction.atomic
def apri_non_conformita_batch(batch, produzione_puo_proseguire, motivo, operatore):
    batch = BatchProduzione.objects.select_for_update().select_related("produzione").get(pk=batch.pk)
    produzione = Produzione.objects.select_for_update().get(pk=batch.produzione_id)
    if batch.esito_conformita != "NC":
        raise ValueError("La quarantena può essere aperta solo per un batch non conforme.")
    if hasattr(batch, "non_conformita"):
        raise ValueError("Per questo batch esiste già una non conformità.")

    puo_proseguire = bool(produzione_puo_proseguire)
    nc = NonConformitaLotto.objects.create(
        produzione=produzione,
        batch=batch,
        lotto_temporaneo=produzione.lotto_provvisorio,
        produzione_puo_proseguire=puo_proseguire,
        numero_batch_origine=batch.numero,
        ambito=NonConformitaLotto.Ambito.PRODUZIONE,
        tipo_nc=NonConformitaLotto.Tipo.INTERNO,
        motivo=motivo or f"Batch {batch.numero} non conforme",
        note_apertura=(
            "Batch messo in quarantena; produzione autorizzata a proseguire dall'operatore."
            if puo_proseguire else
            "Batch messo in quarantena; fase RoboQubo sospesa dall'operatore."
        ),
        aperta_da=operatore,
    )
    batch.stato = BatchProduzione.Stato.QUARANTENA
    batch.quarantena_il = timezone.now()
    batch.save(update_fields=["stato", "quarantena_il"])
    produzione.invasettamento_congelato = True
    if produzione.stato_invasettamento != Produzione.StatoInvasettamento.NON_AVVIATO:
        produzione.stato_invasettamento = Produzione.StatoInvasettamento.CONGELATO
    produzione.stato_roboqubo = (
        Produzione.StatoRoboqubo.CON_NC
        if puo_proseguire else Produzione.StatoRoboqubo.SOSPESA
    )
    produzione.save(update_fields=[
        "invasettamento_congelato", "stato_roboqubo", "stato_invasettamento",
    ])

    if puo_proseguire:
        oggi = timezone.localdate()
        base_temp = f"TEMP{oggi:%y%m%d}"
        progressivo = 1
        nuovo_temp = f"{progressivo}{base_temp}"
        while Produzione.objects.filter(lotto_provvisorio=nuovo_temp).exists():
            progressivo += 1
            nuovo_temp = f"{progressivo}{base_temp}"

        nuova_produzione = Produzione.objects.create(
            articolo=produzione.articolo,
            data_produzione=oggi,
            lotto_provvisorio=nuovo_temp,
            numero_batch_previsti=1,
            fase=Produzione.Fase.PREPARAZIONE,
            stato_roboqubo=Produzione.StatoRoboqubo.SOSPESA,
            invasettamento_congelato=True,
            derivata_da=produzione,
            bloccata_da_nc=nc,
            note=f"Batch in quarantena trasferito automaticamente dalla NC-{nc.pk}.",
        )
        nuova_produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(nuova_produzione)
        nuova_produzione.save(update_fields=["quantita_teorica_kg"])
        batch.produzione = nuova_produzione
        batch.numero = 1
        batch.save(update_fields=["produzione", "numero"])

        rapporto_batch = Decimal("1") / Decimal(produzione.numero_batch_previsti)
        for prelievo in produzione.prelievi.all():
            quantita_esclusa = (
                prelievo.quantita_prelevata * rapporto_batch
            ).quantize(Decimal("0.000001"))
            prelievo.quantita_trasferita_nc += quantita_esclusa
            prelievo.save(update_fields=["quantita_trasferita_nc"])

        produzione.numero_batch_previsti -= 1
        produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
        produzione.save(update_fields=["numero_batch_previsti", "quantita_teorica_kg"])
        nc.note_apertura = (
            f"Batch in quarantena trasferito alla produzione {nuovo_temp}; "
            "la produzione originale è autorizzata a proseguire."
        )
        nc.save(update_fields=["note_apertura"])
        return nc

    if not puo_proseguire:
        oggi = timezone.localdate()
        ubicazione_produzione = Ubicazione.objects.filter(
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE, attiva=True,
        ).order_by("id").first()
        if ubicazione_produzione is None:
            raise ValueError("Non è configurata un'ubicazione attiva di Magazzino produzione.")

        batch_previsti_originali = produzione.numero_batch_previsti
        batch_precedenti = produzione.batch.filter(numero__lt=batch.numero).count()
        batch_da_trasferire = max(batch_previsti_originali - batch_precedenti, 1)
        base_temp = f"TEMP{oggi:%y%m%d}"
        progressivo = 1
        nuovo_temp = f"{progressivo}{base_temp}"
        while Produzione.objects.filter(lotto_provvisorio=nuovo_temp).exists():
            progressivo += 1
            nuovo_temp = f"{progressivo}{base_temp}"

        nuova_produzione = Produzione.objects.create(
            articolo=produzione.articolo,
            data_produzione=oggi,
            lotto_provvisorio=nuovo_temp,
            numero_batch_previsti=batch_da_trasferire,
            fase=Produzione.Fase.PREPARAZIONE,
            stato_roboqubo=Produzione.StatoRoboqubo.SOSPESA,
            invasettamento_congelato=True,
            derivata_da=produzione,
            bloccata_da_nc=nc,
            note=f"Produzione creata automaticamente dalla NC-{nc.pk}.",
        )
        nuova_produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(nuova_produzione)
        nuova_produzione.save(update_fields=["quantita_teorica_kg"])

        batch_da_spostare = list(
            produzione.batch.filter(numero__gte=batch.numero, tank__isnull=True).order_by("numero")
        )
        for nuovo_numero, batch_da_spostare_singolo in enumerate(batch_da_spostare, start=1):
            batch_da_spostare_singolo.produzione = nuova_produzione
            batch_da_spostare_singolo.numero = nuovo_numero
            batch_da_spostare_singolo.stato = (
                BatchProduzione.Stato.QUARANTENA
                if batch_da_spostare_singolo.pk == batch.pk
                else BatchProduzione.Stato.SOSPESO
            )
            batch_da_spostare_singolo.save(update_fields=["produzione", "numero", "stato"])

        for numero_mancante in range(len(batch_da_spostare) + 1, batch_da_trasferire + 1):
            BatchProduzione.objects.create(
                produzione=nuova_produzione,
                numero=numero_mancante,
                stato=BatchProduzione.Stato.SOSPESO,
            )

        batch_materiali_residui = max(batch_previsti_originali - batch.numero, 0)
        rapporto_materiali = Decimal(batch_materiali_residui) / Decimal(batch_previsti_originali)
        rapporto_escluso_originale = Decimal(batch_da_trasferire) / Decimal(batch_previsti_originali)
        scadenza_massima = oggi + timedelta(days=7)
        ricetta = produzione.articolo.ricette.filter(attiva=True).first()
        ingredienti_ids = set(
            ricetta.righe.filter(ingrediente_prodotto=True).values_list("articolo_id", flat=True)
        )
        for prelievo in produzione.prelievi.select_related(
            "lotto__articolo", "lotto__fornitore",
        ).filter(lotto__articolo_id__in=ingredienti_ids):
            quantita = (prelievo.quantita_prelevata * rapporto_materiali).quantize(Decimal("0.000001"))
            quantita_esclusa = (
                prelievo.quantita_prelevata * rapporto_escluso_originale
            ).quantize(Decimal("0.000001"))
            prelievo.quantita_trasferita_nc += quantita_esclusa
            prelievo.save(update_fields=["quantita_trasferita_nc"])
            if quantita <= 0:
                continue
            origine = prelievo.lotto
            nuova_scadenza = min(
                (data for data in (origine.data_scadenza, scadenza_massima) if data is not None),
                default=scadenza_massima,
            )
            base_codice = f"{origine.codice_lotto}-NC{nc.pk}"[:50]
            codice = base_codice
            indice = 1
            while Lotto.objects.filter(articolo=origine.articolo, codice_lotto=codice).exists():
                indice += 1
                suffisso = f"-{indice}"
                codice = f"{base_codice[:50-len(suffisso)]}{suffisso}"
            lotto_recuperato = Lotto.objects.create(
                articolo=origine.articolo,
                codice_lotto=codice,
                tipo=origine.tipo,
                fornitore=origine.fornitore,
                data_arrivo=origine.data_arrivo,
                data_produzione=origine.data_produzione,
                data_scadenza=nuova_scadenza,
                quantita_iniziale=quantita,
                peso_unita_acquisto=origine.peso_unita_acquisto,
                note=f"Trasferito alla produzione {nuovo_temp} per NC-{nc.pk}.",
            )
            movimento_quarantena = registra_carico(
                lotto=lotto_recuperato,
                quantita=quantita,
                ubicazione=ubicazione_produzione,
                causale=f"Trasferimento materiali a {nuovo_temp} per NC-{nc.pk}",
                operatore=operatore,
            )
            movimento_quarantena.tipo = Movimento.Tipo.QUARANTENA
            movimento_quarantena.save(update_fields=["tipo"])
            riferimento_articolo = f"{origine.articolo.codice} {origine.articolo.descrizione}".lower()
            MaterialeSospesoNonConformita.objects.create(
                non_conformita=nc,
                prelievo=prelievo,
                lotto_recuperato=lotto_recuperato,
                quantita=quantita,
                descrizione_miscela=(
                    "Premiscela zucchero / acido ascorbico"
                    if "zuccher" in riferimento_articolo or "ascorb" in riferimento_articolo else ""
                ),
                esito=MaterialeSospesoNonConformita.Esito.CONSERVA,
                nuova_data_scadenza=nuova_scadenza,
                note=f"Disponibile nel Magazzino produzione per {nuovo_temp}.",
            )

        produzione.numero_batch_previsti = batch_precedenti
        produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
        produzione.fase = Produzione.Fase.INVASETTAMENTO
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.CONCLUSA
        produzione.roboqubo_chiuso_il = timezone.now()
        produzione.invasettamento_congelato = False
        produzione.chiusa_per_nc = True
        produzione.save(update_fields=[
            "numero_batch_previsti", "quantita_teorica_kg", "fase", "stato_roboqubo", "roboqubo_chiuso_il",
            "invasettamento_congelato", "chiusa_per_nc",
        ])
        nc.note_apertura = (
            f"Batch residui trasferiti alla produzione {nuovo_temp}; materiali residui "
            "trasferiti nel Magazzino produzione."
        )
        nc.save(update_fields=["note_apertura"])
    return nc


@transaction.atomic
def risolvi_non_conformita_batch(non_conformita, esito_batch, decisioni_materiali, responsabile):
    nc = NonConformitaLotto.objects.select_for_update().select_related("batch", "produzione").get(
        pk=non_conformita.pk,
    )
    if not nc.batch_id or not nc.produzione_id:
        raise ValueError("La non conformità non riguarda un batch RoboQubo.")
    if esito_batch not in {"SCARTA", "REINTEGRA"}:
        raise ValueError("Indicare se il batch deve essere scartato o reintegrato.")

    batch = nc.batch
    produzione = nc.produzione
    batch.stato = (
        BatchProduzione.Stato.SCARTATO
        if esito_batch == "SCARTA" else BatchProduzione.Stato.CONFORME
    )
    if esito_batch == "SCARTA":
        batch.ora_inizio = None
        batch.ora_fine = None
    else:
        batch.esito_conformita = "C"
    batch.risolto_il = timezone.now()
    batch.save(update_fields=[
        "stato", "esito_conformita", "ora_inizio", "ora_fine", "risolto_il",
    ])

    materiali = list(nc.materiali_sospesi.select_related("prelievo__lotto__articolo"))
    contiene_scarti = False
    if materiali:
        for materiale in materiali:
            dati = decisioni_materiali.get(materiale.pk, {})
            esito = dati.get("esito")
            if esito not in dict(MaterialeSospesoNonConformita.Esito.choices) or esito == MaterialeSospesoNonConformita.Esito.DA_VALUTARE:
                raise ValueError(
                    f"Indicare la decisione per {materiale.prelievo.lotto.articolo.codice}."
                )
            materiale.esito = esito
            materiale.note = (dati.get("note") or "").strip()
            materiale.nuova_data_scadenza = dati.get("nuova_data_scadenza")
            if esito == MaterialeSospesoNonConformita.Esito.SCARTA:
                contiene_scarti = True
            materiale.save(update_fields=["esito", "note", "nuova_data_scadenza"])

        if contiene_scarti:
            ubicazione_produzione = Ubicazione.objects.filter(
                tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
                attiva=True,
            ).order_by("id").first()
            if ubicazione_produzione is None:
                raise ValueError("Non è configurata un'ubicazione attiva di Magazzino produzione.")
            for materiale in materiali:
                if materiale.esito == MaterialeSospesoNonConformita.Esito.SCARTA:
                    continue
                if not materiale.nuova_data_scadenza:
                    raise ValueError(
                        "Indicare la nuova scadenza di tutti i materiali recuperabili."
                    )
                origine = materiale.prelievo.lotto
                base_codice = f"{origine.codice_lotto}-NC{nc.pk}"[:50]
                codice = base_codice
                progressivo = 1
                while Lotto.objects.filter(articolo=origine.articolo, codice_lotto=codice).exists():
                    progressivo += 1
                    suffisso = f"-{progressivo}"
                    codice = f"{base_codice[:50-len(suffisso)]}{suffisso}"
                lotto_recupero = Lotto.objects.create(
                    articolo=origine.articolo,
                    codice_lotto=codice,
                    tipo=origine.tipo,
                    fornitore=origine.fornitore,
                    data_arrivo=origine.data_arrivo,
                    data_produzione=origine.data_produzione,
                    data_scadenza=materiale.nuova_data_scadenza,
                    quantita_iniziale=materiale.quantita,
                    peso_unita_acquisto=origine.peso_unita_acquisto,
                    note=f"Materiale recuperato dalla produzione {produzione.pk}, NC-{nc.pk}.",
                )
                registra_carico(
                    lotto=lotto_recupero,
                    quantita=materiale.quantita,
                    ubicazione=ubicazione_produzione,
                    causale=f"Recupero materiale sospeso NC-{nc.pk}",
                    note=materiale.note,
                    operatore=responsabile,
                )
                materiale.esito = MaterialeSospesoNonConformita.Esito.CONSERVA
                materiale.save(update_fields=["esito"])
            produzione.chiusa_per_nc = True
            produzione.stato_roboqubo = Produzione.StatoRoboqubo.CONCLUSA
            produzione.fase = Produzione.Fase.INVASETTAMENTO
            produzione.roboqubo_chiuso_il = timezone.now()
            produzione.batch.filter(stato=BatchProduzione.Stato.SOSPESO).update(
                stato=BatchProduzione.Stato.SCARTATO,
                risolto_il=timezone.now(),
            )
        else:
            produzione.richiede_lotto_ripresa = True
            produzione.stato_roboqubo = Produzione.StatoRoboqubo.NORMALE
            produzione.batch.filter(stato=BatchProduzione.Stato.SOSPESO).update(
                stato=BatchProduzione.Stato.CONFORME,
            )
    else:
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.NORMALE

    nc.stato = NonConformitaLotto.Stato.CHIUSA
    nc.gestita_da = responsabile
    nc.data_chiusura = timezone.now()
    nc.save(update_fields=["stato", "gestita_da", "data_chiusura"])
    nc_aperte = produzione.non_conformita.exclude(stato=NonConformitaLotto.Stato.CHIUSA)
    if not nc_aperte.exists():
        produzione.invasettamento_congelato = False
        produzione.stato_invasettamento = (
            Produzione.StatoInvasettamento.IN_CORSO
            if produzione.moca_igienizzati or produzione.carrelli.exists()
            else Produzione.StatoInvasettamento.NON_AVVIATO
        )
    elif nc_aperte.filter(produzione_puo_proseguire=False).exists():
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.SOSPESA
    else:
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.CON_NC
    produzione.save(update_fields=[
        "stato_roboqubo", "invasettamento_congelato", "richiede_lotto_ripresa", "chiusa_per_nc",
        "fase", "roboqubo_chiuso_il",
        "stato_invasettamento",
    ])
    return nc


@transaction.atomic
def risolvi_nc_produzione_derivata(
    non_conformita, esito_batch, decisioni_materiali, responsabile,
):
    nc = NonConformitaLotto.objects.select_for_update().select_related("batch").get(
        pk=non_conformita.pk,
    )
    produzione = Produzione.objects.select_for_update().filter(bloccata_da_nc=nc).first()
    if produzione is None:
        raise ValueError("Non esiste una produzione derivata bloccata da questa NC.")
    if esito_batch not in {"SCARTA", "REINTEGRA"}:
        raise ValueError("Indicare la decisione sul batch in quarantena.")

    materiali = list(
        nc.materiali_sospesi.select_related("lotto_recuperato__articolo").all()
    )
    almeno_uno_scartato = False
    for materiale in materiali:
        dati = decisioni_materiali.get(materiale.pk, {})
        esito = dati.get("esito")
        if esito not in {
            MaterialeSospesoNonConformita.Esito.RIUTILIZZA,
            MaterialeSospesoNonConformita.Esito.SCARTA,
        }:
            raise ValueError(
                f"Indicare Scarto o Reintegro per {materiale.prelievo.lotto.articolo.codice}."
            )
        materiale.esito = esito
        materiale.note = (dati.get("note") or "").strip()
        materiale.save(update_fields=["esito", "note"])
        almeno_uno_scartato = almeno_uno_scartato or esito == MaterialeSospesoNonConformita.Esito.SCARTA

    batch = nc.batch
    batch.stato = (
        BatchProduzione.Stato.SCARTATO
        if esito_batch == "SCARTA" else BatchProduzione.Stato.CONFORME
    )
    if esito_batch == "SCARTA":
        batch.ora_inizio = None
        batch.ora_fine = None
    else:
        batch.esito_conformita = "C"
    batch.risolto_il = timezone.now()
    batch.save(update_fields=[
        "stato", "esito_conformita", "ora_inizio", "ora_fine", "risolto_il",
    ])

    deve_abortire = almeno_uno_scartato or (
        esito_batch == "SCARTA" and not produzione.batch.exclude(pk=batch.pk).exists()
    )
    if deve_abortire:
        for materiale in materiali:
            if materiale.esito != MaterialeSospesoNonConformita.Esito.SCARTA:
                materiale.esito = MaterialeSospesoNonConformita.Esito.CONSERVA
                materiale.save(update_fields=["esito"])
                continue
            if materiale.lotto_recuperato_id is None:
                raise ValueError("Manca il lotto recuperato del materiale da scartare.")
            for giacenza in Giacenza.objects.select_for_update().filter(
                lotto=materiale.lotto_recuperato, quantita__gt=0,
            ):
                quantita_scartata = giacenza.quantita
                giacenza.quantita = Decimal("0")
                giacenza.save(update_fields=["quantita"])
                Movimento.objects.create(
                    tipo=Movimento.Tipo.SCARTO_NC,
                    lotto=materiale.lotto_recuperato,
                    quantita=quantita_scartata,
                    ubicazione_origine=giacenza.ubicazione,
                    scaffale_origine=giacenza.scaffale,
                    piano_origine=giacenza.piano,
                    causale=f"Scarto materiale e aborto {produzione.lotto_provvisorio} per NC-{nc.pk}",
                    note=materiale.note,
                    eseguito_da=responsabile,
                )
        produzione.stato = Produzione.Stato.ABORTITA
        produzione.fase = Produzione.Fase.COMPLETATA
        produzione.chiusa_per_nc = True
        produzione.invasettamento_congelato = False
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.CONCLUSA
        produzione.stato_invasettamento = Produzione.StatoInvasettamento.CONCLUSO
        produzione.save(update_fields=[
            "stato", "fase", "chiusa_per_nc", "invasettamento_congelato", "stato_roboqubo",
            "stato_invasettamento",
        ])
    else:
        for materiale in materiali:
            lotto = materiale.lotto_recuperato
            if lotto is None:
                raise ValueError("Manca il lotto recuperato di un materiale da reintegrare.")
            giacenze = list(
                Giacenza.objects.select_for_update().filter(lotto=lotto, quantita__gt=0)
            )
            quantita_disponibile = sum((g.quantita for g in giacenze), Decimal("0"))
            if quantita_disponibile < materiale.quantita:
                raise ValueError(f"Giacenza insufficiente per reintegrare {lotto.articolo.codice}.")
            residuo = materiale.quantita
            for giacenza in giacenze:
                prelevata = min(giacenza.quantita, residuo)
                if prelevata <= 0:
                    continue
                giacenza.quantita -= prelevata
                giacenza.save(update_fields=["quantita"])
                Movimento.objects.create(
                    tipo=Movimento.Tipo.REINTEGRO,
                    lotto=lotto,
                    quantita=prelevata,
                    ubicazione_origine=giacenza.ubicazione,
                    scaffale_origine=giacenza.scaffale,
                    piano_origine=giacenza.piano,
                    causale=f"Reintegro nella produzione {produzione.lotto_provvisorio} dopo NC-{nc.pk}",
                    note=materiale.note,
                    eseguito_da=responsabile,
                )
                PrelievoProduzione.objects.create(
                    produzione=produzione,
                    lotto=lotto,
                    ubicazione_origine=giacenza.ubicazione,
                    scaffale_origine=giacenza.scaffale,
                    piano_origine=giacenza.piano,
                    quantita_prelevata=prelevata,
                    quantita_movimentata=prelevata,
                    quantita_scarto=Decimal("0"),
                    note=f"Materiale reintegrato dalla NC-{nc.pk}. {materiale.note}".strip(),
                )
                residuo -= prelevata
                if residuo <= 0:
                    break

        if esito_batch == "SCARTA":
            produzione.numero_batch_previsti = max(
                produzione.numero_batch_previsti - 1, 0,
            )
            produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
        if esito_batch == "REINTEGRA":
            ricetta = produzione.articolo.ricette.filter(attiva=True).first()
            if ricetta is not None:
                produzione.quantita_batch_reintegrato_kg = sum(
                    ricetta.righe.filter(ingrediente_prodotto=True).values_list("quantita", flat=True),
                    Decimal("0"),
                )
        produzione.batch.filter(stato=BatchProduzione.Stato.SOSPESO).update(
            stato=BatchProduzione.Stato.DA_LAVORARE,
        )
        produzione.preparazione_chiusa_il = timezone.now()
        produzione.fase = Produzione.Fase.ROBOQUBO
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.NORMALE
        produzione.invasettamento_congelato = False
        produzione.save(update_fields=[
            "preparazione_chiusa_il", "fase", "stato_roboqubo",
            "invasettamento_congelato", "quantita_batch_reintegrato_kg",
            "numero_batch_previsti", "quantita_teorica_kg",
        ])

    nc.stato = NonConformitaLotto.Stato.CHIUSA
    nc.gestita_da = responsabile
    nc.data_chiusura = timezone.now()
    nc.save(update_fields=["stato", "gestita_da", "data_chiusura"])
    produzione_origine = Produzione.objects.get(pk=nc.produzione_id)
    produzione_origine.invasettamento_congelato = False
    produzione_origine.stato_invasettamento = (
        Produzione.StatoInvasettamento.IN_CORSO
        if produzione_origine.moca_igienizzati or produzione_origine.carrelli.exists()
        else Produzione.StatoInvasettamento.NON_AVVIATO
    )
    produzione_origine.save(update_fields=[
        "invasettamento_congelato", "stato_invasettamento",
    ])
    return produzione


@transaction.atomic
def registra_carico(
    lotto,
    quantita,
    ubicazione,
    scaffale="",
    piano="",
    causale="Carico",
    note="",
    operatore=None,
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
    giacenza, _ = Giacenza.objects.select_for_update().get_or_create(
        lotto=lotto,
        ubicazione=ubicazione,
        scaffale=(scaffale or "").strip(),
        piano=(piano or "").strip(),
        defaults={"quantita": Decimal("0")},
    )
    giacenza.quantita += quantita
    giacenza.save(update_fields=["quantita"])
    movimento = Movimento.objects.create(
        tipo=Movimento.Tipo.CARICO,
        lotto=lotto,
        quantita=quantita,
        ubicazione_destinazione=ubicazione,
        scaffale_destinazione=(scaffale or "").strip(),
        piano_destinazione=(piano or "").strip(),
        causale=causale,
        note=note,
        eseguito_da=operatore,
    )
    return movimento


@transaction.atomic
def registra_carico_lotto(
    articolo,
    codice_lotto,
    fornitore,
    quantita,
    ubicazione,
    numero_colli=None,
    unita_acquisto_per_collo=None,
    peso_unita_acquisto=None,
    fattura="",
    ddt="",
    scaffale="",
    piano="",
    data_arrivo=None,
    data_scadenza=None,
    causale="Carico",
    note="",
    operatore=None,
):
    quantita = Decimal(str(quantita))
    codice_lotto = (codice_lotto or "").strip()
    fattura = (fattura or "").strip()
    ddt = (ddt or "").strip()
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if not fattura and not ddt:
        raise ValueError("Inserire almeno una Fattura oppure un DDT.")
    if numero_colli is not None:
        numero_colli = int(numero_colli)
        if numero_colli <= 0:
            raise ValueError("Il numero di colli deve essere maggiore di zero.")
    if unita_acquisto_per_collo is not None:
        unita_acquisto_per_collo = int(unita_acquisto_per_collo)
        if unita_acquisto_per_collo <= 0:
            raise ValueError(
                "Le unità di acquisto per collo devono essere maggiori di zero."
            )
    if peso_unita_acquisto is not None:
        peso_unita_acquisto = Decimal(str(peso_unita_acquisto))
        if peso_unita_acquisto <= 0:
            raise ValueError(
                "Il peso della singola unità di acquisto deve essere maggiore di zero."
            )

    valori_presenti = sum(
        valore is not None
        for valore in (
            numero_colli,
            unita_acquisto_per_collo,
            peso_unita_acquisto,
        )
    )
    if valori_presenti < 2:
        raise ValueError(
            "Indicare almeno due valori tra numero di colli, numero di unità "
            "di acquisto per collo e peso della singola UDA."
        )
    if valori_presenti == 2:
        if numero_colli is None:
            valore = quantita / (
                Decimal(unita_acquisto_per_collo) * peso_unita_acquisto
            )
            intero = valore.to_integral_value()
            if valore != intero:
                raise ValueError(
                    "Il numero di colli calcolato non è un numero intero."
                )
            numero_colli = int(intero)
        elif unita_acquisto_per_collo is None:
            valore = quantita / (Decimal(numero_colli) * peso_unita_acquisto)
            intero = valore.to_integral_value()
            if valore != intero:
                raise ValueError(
                    "Il numero di unità di acquisto per collo calcolato non è "
                    "un numero intero."
                )
            unita_acquisto_per_collo = int(intero)
        else:
            peso_unita_acquisto = (
                quantita
                / (Decimal(numero_colli) * Decimal(unita_acquisto_per_collo))
            ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    else:
        quantita_calcolata = (
            Decimal(numero_colli)
            * Decimal(unita_acquisto_per_collo)
            * peso_unita_acquisto
        )
        if abs(quantita_calcolata - quantita) > Decimal("0.000001"):
            raise ValueError(
                "I dati di colli e unità di acquisto non sono coerenti con "
                "la quantità totale."
            )
    if not articolo.attivo:
        raise ValueError("L'articolo non è attivo.")
    if articolo.tracciabilita_lotto and not codice_lotto:
        raise ValueError("Il codice lotto è obbligatorio per questo articolo.")
    if not articolo.tracciabilita_lotto and not codice_lotto:
        data_riferimento = data_arrivo or date.today()
        base = f"NT-{data_riferimento:%y%m%d}"
        progressivo = 1
        codice_lotto = f"{base}-{progressivo:03d}"
        while Lotto.objects.filter(
            articolo=articolo, codice_lotto=codice_lotto,
        ).exists():
            progressivo += 1
            codice_lotto = f"{base}-{progressivo:03d}"
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
        fattura=fattura,
        ddt=ddt,
        numero_colli=numero_colli,
        unita_acquisto_per_collo=unita_acquisto_per_collo,
        peso_unita_acquisto=peso_unita_acquisto,
        note=note,
    )
    movimento = registra_carico(
        lotto=lotto,
        quantita=quantita,
        ubicazione=ubicazione,
        scaffale=scaffale,
        piano=piano,
        causale=causale,
        note=note,
        operatore=operatore,
    )
    return lotto, movimento


@transaction.atomic
def registra_trasferimento(
    lotto,
    quantita,
    ubicazione_origine,
    ubicazione_destinazione,
    scaffale_origine="",
    piano_origine="",
    scaffale_destinazione="",
    piano_destinazione="",
    note="",
    operatore=None,
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    posizione_origine = (
        ubicazione_origine.pk,
        (scaffale_origine or "").strip(),
        (piano_origine or "").strip(),
    )
    posizione_destinazione = (
        ubicazione_destinazione.pk,
        (scaffale_destinazione or "").strip(),
        (piano_destinazione or "").strip(),
    )
    if posizione_origine == posizione_destinazione:
        raise ValueError(
            "L'ubicazione di origine e destinazione devono essere diverse."
        )
    if not ubicazione_origine.attiva:
        raise ValueError("L'ubicazione di origine non è attiva.")
    if not ubicazione_destinazione.attiva:
        raise ValueError("L'ubicazione di destinazione non è attiva.")
    giacenza_origine = (
        Giacenza.objects
        .select_for_update()
        .filter(
            lotto=lotto,
            ubicazione=ubicazione_origine,
            scaffale=posizione_origine[1],
            piano=posizione_origine[2],
        )
        .first()
    )
    if giacenza_origine is None or giacenza_origine.quantita < quantita:
        raise ValueError(
            "Quantità insufficiente nell'ubicazione di origine."
        )
    giacenza_destinazione, _ = (
        Giacenza.objects
        .select_for_update()
        .get_or_create(
            lotto=lotto,
            ubicazione=ubicazione_destinazione,
            scaffale=posizione_destinazione[1],
            piano=posizione_destinazione[2],
            defaults={"quantita": Decimal("0")},
        )
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
        scaffale_origine=posizione_origine[1],
        piano_origine=posizione_origine[2],
        scaffale_destinazione=posizione_destinazione[1],
        piano_destinazione=posizione_destinazione[2],
        causale="Trasferimento",
        note=note,
        eseguito_da=operatore,
    )
    return movimento


@transaction.atomic
def registra_consumo(
    lotto,
    quantita,
    ubicazione_origine,
    scaffale_origine="",
    piano_origine="",
    causale="Scarico materiale di consumo",
    note="",
    operatore=None,
):
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValueError("La quantità deve essere maggiore di zero.")
    if not ubicazione_origine.attiva:
        raise ValueError("L'ubicazione di origine non è attiva.")
    giacenza = (
        Giacenza.objects
        .select_for_update()
        .filter(
            lotto=lotto,
            ubicazione=ubicazione_origine,
            scaffale=(scaffale_origine or "").strip(),
            piano=(piano_origine or "").strip(),
        )
        .first()
    )
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
        scaffale_origine=(scaffale_origine or "").strip(),
        piano_origine=(piano_origine or "").strip(),
        ubicazione_destinazione=None,
        causale=causale,
        note=note,
        eseguito_da=operatore,
    )
    return movimento


@transaction.atomic
def apri_non_conformita_lotto(
    lotto,
    giacenza,
    numero_uda,
    motivo,
    note="",
    operatore=None,
    ambito=NonConformitaLotto.Ambito.PRODUZIONE,
    tipo_nc=NonConformitaLotto.Tipo.INTERNO,
):
    numero_uda = int(numero_uda)
    if numero_uda <= 0:
        raise ValueError("Il numero di UDA deve essere maggiore di zero.")
    if operatore is None:
        raise ValueError("L'operatore che apre la non conformità è obbligatorio.")
    if not (motivo or "").strip():
        raise ValueError("Il motivo della non conformità è obbligatorio.")
    if lotto.quantita_singola_uda is None or lotto.quantita_singola_uda <= 0:
        raise ValueError(
            "Il lotto non ha la quantità della singola UDA registrata."
        )

    giacenza = (
        Giacenza.objects.select_for_update()
        .select_related("ubicazione")
        .filter(pk=giacenza.pk, lotto=lotto)
        .first()
    )
    if giacenza is None:
        raise ValueError("La posizione selezionata non appartiene al lotto.")

    quantita_per_uda = Decimal(lotto.quantita_singola_uda)
    quantita_quarantena = Decimal(numero_uda) * quantita_per_uda
    if giacenza.quantita < quantita_quarantena:
        raise ValueError(
            "Le UDA richieste superano la giacenza disponibile nella posizione."
        )

    giacenza.quantita -= quantita_quarantena
    giacenza.save(update_fields=["quantita"])
    non_conformita = NonConformitaLotto.objects.create(
        lotto=lotto,
        ubicazione_origine=giacenza.ubicazione,
        scaffale_origine=giacenza.scaffale,
        piano_origine=giacenza.piano,
        numero_uda_quarantena=numero_uda,
        quantita_quarantena=quantita_quarantena,
        quantita_per_uda=quantita_per_uda,
        motivo=motivo.strip(),
        note_apertura=(note or "").strip(),
        aperta_da=operatore,
        ambito=ambito,
        tipo_nc=tipo_nc,
    )
    Movimento.objects.create(
        tipo=Movimento.Tipo.QUARANTENA,
        lotto=lotto,
        quantita=quantita_quarantena,
        ubicazione_origine=giacenza.ubicazione,
        scaffale_origine=giacenza.scaffale,
        piano_origine=giacenza.piano,
        causale=f"Apertura non conformità NC-{non_conformita.pk}",
        note=motivo.strip(),
        eseguito_da=operatore,
    )
    return non_conformita


@transaction.atomic
def gestisci_non_conformita_lotto(
    non_conformita,
    numero_uda_scartate,
    numero_uda_reintegrate,
    decisione,
    responsabile=None,
):
    non_conformita = (
        NonConformitaLotto.objects.select_for_update()
        .select_related("lotto", "ubicazione_origine")
        .get(pk=non_conformita.pk)
    )
    if non_conformita.stato == NonConformitaLotto.Stato.CHIUSA:
        raise ValueError("La non conformità è già stata chiusa.")
    if responsabile is None:
        raise ValueError("Il responsabile qualità è obbligatorio.")
    if not (decisione or "").strip():
        raise ValueError("La motivazione della decisione è obbligatoria.")

    scartate = int(numero_uda_scartate)
    reintegrate = int(numero_uda_reintegrate)
    if scartate < 0 or reintegrate < 0:
        raise ValueError("Le quantità di UDA non possono essere negative.")
    if scartate + reintegrate != non_conformita.numero_uda_quarantena:
        raise ValueError(
            "La somma delle UDA scartate e reintegrate deve coincidere con "
            "le UDA in quarantena."
        )

    lotto = non_conformita.lotto
    quantita_reintegrata = Decimal(reintegrate) * non_conformita.quantita_per_uda
    quantita_scartata = Decimal(scartate) * non_conformita.quantita_per_uda

    if reintegrate:
        giacenza = (
            Giacenza.objects.select_for_update()
            .filter(
                lotto=lotto,
                ubicazione=non_conformita.ubicazione_origine,
                scaffale=non_conformita.scaffale_origine,
                piano=non_conformita.piano_origine,
            )
            .first()
        )
        if giacenza is None:
            giacenza = Giacenza.objects.create(
                lotto=lotto,
                ubicazione=non_conformita.ubicazione_origine,
                scaffale=non_conformita.scaffale_origine,
                piano=non_conformita.piano_origine,
                quantita=Decimal("0"),
            )
        giacenza.quantita += quantita_reintegrata
        giacenza.save(update_fields=["quantita"])
        Movimento.objects.create(
            tipo=Movimento.Tipo.REINTEGRO,
            lotto=lotto,
            quantita=quantita_reintegrata,
            ubicazione_destinazione=non_conformita.ubicazione_origine,
            scaffale_destinazione=non_conformita.scaffale_origine,
            piano_destinazione=non_conformita.piano_origine,
            causale=f"Reintegro non conformità NC-{non_conformita.pk}",
            note=decisione.strip(),
            eseguito_da=responsabile,
        )

    if scartate:
        Movimento.objects.create(
            tipo=Movimento.Tipo.SCARTO_NC,
            lotto=lotto,
            quantita=quantita_scartata,
            causale=f"Scarto non conformità NC-{non_conformita.pk}",
            note=decisione.strip(),
            eseguito_da=responsabile,
        )

    non_conformita.stato = NonConformitaLotto.Stato.CHIUSA
    non_conformita.numero_uda_scartate = scartate
    non_conformita.numero_uda_reintegrate = reintegrate
    non_conformita.decisione = decisione.strip()
    non_conformita.gestita_da = responsabile
    non_conformita.data_chiusura = timezone.now()
    non_conformita.save(
        update_fields=[
            "stato",
            "numero_uda_scartate",
            "numero_uda_reintegrate",
            "decisione",
            "gestita_da",
            "data_chiusura",
        ]
    )
    return non_conformita


def genera_codice_lotto_produzione(articolo, data_produzione):
    base = data_produzione.strftime("%y%m%d")
    codice = base
    progressivo = 0

    while Lotto.objects.filter(
        articolo=articolo,
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


def genera_codice_lotto_ripresa(articolo, data_produzione):
    base = data_produzione.strftime("%y%m%d")
    progressivo = 1
    codice = f"{progressivo}{base}"
    while Lotto.objects.filter(articolo=articolo, codice_lotto=codice).exists():
        progressivo += 1
        codice = f"{progressivo}{base}"
    return codice


def genera_codice_lotto_per_produzione(produzione, data_conferma):
    """Propone il lotto definitivo rispettando l'eventuale prefisso della bozza NC."""
    lotto_temporaneo = (produzione.lotto_provvisorio or "").strip().upper()
    parti = lotto_temporaneo.partition("TEMP")
    if parti[1] and parti[0].isdigit() and len(parti[2]) == 6 and parti[2].isdigit():
        progressivo = int(parti[0])
        base = parti[2]
        codice = f"{progressivo}{base}"
        while Lotto.objects.filter(
            articolo=produzione.articolo,
            codice_lotto=codice,
        ).exists():
            progressivo += 1
            codice = f"{progressivo}{base}"
        return codice

    if produzione.richiede_lotto_ripresa and produzione.lotti_uscita.exists():
        return genera_codice_lotto_ripresa(produzione.articolo, data_conferma)
    return genera_codice_lotto_produzione(produzione.articolo, data_conferma)


@transaction.atomic
def avvia_produzione(
    articolo,
    data_produzione=None,
    note="",
):
    if not articolo.attivo:
        raise ValueError("L'articolo non è attivo.")

    if articolo.categoria != articolo.Categoria.PRODOTTO_FINITO:
        raise ValueError(
            "La produzione deve riferirsi a un prodotto finito."
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

    produzione = Produzione.objects.create(
        articolo=articolo,
        data_produzione=data_produzione,
        stato=Produzione.Stato.BOZZA,
        note=note,
    )
    produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
    produzione.save(update_fields=["quantita_teorica_kg"])
    return produzione


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
def apri_tank_produzione(produzione, numero_batch):
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione non è in bozza.")
    if produzione.tank.filter(annullato=False, gradi_brix__isnull=True).exists():
        raise ValueError("Registra Brix e pH del tank aperto prima di continuarne un altro.")
    numero_batch = int(numero_batch)
    if numero_batch < 1:
        raise ValueError("Il numero di batch deve essere almeno 1.")
    ultimo = produzione.tank.order_by("-numero").first()
    return TankProduzione.objects.create(
        produzione=produzione,
        numero=(ultimo.numero + 1) if ultimo else 1,
        numero_batch=numero_batch,
    )


@transaction.atomic
def registra_controlli_tank(tank, gradi_brix, ph):
    tank = TankProduzione.objects.select_for_update().get(pk=tank.pk)
    if tank.annullato:
        raise ValueError("Il tank è stato annullato.")
    if tank.controllato:
        raise ValueError("I controlli di questo tank sono già registrati.")
    gradi_brix = Decimal(str(gradi_brix))
    ph = Decimal(str(ph))
    if gradi_brix < 0 or ph < 0 or ph > 14:
        raise ValueError("Valori Brix o pH non validi.")
    tank.gradi_brix = gradi_brix
    tank.ph = ph
    tank.data_ora_controlli = timezone.now()
    tank.chiuso_il = tank.data_ora_controlli
    tank.save(update_fields=["gradi_brix", "ph", "data_ora_controlli", "chiuso_il"])
    return tank


@transaction.atomic
def modifica_tank_produzione(tank, numero_batch, gradi_brix=None, ph=None):
    tank = TankProduzione.objects.select_related("produzione").select_for_update().get(pk=tank.pk)
    if tank.annullato:
        raise ValueError("Un tank annullato non può essere modificato.")
    if tank.produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("È possibile modificare il tank solo con produzione in bozza.")
    numero_batch = int(numero_batch)
    if numero_batch < 1:
        raise ValueError("Il numero di batch deve essere almeno 1.")
    if (gradi_brix is None) != (ph is None):
        raise ValueError("Gradi Brix e pH devono essere compilati insieme.")
    if gradi_brix is not None and not tank.prelievi.exists():
        raise ValueError("Registra i prelievi del tank prima dei controlli.")
    if gradi_brix is not None and tank.prelievi.filter(quantita_scarto__isnull=True).exists():
        raise ValueError("Registra tutti gli scarti del tank prima dei controlli.")
    tank.numero_batch = numero_batch
    tank.gradi_brix = Decimal(str(gradi_brix)) if gradi_brix is not None else None
    tank.ph = Decimal(str(ph)) if ph is not None else None
    if tank.gradi_brix is not None and (tank.gradi_brix < 0 or tank.ph < 0 or tank.ph > 14):
        raise ValueError("Valori Brix o pH non validi.")
    tank.data_ora_controlli = timezone.now() if tank.gradi_brix is not None else None
    tank.save(update_fields=["numero_batch", "gradi_brix", "ph", "data_ora_controlli"])
    return tank


@transaction.atomic
def annulla_tank_produzione(tank, motivo, operatore=None):
    tank = TankProduzione.objects.select_related("produzione").select_for_update().get(pk=tank.pk)
    if tank.annullato:
        raise ValueError("Il tank è già stato annullato.")
    if tank.produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("È possibile annullare il tank solo con produzione in bozza.")
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise ValueError("Inserisci il motivo dell'annullamento.")
    tank.annullato = True
    tank.motivo_annullamento = motivo
    tank.data_ora_annullamento = timezone.now()
    tank.annullato_da = operatore
    tank.save(update_fields=["annullato", "motivo_annullamento", "data_ora_annullamento", "annullato_da"])
    return tank


@transaction.atomic
def registra_pastorizzazione(produzione):
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione non è in bozza.")
    if produzione.pastorizzazione_completata:
        raise ValueError("La pastorizzazione è già stata registrata.")
    produzione.pastorizzazione_completata = True
    produzione.data_ora_pastorizzazione = timezone.now()
    produzione.save(update_fields=["pastorizzazione_completata", "data_ora_pastorizzazione"])
    return produzione


@transaction.atomic
def registra_verifica_vuoto(produzione):
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione non è in bozza.")
    if produzione.vuoto_controllato:
        raise ValueError("La verifica sottovuoto è già stata registrata.")
    produzione.vuoto_controllato = True
    produzione.data_ora_verifica_vuoto = timezone.now()
    produzione.save(update_fields=["vuoto_controllato", "data_ora_verifica_vuoto"])
    return produzione


@transaction.atomic
def registra_prelievi_produzione(
    produzione,
    articolo,
    quantita_richiesta,
    note="",
    operatore=None,
    tank=None,
):
    if not isinstance(produzione, Produzione):
        raise ValueError("La produzione non è valida.")

    produzione = (
        Produzione.objects
        .select_for_update()
        .get(pk=produzione.pk)
    )

    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError(
            "È possibile registrare prelievi solo "
            "su una produzione in bozza."
        )

    if tank is not None and tank.produzione_id != produzione.pk:
        raise ValueError("Il tank non appartiene alla produzione.")

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
        rispetta_uda=True,
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
            .get(pk=riga["giacenza_id"])
        )

        quantita_prelevata = riga["quantita_proposta"]
        quantita_movimentata = riga.get("quantita_movimentata", quantita_prelevata)
        quantita_resa = quantita_movimentata - quantita_prelevata

        if giacenza.quantita < quantita_movimentata:
            raise ValueError(
                f"La giacenza del lotto "
                f"{giacenza.lotto.codice_lotto} è cambiata. "
                "Ripetere la proposta di prelievo."
            )

        giacenza.quantita -= quantita_movimentata
        giacenza.save(update_fields=["quantita"])

        Movimento.objects.create(
            tipo=Movimento.Tipo.CONSUMO,
            lotto=giacenza.lotto,
            quantita=quantita_prelevata,
            ubicazione_origine=giacenza.ubicazione,
            scaffale_origine=giacenza.scaffale,
            piano_origine=giacenza.piano,
            ubicazione_destinazione=None,
            causale="Prelievo produzione marmellata",
            note=note,
            eseguito_da=operatore,
        )

        if quantita_resa > 0:
            ubicazione_produzione = Ubicazione.objects.filter(
                tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
                attiva=True,
            ).order_by("id").first()
            if ubicazione_produzione is None:
                raise ValueError(
                    "Non esiste un'ubicazione attiva di tipo Magazzino produzione "
                    "per depositare l'avanzo dell'unità di acquisto."
                )
            giacenza_produzione, _ = Giacenza.objects.select_for_update().get_or_create(
                lotto=giacenza.lotto, ubicazione=ubicazione_produzione,
                scaffale="", piano="", defaults={"quantita": Decimal("0")},
            )
            giacenza_produzione.quantita += quantita_resa
            giacenza_produzione.save(update_fields=["quantita"])
            Movimento.objects.create(
                tipo=Movimento.Tipo.TRASFERIMENTO,
                lotto=giacenza.lotto, quantita=quantita_resa,
                ubicazione_origine=giacenza.ubicazione,
                ubicazione_destinazione=ubicazione_produzione,
                scaffale_origine=giacenza.scaffale, piano_origine=giacenza.piano,
                causale="Avanzo UDA trasferito al Magazzino produzione",
                note=(f"Prelevati fisicamente {quantita_movimentata}; "
                      f"utilizzati {quantita_prelevata}; avanzo {quantita_resa}."),
                eseguito_da=operatore,
            )

        prelievo = PrelievoProduzione.objects.create(
            produzione=produzione,
            tank=tank,
            lotto=giacenza.lotto,
            ubicazione_origine=giacenza.ubicazione,
            scaffale_origine=giacenza.scaffale,
            piano_origine=giacenza.piano,
            quantita_prelevata=quantita_prelevata,
            quantita_movimentata=quantita_movimentata,
            quantita_resa_produzione=quantita_resa,
            quantita_scarto=None,
            note=note,
        )

        prelievi.append(prelievo)

    return prelievi


@transaction.atomic
def registra_ingredienti_tank(
    produzione,
    tank,
    quantita_per_articolo,
    note_per_articolo=None,
    note="",
    operatore=None,
):
    note_per_articolo = note_per_articolo or {}
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    tank = TankProduzione.objects.select_for_update().get(pk=tank.pk)
    if tank.produzione_id != produzione.pk:
        raise ValueError("Il tank non appartiene alla produzione.")
    if tank.annullato:
        raise ValueError("Il tank è stato annullato.")
    if tank.controllato:
        raise ValueError("I controlli del tank sono già stati registrati.")
    if tank.prelievi.exists():
        raise ValueError("Gli ingredienti di questo tank sono già stati prelevati.")

    ricetta = (
        produzione.articolo.ricette
        .filter(attiva=True)
        .prefetch_related("righe__articolo")
        .first()
    )
    if ricetta is None:
        raise ValueError("Il prodotto non ha una ricetta attiva.")

    righe = list(
        ricetta.righe.select_related("articolo").filter(
            ingrediente_prodotto=True
        )
    )
    mancanti = [
        riga.articolo.codice
        for riga in righe
        if riga.articolo_id not in quantita_per_articolo
    ]
    if mancanti:
        raise ValueError(
            "Inserisci la quantità per tutti gli ingredienti: "
            + ", ".join(mancanti)
            + "."
        )

    prelievi = []
    for riga in righe:
        quantita = Decimal(str(quantita_per_articolo[riga.articolo_id]))
        if quantita <= 0:
            raise ValueError(
                f"La quantità di {riga.articolo.codice} deve essere positiva."
            )
        prelievi.extend(
            registra_prelievi_produzione(
                produzione=produzione,
                articolo=riga.articolo,
                quantita_richiesta=quantita,
                note=note_per_articolo.get(riga.articolo_id, note),
                operatore=operatore,
                tank=tank,
            )
        )
    return prelievi


@transaction.atomic
def chiudi_preparazione_produzione(produzione, quantita_per_articolo, note_per_articolo=None, operatore=None):
    note_per_articolo = note_per_articolo or {}
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.fase != Produzione.Fase.PREPARAZIONE:
        raise ValueError("La preparazione è già stata chiusa.")
    ricetta = produzione.articolo.ricette.filter(attiva=True).prefetch_related("righe__articolo").first()
    if ricetta is None:
        raise ValueError("Il prodotto non ha una ricetta attiva.")
    righe = list(ricetta.righe.select_related("articolo").filter(ingrediente_prodotto=True))
    if any(r.articolo_id not in quantita_per_articolo for r in righe):
        raise ValueError("Inserisci la quantità di tutti gli ingredienti.")
    creati = []
    for riga in righe:
        creati_riga = registra_prelievi_produzione(
            produzione, riga.articolo, quantita_per_articolo[riga.articolo_id],
            note_per_articolo.get(riga.articolo_id, ""), operatore,
        )
        for prelievo in creati_riga:
            prelievo.quantita_scarto = Decimal("0")
            prelievo.save(update_fields=["quantita_scarto"])
        creati.extend(creati_riga)
    produzione.fase = Produzione.Fase.ROBOQUBO
    produzione.preparazione_chiusa_il = timezone.now()
    produzione.quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
    produzione.save(update_fields=["fase", "preparazione_chiusa_il", "quantita_teorica_kg"])
    return creati


@transaction.atomic
def registra_scarti_tank(produzione, tank, scarti_per_prelievo, note_per_prelievo=None):
    note_per_prelievo = note_per_prelievo or {}
    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    tank = TankProduzione.objects.select_for_update().get(pk=tank.pk)
    if tank.produzione_id != produzione.pk:
        raise ValueError("Il tank non appartiene alla produzione.")
    if tank.annullato:
        raise ValueError("Il tank è stato annullato.")
    if tank.controllato:
        raise ValueError("I controlli del tank sono già stati registrati.")

    prelievi = list(
        tank.prelievi.select_for_update().filter(quantita_scarto__isnull=True)
    )
    if not prelievi:
        raise ValueError("Non ci sono scarti da registrare per questo tank.")

    mancanti = [str(prelievo.pk) for prelievo in prelievi if prelievo.pk not in scarti_per_prelievo]
    if mancanti:
        raise ValueError("Inserisci lo scarto per tutti i prelievi del tank.")

    registrati = []
    for prelievo in prelievi:
        registrati.append(
            registra_scarto_prelievo_produzione(
                prelievo=prelievo,
                quantita_scarto=scarti_per_prelievo[prelievo.pk],
                note=note_per_prelievo.get(prelievo.pk, ""),
            )
        )
    return registrati


@transaction.atomic
def elimina_produzione_bozza(produzione, operatore=None):
    if not isinstance(produzione, Produzione):
        raise ValueError("La produzione non è valida.")

    produzione = Produzione.objects.select_for_update().get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("È possibile eliminare solo una produzione in bozza.")

    prelievi = list(
        produzione.prelievi.select_related(
            "lotto", "ubicazione_origine"
        ).select_for_update()
    )
    for prelievo in prelievi:
        quantita_movimentata = (
            prelievo.quantita_movimentata or prelievo.quantita_prelevata
        )
        quantita_resa = prelievo.quantita_resa_produzione or Decimal("0")
        if quantita_resa > 0:
            ubicazione_produzione = Ubicazione.objects.filter(
                tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
                attiva=True,
            ).order_by("id").first()
            if ubicazione_produzione is None:
                raise ValueError("Magazzino produzione non disponibile per annullare il prelievo.")
            giacenza_produzione = Giacenza.objects.select_for_update().filter(
                lotto=prelievo.lotto, ubicazione=ubicazione_produzione,
                scaffale="", piano="",
            ).first()
            if giacenza_produzione is None or giacenza_produzione.quantita < quantita_resa:
                raise ValueError(
                    f"L'avanzo UDA del lotto {prelievo.lotto.codice_lotto} "
                    "non è più disponibile nel Magazzino produzione."
                )
            giacenza_produzione.quantita -= quantita_resa
            giacenza_produzione.save(update_fields=["quantita"])
        giacenza, _ = Giacenza.objects.select_for_update().get_or_create(
            lotto=prelievo.lotto,
            ubicazione=prelievo.ubicazione_origine,
            scaffale=prelievo.scaffale_origine,
            piano=prelievo.piano_origine,
            defaults={"quantita": Decimal("0")},
        )
        giacenza.quantita += quantita_movimentata
        giacenza.save(update_fields=["quantita"])
        Movimento.objects.create(
            tipo=Movimento.Tipo.RETTIFICA,
            lotto=prelievo.lotto,
            quantita=quantita_movimentata,
            ubicazione_destinazione=prelievo.ubicazione_origine,
            causale="Annullamento produzione in bozza",
            note=f"Produzione annullata n. {produzione.pk}",
            eseguito_da=operatore,
        )

    produzione.delete()


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

    prelievo = (
        PrelievoProduzione.objects
        .select_related("produzione")
        .select_for_update()
        .get(pk=prelievo.pk)
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
    quantita_ottenuta_kg=None,
    ubicazione_destinazione=None,
    note="",
    operatore=None,
    pastorizzazione_completata=False,
    vuoto_controllato=False,
    pezzi_difettosi_finali=0,
    capsule_difettose_finali=0,
    peso_netto_vasetto_g=None,
):
    if not isinstance(produzione, Produzione):
        raise ValueError("La produzione non è valida.")

    produzione = (
        Produzione.objects
        .select_for_update()
        .get(pk=produzione.pk)
    )

    if produzione.stato != Produzione.Stato.BOZZA:
        raise ValueError("La produzione non è in bozza.")

    if produzione.lotto is not None:
        raise ValueError(
            "La produzione ha già un lotto associato."
        )

    if produzione.stato_roboqubo != Produzione.StatoRoboqubo.CONCLUSA:
        raise ValueError(
            "La produzione non può essere chiusa finché RoboQubo non è concluso."
        )

    tank_correnti = produzione.tank.filter(
        annullato=False,
        stato_invasettamento=TankProduzione.StatoInvasettamento.DISPONIBILE,
    )
    if not tank_correnti.exists():
        raise ValueError("Non è stato registrato alcun tank.")

    if tank_correnti.filter(
        Q(gradi_brix__isnull=True) | Q(ph__isnull=True)
    ).exists():
        raise ValueError("Completa i controlli Brix e pH di tutti i tank.")

    if not produzione.moca_igienizzati:
        raise ValueError("Conferma pulizia e igienizzazione degli imballaggi MOCA.")
    carrelli_correnti = produzione.carrelli.filter(lotto_uscita__isnull=True)
    if not carrelli_correnti.exists():
        raise ValueError("Registra almeno un carrello di invasettamento.")
    if carrelli_correnti.filter(chiuso_il__isnull=True).exists():
        raise ValueError("Completa tutti i carrelli prima di chiudere la lavorazione.")
    ultimo_carrello = carrelli_correnti.order_by("-numero").first()
    produzione.pastorizzazione_completata = True
    produzione.vuoto_controllato = True
    produzione.data_ora_pastorizzazione = ultimo_carrello.pastorizzazione_registrata_il
    produzione.data_ora_verifica_vuoto = ultimo_carrello.shock_vuoto_registrato_il

    if pastorizzazione_completata and not produzione.pastorizzazione_completata:
        produzione.pastorizzazione_completata = True
        produzione.data_ora_pastorizzazione = timezone.now()
    if vuoto_controllato and not produzione.vuoto_controllato:
        produzione.vuoto_controllato = True
        produzione.data_ora_verifica_vuoto = timezone.now()

    if not produzione.pastorizzazione_completata:
        raise ValueError("Conferma il completamento della pastorizzazione.")
    if not produzione.vuoto_controllato:
        raise ValueError("Conferma il controllo del vuoto.")

    quantita_prodotta = Decimal(str(quantita_prodotta))
    peso_netto_vasetto_g = (
        Decimal(str(peso_netto_vasetto_g))
        if peso_netto_vasetto_g is not None else None
    )
    vasetti_totali = quantita_prodotta + Decimal(str(pezzi_difettosi_finali))
    quantita_ottenuta_kg = (
        vasetti_totali * peso_netto_vasetto_g / Decimal("1000")
        if peso_netto_vasetto_g is not None
        else Decimal(str(quantita_ottenuta_kg or quantita_prodotta))
    )

    if quantita_prodotta <= 0:
        raise ValueError(
            "La quantità prodotta deve essere maggiore di zero."
        )

    prelievi_validi = produzione.prelievi.filter(
        Q(tank__isnull=True) | Q(tank__annullato=False)
    )
    if not prelievi_validi.exists() and produzione.quantita_batch_reintegrato_kg <= 0:
        raise ValueError(
            "Non sono stati registrati prelievi per questa produzione."
        )

    scarti_mancanti = prelievi_validi.filter(
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
        prelievi_validi.select_related("lotto__articolo")
    )
    quantita_teorica_kg = calcola_quantita_teorica_ricetta(produzione)
    resa_percentuale = (
        quantita_ottenuta_kg / quantita_teorica_kg * Decimal("100")
        if quantita_teorica_kg > 0 else None
    )

    utilizzo_per_articolo = {}
    for prelievo in prelievi:
        quantita_utilizzata = (
            prelievo.quantita_prelevata
            - prelievo.quantita_trasferita_nc
            - prelievo.quantita_scarto
        )
        articolo_id = prelievo.lotto.articolo_id
        utilizzo_per_articolo[articolo_id] = (
            utilizzo_per_articolo.get(articolo_id, Decimal("0"))
            + quantita_utilizzata
        )

    ingredienti_mancanti = []
    for riga in ricetta.righe.select_related("articolo").filter(
        ingrediente_prodotto=True
    ):
        if utilizzo_per_articolo.get(riga.articolo_id, Decimal("0")) <= 0:
            ingredienti_mancanti.append(
                f"{riga.articolo.codice} - {riga.articolo.descrizione}"
            )

    if ingredienti_mancanti and produzione.quantita_batch_reintegrato_kg <= 0:
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
    if quantita_ottenuta_kg <= 0:
        raise ValueError("La quantità effettiva ottenuta deve essere maggiore di zero.")

    materiali_moca = list(
        ricetta.righe.select_related("articolo").filter(
            ingrediente_prodotto=False,
            articolo__categoria=Articolo.Categoria.MOCA,
        )
    )
    for riga in materiali_moca:
        quantita_moca = vasetti_totali * riga.quantita
        prelievi_moca = registra_prelievi_produzione(
            produzione=produzione,
            articolo=riga.articolo,
            quantita_richiesta=quantita_moca,
            note=(
                f"Materiale MOCA per {quantita_prodotta} vasetti: "
                f"{riga.articolo.codice}"
            ),
            operatore=operatore,
        )
        for prelievo_moca in prelievi_moca:
            registra_scarto_prelievo_produzione(
                prelievo=prelievo_moca,
                quantita_scarto=Decimal("0"),
            )

    codice_lotto = (produzione.lotto_provvisorio or "").strip() or genera_codice_lotto_produzione(
        produzione.articolo, produzione.data_produzione,
    )
    if Lotto.objects.filter(articolo=produzione.articolo, codice_lotto=codice_lotto).exists():
        raise ValueError("Il numero lotto indicato è già utilizzato per questo articolo.")

    lotto = Lotto.objects.create(
        articolo=produzione.articolo,
        codice_lotto=codice_lotto,
        tipo=Lotto.Tipo.PRODUZIONE,
        fase=Lotto.Fase.INVASETTATO,
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
        causale="Produzione marmellata - prodotto invasettato",
        note=note,
        eseguito_da=operatore,
    )

    produzione.lotto = lotto
    produzione.quantita_prodotta = quantita_prodotta
    produzione.quantita_ottenuta_kg = quantita_ottenuta_kg
    produzione.peso_netto_vasetto_g = peso_netto_vasetto_g
    produzione.quantita_teorica_kg = quantita_teorica_kg
    produzione.resa_percentuale = resa_percentuale
    produzione.fase = Produzione.Fase.COMPLETATA
    produzione.ubicazione_destinazione = ubicazione_destinazione
    produzione.stato = Produzione.Stato.CONFERMATA
    produzione.stato_invasettamento = Produzione.StatoInvasettamento.CONCLUSO
    produzione.pezzi_difettosi_finali = pezzi_difettosi_finali
    produzione.capsule_difettose_finali = capsule_difettose_finali
    produzione.difetti_registrati_il = timezone.now()

    if note:
        produzione.note = note

    produzione.save(
        update_fields=[
            "lotto",
            "quantita_prodotta",
            "quantita_ottenuta_kg",
            "peso_netto_vasetto_g",
            "quantita_teorica_kg",
            "resa_percentuale",
            "fase",
            "ubicazione_destinazione",
            "stato",
            "stato_invasettamento",
            "pastorizzazione_completata",
            "vuoto_controllato",
            "data_ora_pastorizzazione",
            "data_ora_verifica_vuoto",
            "pezzi_difettosi_finali",
            "capsule_difettose_finali",
            "difetti_registrati_il",
            "note",
        ]
    )

    uscita = LottoUscitaProduzione.objects.create(
        produzione=produzione,
        lotto=lotto,
        provvisorio=False,
        numero_vasetti_buoni=int(quantita_prodotta),
        numero_vasetti_scartati=int(pezzi_difettosi_finali),
        numero_capsule_difettose=int(capsule_difettose_finali),
        peso_netto_vasetto_g=peso_netto_vasetto_g,
        quantita_ottenuta_kg=quantita_ottenuta_kg,
        quantita_teorica_kg=quantita_teorica_kg,
        resa_percentuale=resa_percentuale,
        note=note,
    )
    produzione.tank.filter(
        stato_invasettamento=TankProduzione.StatoInvasettamento.DISPONIBILE,
    ).update(
        stato_invasettamento=TankProduzione.StatoInvasettamento.INVASETTATO,
        invasettato_il=timezone.now(),
    )
    produzione.carrelli.filter(lotto_uscita__isnull=True).update(lotto_uscita=uscita)

    return produzione


@transaction.atomic
def registra_produzione(
    articolo,
    quantita_prodotta,
    consumi,
    data_produzione=None,
    note="",
    operatore=None,
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
            operatore=operatore,
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
        operatore=operatore,
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
    operatore=None,
):
    quantita_confezionata = Decimal(str(quantita_confezionata))

    if quantita_confezionata <= 0:
        raise ValueError(
            "La quantità confezionata deve essere maggiore di zero."
        )

    if (
        lotto_origine.articolo.categoria
        != lotto_origine.articolo.Categoria.PRODOTTO_FINITO
        or lotto_origine.fase != Lotto.Fase.INVASETTATO
    ):
        raise ValueError(
            "Il lotto di origine deve essere un prodotto invasettato."
        )

    if articolo_finito.categoria != articolo_finito.Categoria.PRODOTTO_FINITO:
        raise ValueError(
            "L'articolo di destinazione deve essere un prodotto finito."
        )

    if articolo_finito.pk != lotto_origine.articolo_id:
        raise ValueError("L'etichettatura non può cambiare l'articolo del lotto.")

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

    if giacenza_origine.quantita != quantita_confezionata:
        raise ValueError(
            "Etichetta l'intera quantità del lotto in un'unica operazione."
        )

    lotto_finito = lotto_origine

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
        eseguito_da=operatore,
    )

    giacenza_finito, _ = (
        Giacenza.objects
        .select_for_update()
        .get_or_create(
            lotto=lotto_finito,
            ubicazione=ubicazione_destinazione,
            defaults={
                "quantita": Decimal("0"),
            },
        )
    )

    giacenza_finito.quantita += quantita_confezionata
    giacenza_finito.save(
        update_fields=["quantita"]
    )

    lotto_origine.fase = Lotto.Fase.ETICHETTATO
    lotto_origine.save(update_fields=["fase"])

    Movimento.objects.create(
        tipo=Movimento.Tipo.PACKAGING,
        lotto=lotto_finito,
        quantita=quantita_confezionata,
        ubicazione_origine=None,
        ubicazione_destinazione=ubicazione_destinazione,
        causale="Prodotto finito da confezionamento",
        note=note,
        eseguito_da=operatore,
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
                eseguito_da=operatore,
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
    operatore=None,
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

    if lotto_prodotto.fase != Lotto.Fase.ETICHETTATO:
        raise ValueError(
            "Il lotto deve essere etichettato prima dell'inscatolamento."
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
        eseguito_da=operatore,
    )

    if quantita_sfusa == quantita_prodotti:
        lotto_prodotto.fase = Lotto.Fase.INSCATOLATO
        lotto_prodotto.save(update_fields=["fase"])

    return inscatolamento

def proponi_prelievi_articolo(
    articolo,
    quantita_richiesta,
    rispetta_uda=False,
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

    quantita_da_proporre = quantita_richiesta
    proposta = []
    quantita_disponibile = Decimal("0")

    for giacenza in giacenze:
        peso_uda = giacenza.lotto.quantita_singola_uda
        arrotonda_uda = (
            rispetta_uda
            and peso_uda is not None
            and peso_uda > 0
            and giacenza.ubicazione.tipo_magazzino
            != Ubicazione.TipoMagazzino.PRODUZIONE
        )
        quantita_utilizzabile = giacenza.quantita
        if arrotonda_uda:
            quantita_utilizzabile = (
                giacenza.quantita / peso_uda
            ).to_integral_value(rounding=ROUND_DOWN) * peso_uda
        quantita_disponibile += quantita_utilizzabile

        if quantita_da_proporre <= 0 or quantita_utilizzabile <= 0:
            continue

        quantita_proposta = min(quantita_utilizzabile, quantita_da_proporre)
        quantita_movimentata = quantita_proposta
        if arrotonda_uda:
            quantita_movimentata = (
                quantita_proposta / peso_uda
            ).to_integral_value(rounding=ROUND_CEILING) * peso_uda

        proposta.append(
            {
                "giacenza_id": giacenza.pk,
                "lotto": giacenza.lotto,
                "ubicazione": giacenza.ubicazione,
                "disponibile": giacenza.quantita,
                "quantita_proposta": quantita_proposta,
                "quantita_movimentata": quantita_movimentata,
                "quantita_resa_produzione": quantita_movimentata - quantita_proposta,
            }
        )

        quantita_da_proporre -= quantita_proposta

    return {
        "articolo": articolo,
        "criterio": "FEFO/FIFO automatico",
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
    operatore=None,
):
    from .models import (
        ProduzioneSemilavorato,
        PrelievoProduzioneSemilavorato,
    )

    if not isinstance(produzione, ProduzioneSemilavorato):
        raise ValueError(
            "La produzione semilavorato non è valida."
        )

    produzione = (
        ProduzioneSemilavorato.objects
        .select_for_update()
        .get(pk=produzione.pk)
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
            .get(pk=riga["giacenza_id"])
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
            scaffale_origine=giacenza.scaffale,
            piano_origine=giacenza.piano,
            ubicazione_destinazione=None,
            causale="Prelievo produzione semilavorato",
            note=note,
            eseguito_da=operatore,
        )

        prelievo = PrelievoProduzioneSemilavorato.objects.create(
            produzione=produzione,
            lotto=giacenza.lotto,
            ubicazione_origine=giacenza.ubicazione,
            scaffale_origine=giacenza.scaffale,
            piano_origine=giacenza.piano,
            quantita_prelevata=quantita_prelevata,
            quantita_scarto=None,
            note=note,
        )

        prelievi.append(prelievo)

    return prelievi


@transaction.atomic
def elimina_produzione_semilavorato_bozza(produzione, operatore=None):
    from .models import ProduzioneSemilavorato

    if not isinstance(produzione, ProduzioneSemilavorato):
        raise ValueError("La produzione semilavorato non è valida.")

    produzione = (
        ProduzioneSemilavorato.objects.select_for_update()
        .get(pk=produzione.pk)
    )
    if produzione.stato != ProduzioneSemilavorato.Stato.BOZZA:
        raise ValueError(
            "È possibile eliminare solo una produzione semilavorato in bozza."
        )

    prelievi = list(
        produzione.prelievi.select_related(
            "lotto", "ubicazione_origine"
        ).select_for_update()
    )
    for prelievo in prelievi:
        giacenza, _ = Giacenza.objects.select_for_update().get_or_create(
            lotto=prelievo.lotto,
            ubicazione=prelievo.ubicazione_origine,
            scaffale=prelievo.scaffale_origine,
            piano=prelievo.piano_origine,
            defaults={"quantita": Decimal("0")},
        )
        giacenza.quantita += prelievo.quantita_prelevata
        giacenza.save(update_fields=["quantita"])
        Movimento.objects.create(
            tipo=Movimento.Tipo.RETTIFICA,
            lotto=prelievo.lotto,
            quantita=prelievo.quantita_prelevata,
            ubicazione_destinazione=prelievo.ubicazione_origine,
            causale="Annullamento produzione semilavorato in bozza",
            note=f"Produzione semilavorato annullata n. {produzione.pk}",
            eseguito_da=operatore,
        )

    produzione.delete()


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

    prelievo = (
        PrelievoProduzioneSemilavorato.objects
        .select_related("produzione")
        .select_for_update()
        .get(pk=prelievo.pk)
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
    operatore=None,
):
    from .models import ProduzioneSemilavorato

    if not isinstance(produzione, ProduzioneSemilavorato):
        raise ValueError(
            "La produzione semilavorato non è valida."
        )

    produzione = (
        ProduzioneSemilavorato.objects
        .select_for_update()
        .get(pk=produzione.pk)
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
        eseguito_da=operatore,
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


@transaction.atomic
def modifica_risultato_produzione(
    produzione,
    lotto_definitivo,
    quantita_prodotta,
    peso_netto_vasetto_g,
    pezzi_difettosi_finali,
    capsule_difettose_finali,
    note="",
    operatore=None,
):
    produzione = Produzione.objects.select_for_update().select_related(
        "lotto", "ubicazione_destinazione",
    ).get(pk=produzione.pk)
    if produzione.stato != Produzione.Stato.CONFERMATA or produzione.lotto is None:
        raise ValueError("È possibile modificare solo una produzione già confermata.")

    lotto_definitivo = lotto_definitivo.strip()
    if Lotto.objects.filter(
        articolo=produzione.articolo, codice_lotto=lotto_definitivo,
    ).exclude(pk=produzione.lotto_id).exists():
        raise ValueError("Il numero lotto è già utilizzato per questo prodotto.")

    nuova_quantita = Decimal(str(quantita_prodotta))
    vecchia_quantita = produzione.quantita_prodotta or Decimal("0")
    differenza = nuova_quantita - vecchia_quantita
    giacenza = Giacenza.objects.select_for_update().filter(
        lotto=produzione.lotto,
        ubicazione=produzione.ubicazione_destinazione,
        scaffale="", piano="",
    ).first()
    if giacenza is None:
        raise ValueError("La giacenza originaria del lotto non è disponibile.")
    if differenza < 0 and giacenza.quantita < -differenza:
        raise ValueError(
            "Non è possibile ridurre i vasetti: una parte della quantità è già stata "
            "spostata o consumata. Riportala prima nell'ubicazione originaria."
        )

    if differenza:
        giacenza.quantita += differenza
        giacenza.save(update_fields=["quantita"])
        Movimento.objects.create(
            tipo=Movimento.Tipo.RETTIFICA,
            lotto=produzione.lotto,
            quantita=abs(differenza),
            ubicazione_origine=(produzione.ubicazione_destinazione if differenza < 0 else None),
            ubicazione_destinazione=(produzione.ubicazione_destinazione if differenza > 0 else None),
            causale="Correzione quantità produzione confermata",
            note=f"Da {vecchia_quantita} a {nuova_quantita} vasetti buoni. {note}".strip(),
            eseguito_da=operatore,
        )

    produzione.lotto.codice_lotto = lotto_definitivo
    produzione.lotto.quantita_iniziale = nuova_quantita
    produzione.lotto.note = note
    produzione.lotto.save(update_fields=["codice_lotto", "quantita_iniziale", "note"])
    produzione.quantita_prodotta = nuova_quantita
    produzione.peso_netto_vasetto_g = Decimal(str(peso_netto_vasetto_g))
    vasetti_totali = nuova_quantita + Decimal(str(pezzi_difettosi_finali))
    produzione.quantita_ottenuta_kg = (
        vasetti_totali * produzione.peso_netto_vasetto_g / Decimal("1000")
    )
    produzione.resa_percentuale = (
        produzione.quantita_ottenuta_kg / produzione.quantita_teorica_kg * Decimal("100")
        if produzione.quantita_teorica_kg else None
    )
    produzione.pezzi_difettosi_finali = pezzi_difettosi_finali
    produzione.capsule_difettose_finali = capsule_difettose_finali
    produzione.note = note
    produzione.save(update_fields=[
        "quantita_prodotta", "peso_netto_vasetto_g", "quantita_ottenuta_kg",
        "resa_percentuale",
        "pezzi_difettosi_finali", "capsule_difettose_finali", "note",
    ])
    return produzione
