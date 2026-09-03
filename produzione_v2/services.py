from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .domain import ValutatoreControllo
from .calendar import CalendarioLinea
from .scheduling import PianificatoreDinamicoLinea, PianificatoreDinamicoOrdine
from .readiness import ValutatoreProntezzaOrdine
from .models import (
    AbilitazioneOperatore, AllocazioneOrigineUnita, AppartenenzaUnitaLotto,
    AssegnazioneOperatore, ConsumoMateriale, ConsuntivoEtichettatura,
    DefinizioneControllo, DipendenzaPassaggio, EventoProduzione, FabbisognoMateriale,
    FaseProduzione, ImpegnoRisorsa, MovimentoProduzione, NonConformita,
    LottoCommerciale, LottoLavorazione, OrigineLottoCommerciale,
    OrdineProduzione, RisorsaProduzione,
    MovimentoOutput, OutputProduzione, RilevazioneControllo,
    TipoUnitaProduzione, UnitaProduzione,
)


def _evento(ordine, operatore, tipo, fase=None, **dati):
    return EventoProduzione.registra(
        ordine=ordine, fase=fase, tipo=tipo, dati=dati, operatore=operatore,
    )


@transaction.atomic
def prepara_ordine(ordine, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.PIANIFICATO:
        raise ValidationError("Soltanto un ordine pianificato può essere preparato.")
    passaggi = list(ordine.linea.passaggi.select_related("stazione").order_by("ordine"))
    if not passaggi:
        raise ValidationError("La linea non contiene stazioni di lavoro.")
    fasi = []
    for passaggio in passaggi:
        fasi.append(FaseProduzione.objects.create(
            ordine=ordine, passaggio=passaggio, sequenza=passaggio.ordine,
        ))
    if ordine.pianificato_per:
        calendario = CalendarioLinea(ordine.linea)
        inizio_giornata = calendario.normalizza(ordine.linea.prima_disponibilita(
            ordine.pianificato_per, ordine_id=ordine.pk,
        ))
        fasi_per_passaggio = {fase.passaggio_id: fase for fase in fasi}
        passaggi_per_id = {passaggio.pk: passaggio for passaggio in passaggi}
        non_pianificati = set(passaggi_per_id)
        while non_pianificati:
            avanzamento = False
            for passaggio_id in list(non_pianificati):
                passaggio = passaggi_per_id[passaggio_id]
                dipendenze = list(passaggio.dipendenze.all())
                predecessori = [d.predecessore_id for d in dipendenze]
                if not dipendenze:
                    predecessori = [
                        altro.pk for altro in passaggi if altro.ordine < passaggio.ordine
                    ]
                if any(predecessore in non_pianificati for predecessore in predecessori):
                    continue
                if dipendenze:
                    fine_predecessori = [
                        (
                            fasi_per_passaggio[d.predecessore_id].pianificata_inizio
                            if d.modalita == DipendenzaPassaggio.Modalita.FLUSSO
                            else fasi_per_passaggio[d.predecessore_id].pianificata_fine
                        )
                        for d in dipendenze
                    ]
                else:
                    fine_predecessori = [
                        fasi_per_passaggio[predecessore].pianificata_fine
                        for predecessore in predecessori
                    ]
                inizio = calendario.normalizza(
                    max(fine_predecessori) if fine_predecessori else inizio_giornata
                )
                fase = fasi_per_passaggio[passaggio_id]
                fase.pianificata_inizio = inizio
                fase.pianificata_fine = calendario.aggiungi_minuti(
                    inizio, passaggio.durata_standard_minuti,
                )
                fase.save(update_fields=("pianificata_inizio", "pianificata_fine"))
                non_pianificati.remove(passaggio_id)
                avanzamento = True
            if not avanzamento:
                raise ValidationError("Il percorso contiene dipendenze non pianificabili.")
    if ordine.ciclo_id:
        ciclo = ordine.ciclo
        if not ciclo.attivo:
            raise ValidationError("Il ciclo produttivo selezionato non è attivo.")
        ordine.resa_minima_percentuale = ciclo.resa_minima_percentuale
        ordine.resa_massima_percentuale = ciclo.resa_massima_percentuale
        ordine.save(update_fields=(
            "resa_minima_percentuale", "resa_massima_percentuale",
        ))
        moltiplicatore = ordine.quantita_pianificata / ciclo.quantita_riferimento
        for riga in ciclo.ricetta.righe.select_related("articolo"):
            FabbisognoMateriale.objects.create(
                ordine=ordine, fase=fasi[0], articolo=riga.articolo,
                quantita_prevista=riga.quantita * moltiplicatore,
                unita_misura=riga.articolo.unita_misura,
                origine_ricetta=riga,
            )
    ordine.stato = OrdineProduzione.Stato.PRONTO
    ordine.save(update_fields=("stato",))
    _evento(ordine, operatore, "ORDINE_PREPARATO", numero_fasi=len(passaggi))
    return ordine


@transaction.atomic
def avvia_ordine(ordine, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.PRONTO:
        raise ValidationError("Soltanto un ordine pronto può essere avviato.")
    problemi = ValutatoreProntezzaOrdine(ordine).valuta()
    if problemi:
        raise ValidationError(
            "Ordine non pronto: " + "; ".join(
                problema.descrizione for problema in problemi
            )
        )
    ordine.stato = OrdineProduzione.Stato.IN_CORSO
    ordine.avviato_il = timezone.now()
    ordine.save(update_fields=("stato", "avviato_il"))
    _evento(ordine, operatore, "ORDINE_AVVIATO")
    return ordine


@transaction.atomic
def avvia_fase(fase, operatore):
    fase = FaseProduzione.objects.select_for_update().select_related("ordine").get(pk=fase.pk)
    if fase.ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("L'ordine non è in corso.")
    if fase.stato != FaseProduzione.Stato.DA_AVVIARE:
        raise ValidationError("La fase non è da avviare.")
    if fase.stazione.richiede_operatore_abilitato:
        oggi = timezone.localdate()
        assegnato_abilitato = fase.assegnazioni.filter(
            terminato_il__isnull=True,
            operatore__abilitazioni_produzione_v2__stazione=fase.stazione,
            operatore__abilitazioni_produzione_v2__attiva=True,
            operatore__abilitazioni_produzione_v2__valida_dal__lte=oggi,
        ).filter(
            Q(operatore__abilitazioni_produzione_v2__valida_fino_al__isnull=True)
            | Q(operatore__abilitazioni_produzione_v2__valida_fino_al__gte=oggi)
        ).exists()
        if not assegnato_abilitato:
            raise ValidationError("Assegna almeno un operatore abilitato alla stazione.")
    if fase.stazione.richiede_risorsa and not fase.impegni_risorse.filter(
        rilasciata_il__isnull=True,
    ).exists():
        raise ValidationError("Assegna almeno una risorsa produttiva alla fase.")
    if not fase.eseguibile:
        raise ValidationError("Le fasi precedenti non sono state completate.")
    fase.stato = FaseProduzione.Stato.IN_CORSO
    fase.iniziata_il = timezone.now()
    fase.save(update_fields=("stato", "iniziata_il"))
    _evento(fase.ordine, operatore, "FASE_AVVIATA", fase=fase)
    return fase


@transaction.atomic
def salta_fase(fase, motivo, operatore):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "ordine", "passaggio",
    ).get(pk=fase.pk)
    if fase.ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("L'ordine non è in corso.")
    if fase.passaggio.obbligatoria:
        raise ValidationError("Una fase obbligatoria non può essere saltata.")
    if fase.stato != FaseProduzione.Stato.DA_AVVIARE:
        raise ValidationError("Soltanto una fase non ancora avviata può essere saltata.")
    if not fase.eseguibile:
        raise ValidationError("Le fasi precedenti non sono state completate.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Indica il motivo per cui la fase viene saltata.")
    fase.stato = FaseProduzione.Stato.SALTATA
    fase.completata_il = timezone.now()
    fase.note = "\n".join(filter(None, (fase.note, f"Fase saltata: {motivo}")))
    fase.save(update_fields=("stato", "completata_il", "note"))
    _evento(
        fase.ordine, operatore, "FASE_SALTATA", fase=fase, motivo=motivo,
    )
    return fase


@transaction.atomic
def aggiungi_dipendenza(
    passaggio, predecessore,
    modalita=DipendenzaPassaggio.Modalita.COMPLETAMENTO,
    quantita_minima_avvio=Decimal("0"),
):
    passaggio = passaggio.__class__.objects.select_for_update().get(pk=passaggio.pk)
    predecessore = predecessore.__class__.objects.get(pk=predecessore.pk)
    if passaggio.linea_id != predecessore.linea_id:
        raise ValidationError("I passaggi devono appartenere alla stessa linea.")
    if passaggio.pk == predecessore.pk:
        raise ValidationError("Un passaggio non può dipendere da sé stesso.")

    da_visitare = [passaggio.pk]
    visitati = set()
    while da_visitare:
        corrente = da_visitare.pop()
        if corrente == predecessore.pk:
            raise ValidationError("La dipendenza creerebbe un ciclo nel percorso produttivo.")
        if corrente in visitati:
            continue
        visitati.add(corrente)
        da_visitare.extend(
            DipendenzaPassaggio.objects.filter(
                predecessore_id=corrente,
            ).values_list("passaggio_id", flat=True)
        )
    dipendenza = DipendenzaPassaggio(
        passaggio=passaggio, predecessore=predecessore, modalita=modalita,
        quantita_minima_avvio=quantita_minima_avvio,
    )
    dipendenza.full_clean()
    dipendenza.save()
    return dipendenza


@transaction.atomic
def assegna_operatore(fase, operatore_assegnato, responsabile):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "ordine", "passaggio__stazione",
    ).get(pk=fase.pk)
    if fase.stato not in (
        FaseProduzione.Stato.DA_AVVIARE,
        FaseProduzione.Stato.IN_CORSO,
        FaseProduzione.Stato.IN_ATTESA,
    ):
        raise ValidationError("Non è possibile assegnare operatori nello stato attuale della fase.")
    if not operatore_assegnato.is_active:
        raise ValidationError("L'operatore selezionato non è attivo.")
    if fase.stazione.richiede_operatore_abilitato:
        abilitazione = AbilitazioneOperatore.objects.filter(
            operatore=operatore_assegnato, stazione=fase.stazione,
        ).first()
        if abilitazione is None or not abilitazione.valida_il():
            raise ValidationError("L'operatore non possiede un'abilitazione valida per la stazione.")
    assegnazione, creata = AssegnazioneOperatore.objects.get_or_create(
        fase=fase, operatore=operatore_assegnato,
    )
    if not creata and assegnazione.terminato_il is not None:
        assegnazione.terminato_il = None
        assegnazione.save(update_fields=("terminato_il",))
    _evento(
        fase.ordine, responsabile, "OPERATORE_ASSEGNATO", fase=fase,
        operatore_id=operatore_assegnato.pk,
        operatore_username=operatore_assegnato.username,
    )
    return assegnazione


@transaction.atomic
def termina_assegnazione(assegnazione, responsabile):
    assegnazione = AssegnazioneOperatore.objects.select_for_update().select_related(
        "fase__ordine", "operatore",
    ).get(pk=assegnazione.pk)
    if assegnazione.terminato_il is not None:
        raise ValidationError("L'assegnazione è già terminata.")
    assegnazione.terminato_il = timezone.now()
    assegnazione.save(update_fields=("terminato_il",))
    _evento(
        assegnazione.fase.ordine, responsabile, "OPERATORE_RILASCIATO",
        fase=assegnazione.fase, operatore_id=assegnazione.operatore_id,
    )
    return assegnazione


@transaction.atomic
def impegna_risorsa(fase, risorsa, operatore):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "ordine", "passaggio__stazione",
    ).get(pk=fase.pk)
    risorsa = RisorsaProduzione.objects.select_for_update().get(pk=risorsa.pk)
    if fase.stato not in (
        FaseProduzione.Stato.DA_AVVIARE,
        FaseProduzione.Stato.IN_CORSO,
        FaseProduzione.Stato.IN_ATTESA,
    ):
        raise ValidationError("La risorsa non può essere assegnata nello stato attuale della fase.")
    if not risorsa.attiva or risorsa.stazione_id != fase.stazione.pk:
        raise ValidationError("La risorsa non è disponibile per questa stazione.")
    conflitto = risorsa.impegni.filter(rilasciata_il__isnull=True).exclude(fase=fase).first()
    if conflitto:
        raise ValidationError(
            f"La risorsa è già impegnata dall'ordine {conflitto.fase.ordine.codice}."
        )
    impegno, creato = ImpegnoRisorsa.objects.get_or_create(
        fase=fase, risorsa=risorsa, defaults={"assegnata_da": operatore},
    )
    if not creato and impegno.rilasciata_il is not None:
        impegno.rilasciata_il = None
        impegno.assegnata_da = operatore
        impegno.save(update_fields=("rilasciata_il", "assegnata_da"))
    _evento(
        fase.ordine, operatore, "RISORSA_IMPEGNATA", fase=fase,
        risorsa_id=risorsa.pk, risorsa_codice=risorsa.codice,
    )
    return impegno


@transaction.atomic
def rilascia_risorsa(impegno, operatore):
    impegno = ImpegnoRisorsa.objects.select_for_update().select_related(
        "fase__ordine", "risorsa",
    ).get(pk=impegno.pk)
    if impegno.rilasciata_il is not None:
        raise ValidationError("La risorsa è già stata rilasciata.")
    impegno.rilasciata_il = timezone.now()
    impegno.save(update_fields=("rilasciata_il",))
    _evento(
        impegno.fase.ordine, operatore, "RISORSA_RILASCIATA", fase=impegno.fase,
        risorsa_id=impegno.risorsa_id, risorsa_codice=impegno.risorsa.codice,
    )
    return impegno


@transaction.atomic
def registra_controllo(fase, definizione, valore, operatore, unita=None, note=""):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "passaggio__stazione", "ordine__ciclo",
    ).get(pk=fase.pk)
    definizione = DefinizioneControllo.objects.get(pk=definizione.pk)
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("I controlli possono essere registrati solo su una fase in corso.")
    if definizione.stazione_id != fase.passaggio.stazione_id:
        raise ValidationError("Il controllo non appartiene alla stazione della fase.")
    if unita is not None and unita.fase_id != fase.id:
        raise ValidationError("L'unità non appartiene alla fase.")
    regole = definizione.regole
    if fase.ordine.ciclo_id:
        specifica = fase.ordine.ciclo.regole_controllo.filter(
            definizione=definizione, attiva=True,
        ).first()
        if specifica is not None:
            regole = specifica.regole
    esito = ValutatoreControllo(definizione, regole=regole).valuta(valore)
    rilevazione = RilevazioneControllo.objects.create(
        fase=fase, unita=unita, definizione=definizione, valore=valore,
        esito=esito, regole_applicate=regole, rilevato_da=operatore, note=note,
    )
    _evento(
        fase.ordine, operatore, "CONTROLLO_REGISTRATO", fase=fase,
        controllo=definizione.codice, esito=esito,
    )
    if esito == RilevazioneControllo.Esito.NON_CONFORME:
        apri_non_conformita(
            fase.ordine,
            f"Controllo {definizione.nome} non conforme: {valore}",
            operatore, fase=fase, unita=unita, rilevazione=rilevazione,
        )
    return rilevazione


def quantita_prenotabile(giacenza):
    impegnata = giacenza.impegni_produzione_v2.filter(
        stato=ConsumoMateriale.Stato.PRENOTATO,
    ).aggregate(totale=models.Sum("quantita"))["totale"] or 0
    return giacenza.quantita - impegnata


@transaction.atomic
def prenota_materiale(fase, giacenza, quantita, operatore):
    from magazzino.models import Giacenza

    fase = FaseProduzione.objects.select_for_update().select_related("ordine").get(pk=fase.pk)
    giacenza = Giacenza.objects.select_for_update().select_related(
        "lotto__articolo", "ubicazione",
    ).get(pk=giacenza.pk)
    quantita = Decimal(str(quantita))
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("I materiali possono essere prenotati solo su una fase in corso.")
    if quantita <= 0:
        raise ValidationError("La quantità deve essere maggiore di zero.")
    if fase.ordine.fabbisogni.exists():
        fabbisogno = FabbisognoMateriale.objects.select_for_update().filter(
            ordine=fase.ordine, articolo=giacenza.lotto.articolo,
        ).first()
        if fabbisogno is None:
            raise ValidationError("Il materiale non è previsto dal ciclo produttivo dell'ordine.")
        if quantita > fabbisogno.quantita_residua:
            raise ValidationError("La quantità supera il fabbisogno residuo dell'articolo.")
    if quantita_prenotabile(giacenza) < quantita:
        raise ValidationError("Quantità prenotabile insufficiente nella posizione selezionata.")
    consumo = ConsumoMateriale.objects.create(
        ordine=fase.ordine, fase=fase, articolo=giacenza.lotto.articolo,
        lotto=giacenza.lotto, giacenza=giacenza, ubicazione=giacenza.ubicazione,
        scaffale=giacenza.scaffale, piano=giacenza.piano,
        quantita=quantita, stato=ConsumoMateriale.Stato.PRENOTATO,
    )
    _evento(
        fase.ordine, operatore, "MATERIALE_PRENOTATO", fase=fase,
        consumo_id=consumo.pk, lotto=giacenza.lotto.codice_lotto,
        quantita=str(quantita),
    )
    return consumo


@transaction.atomic
def consuma_materiale(consumo, operatore):
    from magazzino.services import registra_consumo

    consumo = ConsumoMateriale.objects.select_for_update().select_related(
        "ordine", "fase", "lotto", "ubicazione",
    ).get(pk=consumo.pk)
    if consumo.stato != ConsumoMateriale.Stato.PRENOTATO:
        raise ValidationError("Soltanto un materiale prenotato può essere consumato.")
    try:
        movimento = registra_consumo(
            lotto=consumo.lotto, quantita=consumo.quantita,
            ubicazione_origine=consumo.ubicazione,
            scaffale_origine=consumo.scaffale, piano_origine=consumo.piano,
            causale=f"Produzione V2 - ordine {consumo.ordine.codice}",
            note=f"Fase {consumo.fase.sequenza}: {consumo.fase.stazione.nome}",
            operatore=operatore,
        )
    except ValueError as errore:
        raise ValidationError(str(errore)) from errore
    consumo.stato = ConsumoMateriale.Stato.CONSUMATO
    consumo.save(update_fields=("stato",))
    MovimentoProduzione.objects.create(
        consumo=consumo, movimento=movimento, causale="CONSUMO",
    )
    _evento(
        consumo.ordine, operatore, "MATERIALE_CONSUMATO", fase=consumo.fase,
        consumo_id=consumo.pk, movimento_id=movimento.pk,
    )
    return consumo


@transaction.atomic
def consuma_materiali_prenotati(fase, operatore):
    fase = FaseProduzione.objects.select_for_update().get(pk=fase.pk)
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("Il consumo cumulativo richiede una fase in corso.")
    prenotati = list(fase.materiali.select_for_update().filter(
        stato=ConsumoMateriale.Stato.PRENOTATO,
    ).order_by("creato_il", "id"))
    if not prenotati:
        raise ValidationError("Non ci sono materiali prenotati da consumare.")
    consumati = [consuma_materiale(consumo, operatore) for consumo in prenotati]
    _evento(
        fase.ordine, operatore, "CONSUMO_MATERIALI_CUMULATIVO", fase=fase,
        consumi=[consumo.pk for consumo in consumati],
    )
    return consumati


@transaction.atomic
def reintegra_materiale(consumo, operatore):
    from magazzino.models import Movimento
    from magazzino.services import registra_carico

    consumo = ConsumoMateriale.objects.select_for_update().select_related(
        "ordine", "fase", "lotto", "ubicazione",
    ).get(pk=consumo.pk)
    if consumo.stato != ConsumoMateriale.Stato.CONSUMATO:
        raise ValidationError("Soltanto un materiale consumato può essere reintegrato.")
    try:
        movimento = registra_carico(
            lotto=consumo.lotto, quantita=consumo.quantita,
            ubicazione=consumo.ubicazione, scaffale=consumo.scaffale,
            piano=consumo.piano,
            causale=f"Reintegro produzione V2 - ordine {consumo.ordine.codice}",
            note=f"Reintegro dalla fase {consumo.fase.sequenza}", operatore=operatore,
        )
    except ValueError as errore:
        raise ValidationError(str(errore)) from errore
    movimento.tipo = Movimento.Tipo.REINTEGRO
    movimento.save(update_fields=("tipo",))
    consumo.stato = ConsumoMateriale.Stato.REINTEGRATO
    consumo.save(update_fields=("stato",))
    MovimentoProduzione.objects.create(
        consumo=consumo, movimento=movimento, causale="REINTEGRO",
    )
    _evento(
        consumo.ordine, operatore, "MATERIALE_REINTEGRATO", fase=consumo.fase,
        consumo_id=consumo.pk, movimento_id=movimento.pk,
    )
    return consumo


@transaction.atomic
def scarta_materiale(consumo, operatore):
    from magazzino.models import Movimento
    from magazzino.services import registra_consumo

    consumo = ConsumoMateriale.objects.select_for_update().select_related(
        "ordine", "fase", "lotto", "ubicazione",
    ).get(pk=consumo.pk)
    if consumo.stato == ConsumoMateriale.Stato.PRENOTATO:
        try:
            movimento = registra_consumo(
                lotto=consumo.lotto, quantita=consumo.quantita,
                ubicazione_origine=consumo.ubicazione,
                scaffale_origine=consumo.scaffale, piano_origine=consumo.piano,
                causale=f"Scarto produzione V2 - ordine {consumo.ordine.codice}",
                note=f"Scarto dalla fase {consumo.fase.sequenza}", operatore=operatore,
            )
        except ValueError as errore:
            raise ValidationError(str(errore)) from errore
        movimento.tipo = Movimento.Tipo.SCARTO_NC
        movimento.save(update_fields=("tipo",))
        MovimentoProduzione.objects.create(
            consumo=consumo, movimento=movimento, causale="SCARTO",
        )
    elif consumo.stato != ConsumoMateriale.Stato.CONSUMATO:
        raise ValidationError("Il materiale non può essere scartato nello stato corrente.")
    consumo.stato = ConsumoMateriale.Stato.SCARTATO
    consumo.save(update_fields=("stato",))
    _evento(
        consumo.ordine, operatore, "MATERIALE_SCARTATO", fase=consumo.fase,
        consumo_id=consumo.pk,
    )
    return consumo


@transaction.atomic
def apri_non_conformita(
    ordine, motivo, operatore, fase=None, unita=None, consumo=None,
    rilevazione=None, codice=None, tipo=None,
):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato not in (
        OrdineProduzione.Stato.IN_CORSO,
        OrdineProduzione.Stato.SOSPESO,
        OrdineProduzione.Stato.BLOCCATO_NC,
    ):
        raise ValidationError("La NC può essere aperta soltanto su un ordine attivo.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Il motivo della non conformità è obbligatorio.")
    if fase is not None:
        fase = FaseProduzione.objects.select_for_update().get(pk=fase.pk, ordine=ordine)
    if unita is not None:
        unita = UnitaProduzione.objects.select_for_update().get(pk=unita.pk, ordine=ordine)
        if fase is not None and unita.fase_id != fase.pk:
            raise ValidationError("L'unità non appartiene alla fase selezionata.")
    if consumo is not None:
        consumo = ConsumoMateriale.objects.select_for_update().get(pk=consumo.pk, ordine=ordine)
        if fase is not None and consumo.fase_id != fase.pk:
            raise ValidationError("Il materiale non appartiene alla fase selezionata.")
    if rilevazione is not None:
        rilevazione = RilevazioneControllo.objects.select_for_update().get(
            pk=rilevazione.pk, fase__ordine=ordine,
        )
        if fase is not None and rilevazione.fase_id != fase.pk:
            raise ValidationError("La rilevazione non appartiene alla fase selezionata.")

    progressivo = ordine.non_conformita.count() + 1
    codice = codice or f"{ordine.codice}-NC-{progressivo:03d}"
    tipo = tipo or (
        NonConformita.Tipo.QUALITA if rilevazione is not None
        else NonConformita.Tipo.MATERIALE if consumo is not None
        else NonConformita.Tipo.UNITA if unita is not None
        else NonConformita.Tipo.ALTRO
    )
    nc = NonConformita.objects.create(
        codice=codice, tipo=tipo, ordine=ordine, fase=fase, unita=unita, consumo=consumo,
        rilevazione=rilevazione,
        motivo=motivo, aperta_da=operatore,
        stato_ordine_precedente=ordine.stato,
        stato_fase_precedente=fase.stato if fase else "",
        stato_unita_precedente=unita.stato if unita else "",
    )
    ordine.stato = OrdineProduzione.Stato.BLOCCATO_NC
    ordine.save(update_fields=("stato",))
    if fase is not None and fase.stato not in (
        FaseProduzione.Stato.COMPLETATA, FaseProduzione.Stato.ANNULLATA,
    ):
        fase.stato = FaseProduzione.Stato.BLOCCATA
        fase.save(update_fields=("stato",))
    if unita is not None:
        unita.stato = UnitaProduzione.Stato.QUARANTENA
        unita.save(update_fields=("stato",))
    _evento(
        ordine, operatore, "NON_CONFORMITA_APERTA", fase=fase,
        nc_id=nc.pk, codice=nc.codice,
    )
    return nc


def _applica_matrice_non_conformita(ordine, nc_decisiva, operatore):
    nc_chiuse = ordine.non_conformita.filter(stato=NonConformita.Stato.CHIUSA)
    batch_reintegrati = nc_chiuse.filter(
        unita__isnull=False,
        esito__in=(NonConformita.Esito.REINTEGRO, NonConformita.Esito.DEROGA),
    )
    batch_scartati = nc_chiuse.filter(
        unita__isnull=False,
        esito__in=(NonConformita.Esito.SCARTO, NonConformita.Esito.ANNULLAMENTO),
    ).exists()
    materiali_scartati = nc_chiuse.filter(
        consumo__isnull=False,
        esito__in=(NonConformita.Esito.SCARTO, NonConformita.Esito.ANNULLAMENTO),
    ).exists()
    annullamento_esplicito = nc_chiuse.filter(
        esito=NonConformita.Esito.ANNULLAMENTO,
    ).exists()
    resa_scartata = nc_chiuse.filter(
        tipo=NonConformita.Tipo.RESA,
        esito=NonConformita.Esito.SCARTO,
    ).exists()

    if annullamento_esplicito or resa_scartata or (materiali_scartati and batch_scartati):
        decisione = NonConformita.DecisioneFlusso.PRODUZIONE_ABORTITA
    elif materiali_scartati and not batch_reintegrati.exists():
        decisione = NonConformita.DecisioneFlusso.PRODUZIONE_ABORTITA
    elif materiali_scartati:
        decisione = NonConformita.DecisioneFlusso.SOLO_REINTEGRATI
    elif batch_scartati:
        decisione = NonConformita.DecisioneFlusso.SENZA_SCARTATI
    else:
        decisione = NonConformita.DecisioneFlusso.PROSEGUE_TUTTI

    nc_decisiva.decisione_flusso = decisione
    nc_decisiva.save(update_fields=("decisione_flusso",))
    momento = timezone.now()
    if decisione == NonConformita.DecisioneFlusso.PRODUZIONE_ABORTITA:
        ordine.stato = OrdineProduzione.Stato.ABORTITO
        ordine.fasi.exclude(
            stato__in=(FaseProduzione.Stato.COMPLETATA, FaseProduzione.Stato.SALTATA),
        ).update(stato=FaseProduzione.Stato.ANNULLATA)
        ordine.unita.exclude(
            stato=UnitaProduzione.Stato.SCARTATA,
        ).update(stato=UnitaProduzione.Stato.ANNULLATA)
        ordine.fasi.all().update(
            stato_pre_sospensione="",
        )
        ImpegnoRisorsa.objects.filter(
            fase__ordine=ordine, rilasciata_il__isnull=True,
        ).update(rilasciata_il=momento)
        AssegnazioneOperatore.objects.filter(
            fase__ordine=ordine, terminato_il__isnull=True,
        ).update(terminato_il=momento)
    else:
        ordine.stato = OrdineProduzione.Stato.IN_CORSO
        if decisione == NonConformita.DecisioneFlusso.SOLO_REINTEGRATI:
            reintegrati_ids = batch_reintegrati.values_list("unita_id", flat=True)
            ordine.unita.exclude(pk__in=reintegrati_ids).filter(
                stato__in=(
                    UnitaProduzione.Stato.CREATA,
                    UnitaProduzione.Stato.IN_LAVORAZIONE,
                    UnitaProduzione.Stato.ALLERTA,
                    UnitaProduzione.Stato.QUARANTENA,
                ),
            ).update(stato=UnitaProduzione.Stato.ANNULLATA)
        for fase in ordine.fasi.filter(stato=FaseProduzione.Stato.BLOCCATA):
            nc_fase = nc_chiuse.filter(fase=fase).exclude(
                stato_fase_precedente=FaseProduzione.Stato.BLOCCATA,
            ).order_by("aperta_il").first()
            fase.stato = (
                nc_fase.stato_fase_precedente
                if nc_fase and nc_fase.stato_fase_precedente
                else FaseProduzione.Stato.IN_CORSO
            )
            fase.save(update_fields=("stato",))
    ordine.save(update_fields=("stato",))
    _evento(
        ordine, operatore, "MATRICE_NC_APPLICATA", fase=nc_decisiva.fase,
        decisione=decisione,
    )
    return decisione


@transaction.atomic
def chiudi_non_conformita(nc, esito, azione, operatore):
    nc = NonConformita.objects.select_for_update().select_related(
        "ordine", "fase", "unita", "consumo",
    ).get(pk=nc.pk)
    ordine = OrdineProduzione.objects.select_for_update().get(pk=nc.ordine_id)
    if nc.stato == NonConformita.Stato.CHIUSA:
        raise ValidationError("La non conformità è già chiusa.")
    if esito not in NonConformita.Esito.values:
        raise ValidationError("Esito della non conformità non valido.")
    azione = (azione or "").strip()
    if not azione:
        raise ValidationError("Descrivi l'azione adottata.")

    if nc.consumo_id:
        if esito == NonConformita.Esito.REINTEGRO:
            if nc.consumo.stato == ConsumoMateriale.Stato.CONSUMATO:
                reintegra_materiale(nc.consumo, operatore)
            elif nc.consumo.stato == ConsumoMateriale.Stato.PRENOTATO:
                nc.consumo.stato = ConsumoMateriale.Stato.REINTEGRATO
                nc.consumo.save(update_fields=("stato",))
        elif esito == NonConformita.Esito.SCARTO:
            scarta_materiale(nc.consumo, operatore)

    if nc.unita_id:
        if esito in (NonConformita.Esito.REINTEGRO, NonConformita.Esito.DEROGA):
            nc.unita.stato = UnitaProduzione.Stato.REINTEGRATA
        elif esito == NonConformita.Esito.SCARTO:
            nc.unita.stato = UnitaProduzione.Stato.SCARTATA
        else:
            nc.unita.stato = UnitaProduzione.Stato.ANNULLATA
        nc.unita.save(update_fields=("stato",))

    nc.stato = NonConformita.Stato.CHIUSA
    nc.esito = esito
    nc.azione = azione
    nc.chiusa_il = timezone.now()
    nc.chiusa_da = operatore
    nc.save(update_fields=("stato", "esito", "azione", "chiusa_il", "chiusa_da"))

    altre_aperte = ordine.non_conformita.exclude(pk=nc.pk).exclude(
        stato=NonConformita.Stato.CHIUSA,
    ).exists()
    if not altre_aperte:
        _applica_matrice_non_conformita(ordine, nc, operatore)
    _evento(
        ordine, operatore, "NON_CONFORMITA_CHIUSA", fase=nc.fase,
        nc_id=nc.pk, codice=nc.codice, esito=esito,
    )
    return nc


@transaction.atomic
def completa_fase(fase, operatore):
    fase = FaseProduzione.objects.select_for_update().select_related("ordine").get(pk=fase.pk)
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("Soltanto una fase in corso può essere completata.")
    obbligatori = fase.passaggio.stazione.controlli.filter(obbligatorio=True)
    rilevati = fase.rilevazioni.values_list("definizione_id", flat=True)
    if obbligatori.exclude(pk__in=rilevati).exists():
        raise ValidationError("Mancano controlli obbligatori della stazione.")
    if fase.materiali.filter(stato=ConsumoMateriale.Stato.PRENOTATO).exists():
        raise ValidationError("Sono presenti materiali prenotati non ancora consumati o scartati.")
    if fase.unita.filter(stato__in=(
        UnitaProduzione.Stato.CREATA,
        UnitaProduzione.Stato.IN_LAVORAZIONE,
        UnitaProduzione.Stato.QUARANTENA,
    )).exists():
        raise ValidationError("Sono presenti unità produttive senza un esito definitivo.")
    if fase.non_conformita.exclude(stato="CHIUSA").exists():
        raise ValidationError("La fase presenta non conformità aperte.")
    fase.stato = FaseProduzione.Stato.COMPLETATA
    fase.completata_il = timezone.now()
    fase.save(update_fields=("stato", "completata_il"))
    fase.impegni_risorse.filter(rilasciata_il__isnull=True).update(
        rilasciata_il=fase.completata_il,
    )
    fase.assegnazioni.filter(terminato_il__isnull=True).update(
        terminato_il=fase.completata_il,
    )
    _evento(fase.ordine, operatore, "FASE_COMPLETATA", fase=fase)
    ripianificate = PianificatoreDinamicoOrdine(fase.ordine).ripianifica_residue()
    if ripianificate:
        _evento(
            fase.ordine, operatore, "ORDINE_RIPIANIFICATO", fase=fase,
            causa="Completamento reale della fase",
            fasi=[
                {
                    "fase_id": elemento.pk,
                    "inizio": elemento.pianificata_inizio.isoformat(),
                    "fine": elemento.pianificata_fine.isoformat(),
                }
                for elemento in ripianificate
            ],
        )
        for ordine_successivo, fasi_successive in PianificatoreDinamicoLinea(
            fase.ordine.linea,
        ).propaga_dopo(fase.ordine):
            _evento(
                ordine_successivo, operatore, "ORDINE_RIPIANIFICATO_PER_LINEA",
                causa=f"Ritardo dell'ordine {fase.ordine.codice}",
                fasi=[
                    {
                        "fase_id": elemento.pk,
                        "inizio": elemento.pianificata_inizio.isoformat(),
                        "fine": elemento.pianificata_fine.isoformat(),
                    }
                    for elemento in fasi_successive
                ],
            )
    return fase


@transaction.atomic
def crea_unita(
    fase, tipo, codice, quantita, operatore, origine=None, quantita_origine=None,
):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "ordine", "passaggio__stazione",
    ).get(pk=fase.pk)
    tipo = TipoUnitaProduzione.objects.get(pk=tipo.pk)
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("Le unità possono essere create soltanto in una fase in corso.")
    if not tipo.attivo or tipo.stazione_id != fase.passaggio.stazione_id:
        raise ValidationError("Il tipo di unità non è disponibile per questa stazione.")
    codice = (codice or "").strip()
    if not codice:
        raise ValidationError("Il codice dell'unità è obbligatorio.")
    if tipo.richiede_quantita:
        if quantita in (None, ""):
            raise ValidationError("La quantità dell'unità è obbligatoria.")
        quantita = Decimal(str(quantita))
        if quantita < 0:
            raise ValidationError("La quantità dell'unità non può essere negativa.")
    else:
        quantita = None
    if origine is not None:
        origine = UnitaProduzione.objects.select_for_update().select_related(
            "fase__passaggio",
        ).get(pk=origine.pk)
        if origine.ordine_id != fase.ordine_id:
            raise ValidationError("L'unità di origine appartiene a un altro ordine.")
        predecessori = set(fase.predecessori().values_list("pk", flat=True))
        riversamento_roboqbo = (
            origine.fase_id == fase.pk and origine.tipo == "BATCH" and tipo.codice == "TANK"
        )
        if origine.fase_id not in predecessori and not riversamento_roboqbo:
            raise ValidationError("L'unità di origine non proviene da una stazione precedente.")
        if origine.stato not in (
            UnitaProduzione.Stato.CONFORME,
            UnitaProduzione.Stato.ALLERTA,
            UnitaProduzione.Stato.REINTEGRATA,
        ):
            raise ValidationError("L'unità di origine non è utilizzabile.")
        if quantita_origine in (None, ""):
            quantita_origine = origine.quantita_disponibile
        else:
            quantita_origine = Decimal(str(quantita_origine))
        if quantita_origine <= 0:
            raise ValidationError("Non c'è prodotto disponibile nell'unità di origine.")
        if quantita_origine > origine.quantita_disponibile:
            raise ValidationError("La quantità supera il prodotto disponibile nell'unità di origine.")
    unita = UnitaProduzione.objects.create(
        ordine=fase.ordine, fase=fase, tipo_definizione=tipo, tipo=tipo.codice,
        codice=codice, quantita=quantita, origine=origine,
        quantita_origine=quantita_origine,
    )
    if origine is not None:
        AllocazioneOrigineUnita.objects.create(
            origine=origine, destinazione=unita, quantita=quantita_origine,
        )
    _evento(
        fase.ordine, operatore, "UNITA_CREATA", fase=fase,
        unita_id=unita.pk, codice=unita.codice, tipo_unita=tipo.codice,
    )
    return unita


@transaction.atomic
def aggiungi_origine_unita(destinazione, origine, quantita, operatore):
    destinazione = UnitaProduzione.objects.select_for_update().select_related(
        "ordine", "fase",
    ).get(pk=destinazione.pk)
    origine = UnitaProduzione.objects.select_for_update().select_related("fase").get(
        pk=origine.pk,
    )
    quantita = Decimal(str(quantita))
    allocazione = AllocazioneOrigineUnita(
        origine=origine, destinazione=destinazione, quantita=quantita,
    )
    allocazione.full_clean()
    if quantita > origine.quantita_disponibile:
        raise ValidationError("La quantità supera il prodotto disponibile nell'unità di origine.")
    allocazione.save()
    if destinazione.origine_id is None:
        destinazione.origine = origine
        destinazione.quantita_origine = quantita
        destinazione.save(update_fields=("origine", "quantita_origine"))
    if destinazione.tipo == "TANK" and destinazione.fase_id == origine.fase_id:
        destinazione.quantita = destinazione.allocazioni_origine.aggregate(
            totale=models.Sum("quantita"),
        )["totale"] or Decimal("0")
        destinazione.save(update_fields=("quantita",))
    _evento(
        destinazione.ordine, operatore, "ORIGINE_UNITA_AGGIUNTA", fase=destinazione.fase,
        origine_id=origine.pk, destinazione_id=destinazione.pk, quantita=str(quantita),
    )
    return allocazione


@transaction.atomic
def apri_lotto_lavorazione(ordine, codice, operatore, note=""):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("Il lotto di lavorazione richiede un ordine in corso.")
    if ordine.lotti_lavorazione.filter(stato=LottoLavorazione.Stato.APERTO).exists():
        raise ValidationError("Esiste già un lotto di lavorazione aperto.")
    codice = (codice or "").strip()
    if not codice:
        raise ValidationError("Indica il codice temporaneo del lotto.")
    lotto = LottoLavorazione.objects.create(
        ordine=ordine, codice=codice, aperto_da=operatore, note=note,
    )
    _evento(ordine, operatore, "LOTTO_LAVORAZIONE_APERTO", codice=codice)
    return lotto


@transaction.atomic
def collega_unita_lotto(lotto, unita, operatore):
    lotto = LottoLavorazione.objects.select_for_update().get(pk=lotto.pk)
    unita = UnitaProduzione.objects.select_for_update().get(pk=unita.pk)
    if lotto.stato != LottoLavorazione.Stato.APERTO:
        raise ValidationError("Il lotto di lavorazione è già chiuso.")
    if lotto.ordine_id != unita.ordine_id:
        raise ValidationError("L'unità appartiene a un altro ordine.")
    collegamento = AppartenenzaUnitaLotto.objects.create(
        lotto_lavorazione=lotto, unita=unita,
    )
    _evento(
        lotto.ordine, operatore, "UNITA_COLLEGATA_LOTTO", fase=unita.fase,
        lotto=lotto.codice, unita_id=unita.pk,
    )
    return collegamento


@transaction.atomic
def chiudi_lotto_lavorazione(lotto, operatore):
    lotto = LottoLavorazione.objects.select_for_update().get(pk=lotto.pk)
    if lotto.stato != LottoLavorazione.Stato.APERTO:
        raise ValidationError("Il lotto di lavorazione è già chiuso.")
    lotto.stato = LottoLavorazione.Stato.CHIUSO
    lotto.chiuso_il = timezone.now()
    lotto.chiuso_da = operatore
    lotto.save(update_fields=("stato", "chiuso_il", "chiuso_da"))
    _evento(lotto.ordine, operatore, "LOTTO_LAVORAZIONE_CHIUSO", codice=lotto.codice)
    return lotto


def _prefisso_progressivo(indice):
    if indice == 0:
        return ""
    risultato = ""
    valore = indice
    while valore:
        valore, resto = divmod(valore - 1, 26)
        risultato = chr(65 + resto) + risultato
    return risultato


def proponi_codice_lotto_commerciale(giorno=None):
    giorno = giorno or timezone.localdate()
    base = giorno.strftime("%y%m%d")
    esistenti = LottoCommerciale.objects.filter(
        chiuso_il__date=giorno,
    ).count()
    return f"{_prefisso_progressivo(esistenti)}{base}"


@transaction.atomic
def chiudi_lotto_commerciale(
    ordine, lotti_lavorazione, vasetti_conformi, vasetti_scartati,
    capsule_scartate, operatore, codice=None, motivazione_eccezione="",
):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    lotti = list(LottoLavorazione.objects.select_for_update().filter(
        pk__in=[lotto.pk for lotto in lotti_lavorazione], ordine=ordine,
    ))
    if not lotti:
        raise ValidationError("Seleziona almeno un lotto temporaneo di lavorazione.")
    if any(lotto.stato != LottoLavorazione.Stato.CHIUSO for lotto in lotti):
        raise ValidationError("Prima di assegnare il lotto definitivo, chiudi i lotti temporanei selezionati.")
    vasetti_conformi = int(vasetti_conformi)
    vasetti_scartati = int(vasetti_scartati)
    capsule_scartate = int(capsule_scartate)
    eccezione = len(lotti) > 1
    if eccezione:
        if not operatore.has_perm("produzione_v2.gestire_qualita_v2"):
            raise ValidationError("L'unione richiede l'autorizzazione del responsabile qualità.")
        if not (motivazione_eccezione or "").strip():
            raise ValidationError("Motiva l'unione eccezionale di lotti temporanei diversi.")
    proposto = proponi_codice_lotto_commerciale()
    lotto = LottoCommerciale.objects.create(
        ordine=ordine, codice_proposto=proposto, codice=(codice or proposto).strip(),
        vasetti_conformi=vasetti_conformi, vasetti_scartati=vasetti_scartati,
        capsule_scartate=capsule_scartate, chiuso_da=operatore,
    )
    for origine in lotti:
        OrigineLottoCommerciale.objects.create(
            lotto_commerciale=lotto, lotto_lavorazione=origine,
            autorizzazione_eccezione=eccezione,
            motivazione_eccezione=motivazione_eccezione if eccezione else "",
            autorizzata_da=operatore if eccezione else None,
        )
    _evento(
        ordine, operatore, "LOTTO_COMMERCIALE_CHIUSO", codice=lotto.codice,
        codice_proposto=proposto, origini=[origine.codice for origine in lotti],
        vasetti_conformi=vasetti_conformi, vasetti_scartati=vasetti_scartati,
        capsule_scartate=capsule_scartate, eccezione=eccezione,
    )
    return lotto


@transaction.atomic
def registra_consuntivo_etichettatura(
    lotto_commerciale, vasetti_conformi, vasetti_scartati,
    etichette_scartate, operatore,
):
    lotto = LottoCommerciale.objects.select_for_update().get(pk=lotto_commerciale.pk)
    vasetti_conformi = int(vasetti_conformi)
    vasetti_scartati = int(vasetti_scartati)
    etichette_scartate = int(etichette_scartate)
    ricevuti = lotto.vasetti_conformi
    if vasetti_conformi + vasetti_scartati > ricevuti:
        raise ValidationError("I vasetti dichiarati superano quelli ricevuti da C.")
    consuntivo = ConsuntivoEtichettatura.objects.create(
        lotto_commerciale=lotto, vasetti_conformi=vasetti_conformi,
        vasetti_scartati=vasetti_scartati, etichette_scartate=etichette_scartate,
        registrato_da=operatore,
    )
    _evento(
        lotto.ordine, operatore, "CONSUNTIVO_ETICHETTATURA_REGISTRATO",
        lotto=lotto.codice, vasetti_conformi=vasetti_conformi,
        vasetti_scartati=vasetti_scartati,
        etichette_scartate=etichette_scartate,
        etichette_consumate=consuntivo.etichette_consumate,
    )
    return consuntivo


@transaction.atomic
def avvia_unita(unita, operatore):
    unita = UnitaProduzione.objects.select_for_update().select_related("ordine", "fase").get(pk=unita.pk)
    if unita.fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("La fase dell'unità non è in corso.")
    if unita.stato != UnitaProduzione.Stato.CREATA:
        raise ValidationError("Soltanto un'unità creata può essere avviata.")
    unita.stato = UnitaProduzione.Stato.IN_LAVORAZIONE
    unita.save(update_fields=("stato",))
    _evento(unita.ordine, operatore, "UNITA_AVVIATA", fase=unita.fase, unita_id=unita.pk)
    return unita


@transaction.atomic
def assegna_esito_unita(unita, esito, operatore):
    unita = UnitaProduzione.objects.select_for_update().select_related("ordine", "fase").get(pk=unita.pk)
    if esito not in (UnitaProduzione.Stato.CONFORME, UnitaProduzione.Stato.ALLERTA):
        raise ValidationError("Esito dell'unità non valido.")
    if unita.stato != UnitaProduzione.Stato.IN_LAVORAZIONE:
        raise ValidationError("L'unità non è in lavorazione.")
    unita.stato = esito
    unita.save(update_fields=("stato",))
    _evento(
        unita.ordine, operatore, "UNITA_VALUTATA", fase=unita.fase,
        unita_id=unita.pk, esito=esito,
    )
    return unita


@transaction.atomic
def registra_output(
    fase, articolo, codice_lotto, quantita, ubicazione, operatore,
    unita=None, scaffale="", piano="", note="",
):
    from magazzino.models import Lotto, Movimento
    from magazzino.services import registra_carico

    fase = FaseProduzione.objects.select_for_update().select_related("ordine").get(pk=fase.pk)
    if fase.stato != FaseProduzione.Stato.IN_CORSO:
        raise ValidationError("L'output può essere registrato soltanto durante una fase in corso.")
    if unita is not None:
        unita = UnitaProduzione.objects.select_for_update().get(pk=unita.pk, fase=fase)
        if unita.stato not in (
            UnitaProduzione.Stato.CONFORME,
            UnitaProduzione.Stato.ALLERTA,
            UnitaProduzione.Stato.REINTEGRATA,
        ):
            raise ValidationError("L'unità di origine non ha un esito utilizzabile.")
    quantita = Decimal(str(quantita))
    if quantita <= 0:
        raise ValidationError("La quantità prodotta deve essere maggiore di zero.")
    codice_lotto = (codice_lotto or "").strip()
    if not codice_lotto:
        raise ValidationError("Il codice lotto di produzione è obbligatorio.")
    if Lotto.objects.filter(articolo=articolo, codice_lotto__iexact=codice_lotto).exists():
        raise ValidationError("Esiste già un lotto con questo codice per l'articolo.")

    output = OutputProduzione.objects.create(
        ordine=fase.ordine, fase=fase, unita=unita, articolo=articolo,
        codice_lotto=codice_lotto, quantita=quantita, ubicazione=ubicazione,
        scaffale=(scaffale or "").strip(), piano=(piano or "").strip(),
        creato_da=operatore, note=note,
    )
    lotto = Lotto.objects.create(
        articolo=articolo, codice_lotto=codice_lotto, tipo=Lotto.Tipo.PRODUZIONE,
        data_produzione=timezone.localdate(), quantita_iniziale=quantita, note=note,
    )
    try:
        movimento = registra_carico(
            lotto=lotto, quantita=quantita, ubicazione=ubicazione,
            scaffale=output.scaffale, piano=output.piano,
            causale=f"Output produzione V2 - ordine {fase.ordine.codice}",
            note=note, operatore=operatore,
        )
    except ValueError as errore:
        raise ValidationError(str(errore)) from errore
    movimento.tipo = Movimento.Tipo.PRODUZIONE
    movimento.save(update_fields=("tipo",))
    output.lotto = lotto
    output.stato = OutputProduzione.Stato.CARICATO
    output.caricato_il = timezone.now()
    output.save(update_fields=("lotto", "stato", "caricato_il"))
    MovimentoOutput.objects.create(output=output, movimento=movimento)
    _evento(
        fase.ordine, operatore, "OUTPUT_CARICATO", fase=fase,
        output_id=output.pk, lotto=codice_lotto, quantita=str(quantita),
        movimento_id=movimento.pk,
    )
    return output


@transaction.atomic
def completa_ordine(ordine, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("L'ordine non è in corso.")
    if ordine.fasi.exclude(
        stato__in=(FaseProduzione.Stato.COMPLETATA, FaseProduzione.Stato.SALTATA),
    ).exists():
        raise ValidationError("Non tutte le fasi sono state completate.")
    if ordine.non_conformita.exclude(stato="CHIUSA").exists():
        raise ValidationError("L'ordine presenta non conformità aperte.")
    if ordine.ciclo_id and any(
        fabbisogno.quantita_residua > 0 for fabbisogno in ordine.fabbisogni.all()
    ):
        raise ValidationError("Non tutti i fabbisogni materiali risultano coperti.")
    if ordine.ciclo_id and not ordine.output.filter(
        articolo=ordine.prodotto, stato=OutputProduzione.Stato.CARICATO,
    ).exists():
        raise ValidationError("Non è stato caricato alcun output del prodotto dell'ordine.")
    if ordine.resa_fuori_specifica:
        deroga = ordine.non_conformita.filter(
            tipo=NonConformita.Tipo.RESA,
            stato=NonConformita.Stato.CHIUSA,
            esito=NonConformita.Esito.DEROGA,
        ).exists()
        if not deroga:
            nc_aperta = ordine.non_conformita.exclude(
                stato=NonConformita.Stato.CHIUSA,
            ).filter(tipo=NonConformita.Tipo.RESA).exists()
            if not nc_aperta:
                apri_non_conformita(
                    ordine,
                    f"Resa {ordine.resa_percentuale}% fuori specifica "
                    f"({ordine.resa_minima_percentuale or '—'}% - "
                    f"{ordine.resa_massima_percentuale or '—'}%).",
                    operatore, tipo=NonConformita.Tipo.RESA,
                )
            return OrdineProduzione.objects.get(pk=ordine.pk)
    ordine.stato = OrdineProduzione.Stato.COMPLETATO
    ordine.completato_il = timezone.now()
    ordine.save(update_fields=("stato", "completato_il"))
    _evento(ordine, operatore, "ORDINE_COMPLETATO")
    return ordine


@transaction.atomic
def sospendi_ordine(ordine, motivo, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("Soltanto un ordine in corso può essere sospeso.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Il motivo della sospensione è obbligatorio.")
    momento = timezone.now()
    for fase in ordine.fasi.select_for_update().filter(
        stato=FaseProduzione.Stato.IN_CORSO,
    ):
        fase.stato_pre_sospensione = fase.stato
        fase.stato = FaseProduzione.Stato.IN_ATTESA
        fase.save(update_fields=("stato", "stato_pre_sospensione"))
        fase.impegni_risorse.filter(rilasciata_il__isnull=True).update(
            rilasciata_il=momento,
        )
        fase.assegnazioni.filter(terminato_il__isnull=True).update(
            terminato_il=momento,
        )
    ordine.stato = OrdineProduzione.Stato.SOSPESO
    ordine.save(update_fields=("stato",))
    _evento(ordine, operatore, "ORDINE_SOSPESO", motivo=motivo)
    return ordine


@transaction.atomic
def riprendi_ordine(ordine, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato != OrdineProduzione.Stato.SOSPESO:
        raise ValidationError("Soltanto un ordine sospeso può essere ripreso.")
    if ordine.non_conformita.exclude(stato=NonConformita.Stato.CHIUSA).exists():
        raise ValidationError("Chiudi le non conformità prima di riprendere l'ordine.")
    ordine.stato = OrdineProduzione.Stato.IN_CORSO
    ordine.save(update_fields=("stato",))
    _evento(ordine, operatore, "ORDINE_RIPRESO")
    return ordine


@transaction.atomic
def riprendi_fase(fase, operatore):
    fase = FaseProduzione.objects.select_for_update().select_related(
        "ordine", "passaggio__stazione",
    ).get(pk=fase.pk)
    if fase.ordine.stato != OrdineProduzione.Stato.IN_CORSO:
        raise ValidationError("L'ordine non è in corso.")
    if fase.stato != FaseProduzione.Stato.IN_ATTESA:
        raise ValidationError("La fase non è in attesa di ripresa.")
    if fase.stazione.richiede_risorsa and not fase.impegni_risorse.filter(
        rilasciata_il__isnull=True,
    ).exists():
        raise ValidationError("Riassegna una risorsa produttiva prima di riprendere la fase.")
    if fase.stazione.richiede_operatore_abilitato:
        oggi = timezone.localdate()
        if not fase.assegnazioni.filter(
            terminato_il__isnull=True,
            operatore__abilitazioni_produzione_v2__stazione=fase.stazione,
            operatore__abilitazioni_produzione_v2__attiva=True,
            operatore__abilitazioni_produzione_v2__valida_dal__lte=oggi,
        ).filter(
            Q(operatore__abilitazioni_produzione_v2__valida_fino_al__isnull=True)
            | Q(operatore__abilitazioni_produzione_v2__valida_fino_al__gte=oggi)
        ).exists():
            raise ValidationError("Riassegna un operatore abilitato prima di riprendere la fase.")
    fase.stato = fase.stato_pre_sospensione or FaseProduzione.Stato.IN_CORSO
    fase.stato_pre_sospensione = ""
    fase.save(update_fields=("stato", "stato_pre_sospensione"))
    _evento(fase.ordine, operatore, "FASE_RIPRESA", fase=fase)
    return fase


@transaction.atomic
def annulla_ordine(ordine, motivo, operatore):
    ordine = OrdineProduzione.objects.select_for_update().get(pk=ordine.pk)
    if ordine.stato not in (
        OrdineProduzione.Stato.PIANIFICATO,
        OrdineProduzione.Stato.PRONTO,
        OrdineProduzione.Stato.SOSPESO,
    ):
        raise ValidationError("L'ordine deve essere pianificato, pronto o sospeso per essere annullato.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Il motivo dell'annullamento è obbligatorio.")
    if ordine.output.filter(stato=OutputProduzione.Stato.CARICATO).exists():
        raise ValidationError("L'ordine ha output già caricati: gestiscili prima dell'annullamento.")
    if ordine.materiali.filter(stato=ConsumoMateriale.Stato.CONSUMATO).exists():
        raise ValidationError("L'ordine ha materiali consumati: reintegrali o scartali prima dell'annullamento.")
    ordine.materiali.filter(stato=ConsumoMateriale.Stato.PRENOTATO).update(
        stato=ConsumoMateriale.Stato.REINTEGRATO,
    )
    momento = timezone.now()
    ordine.fasi.exclude(stato__in=(
        FaseProduzione.Stato.COMPLETATA,
        FaseProduzione.Stato.SALTATA,
    )).update(
        stato=FaseProduzione.Stato.ANNULLATA,
        completata_il=momento,
    )
    ImpegnoRisorsa.objects.filter(
        fase__ordine=ordine, rilasciata_il__isnull=True,
    ).update(rilasciata_il=momento)
    AssegnazioneOperatore.objects.filter(
        fase__ordine=ordine, terminato_il__isnull=True,
    ).update(terminato_il=momento)
    ordine.stato = OrdineProduzione.Stato.ANNULLATO
    ordine.save(update_fields=("stato",))
    _evento(ordine, operatore, "ORDINE_ANNULLATO", motivo=motivo)
    return ordine
