import hashlib
import json
from datetime import datetime, time
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max
from django.utils import timezone


class LineaProduzione(models.Model):
    codice = models.CharField(max_length=30, unique=True)
    nome = models.CharField(max_length=120)
    attiva = models.BooleanField(default=True)
    descrizione = models.TextField(blank=True)

    class Meta:
        ordering = ("codice",)

    def __str__(self):
        return f"{self.codice} - {self.nome}"

    def prima_disponibilita(self, giorno, ordine_id=None):
        inizio_giornata = timezone.make_aware(
            datetime.combine(giorno, time(hour=8)),
            timezone.get_current_timezone(),
        )
        occupazioni = FaseProduzione.objects.filter(
            ordine__linea=self,
            ordine__pianificato_per=giorno,
            pianificata_fine__isnull=False,
        ).exclude(
            ordine__stato__in=(
                OrdineProduzione.Stato.ANNULLATO,
                OrdineProduzione.Stato.ABORTITO,
            ),
        )
        if ordine_id is not None:
            occupazioni = occupazioni.exclude(ordine_id=ordine_id)
        ultima_fine = occupazioni.aggregate(ultima=Max("pianificata_fine"))["ultima"]
        return max(inizio_giornata, ultima_fine) if ultima_fine else inizio_giornata


class TurnoLinea(models.Model):
    class Giorno(models.IntegerChoices):
        LUNEDI = 0, "Lunedì"
        MARTEDI = 1, "Martedì"
        MERCOLEDI = 2, "Mercoledì"
        GIOVEDI = 3, "Giovedì"
        VENERDI = 4, "Venerdì"
        SABATO = 5, "Sabato"
        DOMENICA = 6, "Domenica"

    linea = models.ForeignKey(
        LineaProduzione, on_delete=models.PROTECT, related_name="turni",
    )
    giorno_settimana = models.PositiveSmallIntegerField(choices=Giorno.choices)
    ora_inizio = models.TimeField()
    ora_fine = models.TimeField()
    attivo = models.BooleanField(default=True)

    class Meta:
        ordering = ("linea", "giorno_settimana", "ora_inizio")
        constraints = [
            models.UniqueConstraint(
                fields=("linea", "giorno_settimana", "ora_inizio", "ora_fine"),
                name="v2_unico_turno_linea",
            ),
            models.CheckConstraint(
                condition=models.Q(ora_fine__gt=models.F("ora_inizio")),
                name="v2_turno_fine_dopo_inizio",
            ),
        ]

    def __str__(self):
        return f"{self.get_giorno_settimana_display()} {self.ora_inizio}–{self.ora_fine}"


class StazioneLavoro(models.Model):
    class Tipo(models.TextChoices):
        PREPARAZIONE = "PREPARAZIONE", "Preparazione"
        TRASFORMAZIONE = "TRASFORMAZIONE", "Trasformazione"
        CONFEZIONAMENTO = "CONFEZIONAMENTO", "Confezionamento"
        CONTROLLO = "CONTROLLO", "Controllo"
        ALTRO = "ALTRO", "Altro"

    codice = models.CharField(max_length=30, unique=True)
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    attiva = models.BooleanField(default=True)
    richiede_operatore_abilitato = models.BooleanField(default=False)
    richiede_risorsa = models.BooleanField(default=False)
    configurazione = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("codice",)

    def __str__(self):
        return f"{self.codice} - {self.nome}"


class PassaggioLinea(models.Model):
    linea = models.ForeignKey(
        LineaProduzione, on_delete=models.PROTECT, related_name="passaggi",
    )
    stazione = models.ForeignKey(
        StazioneLavoro, on_delete=models.PROTECT, related_name="passaggi_linea",
    )
    ordine = models.PositiveSmallIntegerField()
    obbligatoria = models.BooleanField(default=True)
    durata_standard_minuti = models.PositiveIntegerField(default=60)
    configurazione = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("linea", "ordine")
        constraints = [
            models.UniqueConstraint(
                fields=("linea", "ordine"), name="v2_unico_ordine_stazione_linea",
            ),
            models.UniqueConstraint(
                fields=("linea", "stazione"), name="v2_unica_stazione_linea",
            ),
            models.CheckConstraint(
                condition=models.Q(ordine__gt=0), name="v2_ordine_passaggio_positivo",
            ),
            models.CheckConstraint(
                condition=models.Q(durata_standard_minuti__gt=0),
                name="v2_durata_passaggio_positiva",
            ),
        ]


class DipendenzaPassaggio(models.Model):
    class Modalita(models.TextChoices):
        COMPLETAMENTO = "COMPLETAMENTO", "Attendi completamento"
        FLUSSO = "FLUSSO", "Avvio su prodotto disponibile"

    passaggio = models.ForeignKey(
        PassaggioLinea, on_delete=models.PROTECT, related_name="dipendenze",
    )
    predecessore = models.ForeignKey(
        PassaggioLinea, on_delete=models.PROTECT, related_name="passaggi_successivi",
    )
    modalita = models.CharField(
        max_length=15, choices=Modalita.choices, default=Modalita.COMPLETAMENTO,
    )
    quantita_minima_avvio = models.DecimalField(
        max_digits=14, decimal_places=3, default=Decimal("0"),
        help_text="Per il flusso, quantità conforme che rende avviabile la stazione.",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("passaggio", "predecessore"),
                name="v2_unica_dipendenza_passaggio",
            ),
            models.CheckConstraint(
                condition=~models.Q(passaggio=models.F("predecessore")),
                name="v2_dipendenza_passaggio_non_riflessiva",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita_minima_avvio__gte=0),
                name="v2_quantita_minima_flusso_non_negativa",
            ),
        ]

    def clean(self):
        if self.passaggio_id and self.predecessore_id:
            if self.passaggio.linea_id != self.predecessore.linea_id:
                raise ValidationError("I passaggi devono appartenere alla stessa linea.")

    def __str__(self):
        return (
            f"{self.predecessore.stazione.nome} → {self.passaggio.stazione.nome} "
            f"({self.get_modalita_display()})"
        )


class DefinizioneControllo(models.Model):
    class TipoDato(models.TextChoices):
        DECIMALE = "DECIMALE", "Numero decimale"
        INTERO = "INTERO", "Numero intero"
        BOOLEANO = "BOOLEANO", "Sì/No"
        TESTO = "TESTO", "Testo"

    stazione = models.ForeignKey(
        StazioneLavoro, on_delete=models.PROTECT, related_name="controlli",
    )
    codice = models.CharField(max_length=40)
    nome = models.CharField(max_length=120)
    tipo_dato = models.CharField(max_length=12, choices=TipoDato.choices)
    obbligatorio = models.BooleanField(default=True)
    unita_misura = models.CharField(max_length=20, blank=True)
    regole = models.JSONField(default=dict, blank=True)
    ordine = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ("stazione", "ordine", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("stazione", "codice"), name="v2_unico_controllo_stazione",
            ),
        ]


class TipoUnitaProduzione(models.Model):
    stazione = models.ForeignKey(
        StazioneLavoro, on_delete=models.PROTECT, related_name="tipi_unita",
    )
    codice = models.CharField(max_length=30)
    nome = models.CharField(max_length=100)
    unita_misura = models.CharField(max_length=10, blank=True)
    richiede_quantita = models.BooleanField(default=True)
    attivo = models.BooleanField(default=True)

    class Meta:
        ordering = ("stazione", "codice")
        constraints = [
            models.UniqueConstraint(
                fields=("stazione", "codice"), name="v2_unico_tipo_unita_stazione",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.stazione.nome})"


class CicloProduzione(models.Model):
    prodotto = models.ForeignKey(
        "magazzino.Articolo", on_delete=models.PROTECT,
        related_name="cicli_produzione_v2",
    )
    linea = models.ForeignKey(
        LineaProduzione, on_delete=models.PROTECT, related_name="cicli",
    )
    ricetta = models.ForeignKey(
        "magazzino.Ricetta", on_delete=models.PROTECT,
        related_name="cicli_produzione_v2",
    )
    versione = models.CharField(max_length=30, default="1")
    quantita_riferimento = models.DecimalField(
        max_digits=14, decimal_places=3, default=1,
        help_text="Quantità di prodotto a cui si riferiscono le quantità della ricetta.",
    )
    resa_minima_percentuale = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    resa_massima_percentuale = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("prodotto__codice", "versione")
        constraints = [
            models.UniqueConstraint(
                fields=("prodotto", "versione"), name="v2_unico_ciclo_versione_prodotto",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita_riferimento__gt=0),
                name="v2_quantita_riferimento_ciclo_positiva",
            ),
            models.CheckConstraint(
                condition=models.Q(resa_minima_percentuale__isnull=True)
                | models.Q(resa_minima_percentuale__gte=0),
                name="v2_resa_minima_non_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(resa_massima_percentuale__isnull=True)
                | models.Q(resa_massima_percentuale__gte=0),
                name="v2_resa_massima_non_negativa",
            ),
        ]

    def clean(self):
        if self.ricetta_id and self.prodotto_id and self.ricetta.articolo_id != self.prodotto_id:
            raise ValidationError("La ricetta non appartiene al prodotto del ciclo.")
        if (
            self.resa_minima_percentuale is not None
            and self.resa_massima_percentuale is not None
            and self.resa_minima_percentuale > self.resa_massima_percentuale
        ):
            raise ValidationError("La resa minima non può superare la resa massima.")

    def __str__(self):
        return f"{self.prodotto.nome_per_produzione} · {self.linea.nome} · v{self.versione}"


class RegolaControlloCiclo(models.Model):
    ciclo = models.ForeignKey(
        CicloProduzione, on_delete=models.PROTECT, related_name="regole_controllo",
    )
    definizione = models.ForeignKey(
        DefinizioneControllo, on_delete=models.PROTECT, related_name="regole_ciclo",
    )
    regole = models.JSONField(default=dict)
    attiva = models.BooleanField(default=True)

    class Meta:
        ordering = ("definizione__stazione", "definizione__ordine")
        constraints = [
            models.UniqueConstraint(
                fields=("ciclo", "definizione"),
                name="v2_unica_regola_controllo_ciclo",
            ),
        ]

    def clean(self):
        if self.ciclo_id and self.definizione_id and not self.ciclo.linea.passaggi.filter(
            stazione=self.definizione.stazione,
        ).exists():
            raise ValidationError("Il controllo non appartiene a una stazione del ciclo.")


class OrdineProduzione(models.Model):
    class Stato(models.TextChoices):
        PIANIFICATO = "PIANIFICATO", "Pianificato"
        PRONTO = "PRONTO", "Pronto"
        IN_CORSO = "IN_CORSO", "In corso"
        SOSPESO = "SOSPESO", "Sospeso"
        BLOCCATO_NC = "BLOCCATO_NC", "Bloccato per NC"
        COMPLETATO = "COMPLETATO", "Completato"
        ANNULLATO = "ANNULLATO", "Annullato"
        ABORTITO = "ABORTITO", "Abortito"

    codice = models.CharField(max_length=40, unique=True)
    linea = models.ForeignKey(
        LineaProduzione, on_delete=models.PROTECT, related_name="ordini",
    )
    prodotto = models.ForeignKey(
        "magazzino.Articolo", on_delete=models.PROTECT, related_name="ordini_produzione_v2",
    )
    ciclo = models.ForeignKey(
        CicloProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="ordini",
    )
    quantita_pianificata = models.DecimalField(max_digits=14, decimal_places=3)
    stato = models.CharField(
        max_length=15, choices=Stato.choices, default=Stato.PIANIFICATO, db_index=True,
    )
    priorita = models.PositiveSmallIntegerField(default=0)
    pianificato_per = models.DateField(null=True, blank=True)
    resa_minima_percentuale = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    resa_massima_percentuale = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
    )
    creato_il = models.DateTimeField(auto_now_add=True)
    avviato_il = models.DateTimeField(null=True, blank=True)
    completato_il = models.DateTimeField(null=True, blank=True)
    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="ordini_produzione_v2_creati",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("-priorita", "pianificato_per", "codice")
        permissions = [
            ("configurare_produzione_v2", "Può configurare linee, stazioni e cicli V2"),
            ("pianificare_produzione_v2", "Può creare e pianificare ordini V2"),
            ("operare_produzione_v2", "Può eseguire le fasi degli ordini V2"),
            ("gestire_qualita_v2", "Può aprire e chiudere non conformità V2"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantita_pianificata__gt=0),
                name="v2_quantita_ordine_positiva",
            ),
        ]

    def __str__(self):
        return self.codice

    def clean(self):
        if self.ciclo_id and self.linea_id and self.prodotto_id:
            if self.ciclo.linea_id != self.linea_id or self.ciclo.prodotto_id != self.prodotto_id:
                raise ValidationError("Linea e prodotto devono corrispondere al ciclo selezionato.")

    @property
    def avanzamento_percentuale(self):
        fasi = list(self.fasi.all())
        if not fasi:
            return 0
        concluse = sum(
            fase.stato in (FaseProduzione.Stato.COMPLETATA, FaseProduzione.Stato.SALTATA)
            for fase in fasi
        )
        return round(concluse * 100 / len(fasi))

    @property
    def fasi_eseguibili(self):
        return [fase for fase in self.fasi.all() if fase.eseguibile]

    @property
    def pianificata_inizio(self):
        inizi = [fase.pianificata_inizio for fase in self.fasi.all() if fase.pianificata_inizio]
        return min(inizi) if inizi else None

    @property
    def pianificata_fine(self):
        fini = [fase.pianificata_fine for fase in self.fasi.all() if fase.pianificata_fine]
        return max(fini) if fini else None

    @property
    def quantita_prodotta(self):
        return self.output.filter(
            articolo=self.prodotto, stato=OutputProduzione.Stato.CARICATO,
        ).aggregate(totale=models.Sum("quantita"))["totale"] or Decimal("0")

    @property
    def resa_percentuale(self):
        if not self.quantita_pianificata:
            return None
        return (self.quantita_prodotta * Decimal("100") / self.quantita_pianificata).quantize(
            Decimal("0.01"),
        )

    @property
    def resa_fuori_specifica(self):
        resa = self.resa_percentuale
        if resa is None:
            return False
        return (
            self.resa_minima_percentuale is not None and resa < self.resa_minima_percentuale
        ) or (
            self.resa_massima_percentuale is not None and resa > self.resa_massima_percentuale
        )


class FaseProduzione(models.Model):
    class Stato(models.TextChoices):
        DA_AVVIARE = "DA_AVVIARE", "Da avviare"
        IN_CORSO = "IN_CORSO", "In corso"
        IN_ATTESA = "IN_ATTESA", "In attesa"
        BLOCCATA = "BLOCCATA", "Bloccata"
        COMPLETATA = "COMPLETATA", "Completata"
        SALTATA = "SALTATA", "Saltata"
        ANNULLATA = "ANNULLATA", "Annullata"

    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="fasi",
    )
    passaggio = models.ForeignKey(
        PassaggioLinea, on_delete=models.PROTECT, related_name="fasi",
    )
    sequenza = models.PositiveSmallIntegerField()
    stato = models.CharField(
        max_length=12, choices=Stato.choices, default=Stato.DA_AVVIARE, db_index=True,
    )
    stato_pre_sospensione = models.CharField(max_length=12, blank=True)
    pianificata_inizio = models.DateTimeField(null=True, blank=True)
    pianificata_fine = models.DateTimeField(null=True, blank=True)
    iniziata_il = models.DateTimeField(null=True, blank=True)
    completata_il = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("ordine", "sequenza")
        constraints = [
            models.UniqueConstraint(
                fields=("ordine", "sequenza"), name="v2_unica_sequenza_fase_ordine",
            ),
            models.UniqueConstraint(
                fields=("ordine", "passaggio"), name="v2_unico_passaggio_fase_ordine",
            ),
        ]

    def clean(self):
        if self.passaggio_id and self.ordine_id:
            if self.passaggio.linea_id != self.ordine.linea_id:
                raise ValidationError("Il passaggio non appartiene alla linea dell'ordine.")

    @property
    def stazione(self):
        return self.passaggio.stazione

    def predecessori(self):
        passaggio_ids = list(
            self.passaggio.dipendenze.values_list("predecessore_id", flat=True)
        )
        if passaggio_ids:
            return self.ordine.fasi.filter(passaggio_id__in=passaggio_ids)
        return self.ordine.fasi.filter(sequenza__lt=self.sequenza)

    @property
    def eseguibile(self):
        if (
            not OrdineProduzione.objects.filter(
                pk=self.ordine_id, stato=OrdineProduzione.Stato.IN_CORSO,
            ).exists()
            or self.stato != self.Stato.DA_AVVIARE
        ):
            return False
        dipendenze = list(self.passaggio.dipendenze.select_related("predecessore"))
        if not dipendenze:
            return not self.predecessori().exclude(
                stato__in=(self.Stato.COMPLETATA, self.Stato.SALTATA),
            ).exists()
        fasi = {
            fase.passaggio_id: fase
            for fase in self.ordine.fasi.filter(
                passaggio_id__in=[d.predecessore_id for d in dipendenze],
            )
        }
        for dipendenza in dipendenze:
            predecessore = fasi.get(dipendenza.predecessore_id)
            if predecessore is None:
                return False
            if dipendenza.modalita == DipendenzaPassaggio.Modalita.COMPLETAMENTO:
                if predecessore.stato not in (self.Stato.COMPLETATA, self.Stato.SALTATA):
                    return False
            elif not predecessore.unita_utilizzabili_per_flusso(
                dipendenza.quantita_minima_avvio,
            ):
                return False
        return True

    def unita_utilizzabili_per_flusso(self, quantita_minima=Decimal("0")):
        soglia = Decimal(str(quantita_minima or 0))
        for unita in self.unita.filter(
            stato__in=(
                UnitaProduzione.Stato.CONFORME,
                UnitaProduzione.Stato.ALLERTA,
                UnitaProduzione.Stato.REINTEGRATA,
            ),
            quantita__isnull=False,
        ):
            disponibile = unita.quantita_disponibile
            if disponibile > 0 and (soglia == 0 or disponibile >= soglia):
                return True
        return False

    @property
    def scostamento_minuti(self):
        if not self.pianificata_fine:
            return None
        riferimento = self.completata_il
        if riferimento is None and self.stato == self.Stato.IN_CORSO:
            riferimento = timezone.now()
        if riferimento is None:
            return None
        return round((riferimento - self.pianificata_fine).total_seconds() / 60)


class AssegnazioneOperatore(models.Model):
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="assegnazioni",
    )
    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="assegnazioni_produzione_v2",
    )
    assegnato_il = models.DateTimeField(auto_now_add=True)
    terminato_il = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("fase", "operatore"), name="v2_unica_assegnazione_operatore_fase",
            ),
        ]


class AbilitazioneOperatore(models.Model):
    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="abilitazioni_produzione_v2",
    )
    stazione = models.ForeignKey(
        StazioneLavoro, on_delete=models.PROTECT, related_name="abilitazioni_operatori",
    )
    ruolo = models.CharField(max_length=80, blank=True)
    valida_dal = models.DateField(default=timezone.localdate)
    valida_fino_al = models.DateField(null=True, blank=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("stazione", "operatore__username")
        constraints = [
            models.UniqueConstraint(
                fields=("operatore", "stazione"),
                name="v2_unica_abilitazione_operatore_stazione",
            ),
        ]

    def valida_il(self, giorno=None):
        giorno = giorno or timezone.localdate()
        return (
            self.attiva
            and self.valida_dal <= giorno
            and (self.valida_fino_al is None or self.valida_fino_al >= giorno)
        )


class RisorsaProduzione(models.Model):
    class Tipo(models.TextChoices):
        MACCHINA = "MACCHINA", "Macchina"
        AREA = "AREA", "Area di lavoro"
        ATTREZZATURA = "ATTREZZATURA", "Attrezzatura"

    stazione = models.ForeignKey(
        StazioneLavoro, on_delete=models.PROTECT, related_name="risorse",
    )
    codice = models.CharField(max_length=40, unique=True)
    nome = models.CharField(max_length=120)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    capacita = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    unita_misura = models.CharField(max_length=10, blank=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("stazione", "codice")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(capacita__isnull=True) | models.Q(capacita__gt=0),
                name="v2_capacita_risorsa_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.codice} - {self.nome}"


class ImpegnoRisorsa(models.Model):
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="impegni_risorse",
    )
    risorsa = models.ForeignKey(
        RisorsaProduzione, on_delete=models.PROTECT, related_name="impegni",
    )
    impegnata_il = models.DateTimeField(auto_now_add=True)
    rilasciata_il = models.DateTimeField(null=True, blank=True)
    assegnata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="impegni_risorse_produzione_v2",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("fase", "risorsa"), name="v2_unico_impegno_risorsa_fase",
            ),
        ]


class UnitaProduzione(models.Model):
    class Stato(models.TextChoices):
        CREATA = "CREATA", "Creata"
        IN_LAVORAZIONE = "IN_LAVORAZIONE", "In lavorazione"
        CONFORME = "CONFORME", "Conforme"
        ALLERTA = "ALLERTA", "In allerta"
        QUARANTENA = "QUARANTENA", "In quarantena"
        REINTEGRATA = "REINTEGRATA", "Reintegrata"
        SCARTATA = "SCARTATA", "Scartata"
        ANNULLATA = "ANNULLATA", "Annullata"

    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="unita",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="unita",
    )
    tipo_definizione = models.ForeignKey(
        TipoUnitaProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="unita",
    )
    tipo = models.CharField(max_length=30)
    codice = models.CharField(max_length=50)
    quantita = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    quantita_origine = models.DecimalField(
        max_digits=14, decimal_places=3, null=True, blank=True,
        help_text="Quantità prelevata dall'unità della stazione precedente.",
    )
    stato = models.CharField(max_length=15, choices=Stato.choices, default=Stato.CREATA)
    origine = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="derivate",
    )
    metadati = models.JSONField(default=dict, blank=True)
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("ordine", "codice"), name="v2_unico_codice_unita_ordine",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita__isnull=True) | models.Q(quantita__gte=0),
                name="v2_quantita_unita_non_negativa",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita_origine__isnull=True) | models.Q(quantita_origine__gt=0),
                name="v2_quantita_origine_unita_positiva",
            ),
        ]

    def clean(self):
        if self.fase_id and self.ordine_id and self.fase.ordine_id != self.ordine_id:
            raise ValidationError("La fase non appartiene all'ordine dell'unità.")
        if self.tipo_definizione_id and self.fase_id:
            if self.tipo_definizione.stazione_id != self.fase.passaggio.stazione_id:
                raise ValidationError("Il tipo di unità non appartiene alla stazione della fase.")

    def __str__(self):
        quantita = f" · {self.quantita}" if self.quantita is not None else ""
        return f"{self.codice}{quantita} · {self.get_stato_display()}"

    @property
    def quantita_trasferita(self):
        da_allocazioni = self.allocazioni_come_origine.exclude(
            destinazione__stato=self.Stato.ANNULLATA,
        ).aggregate(totale=models.Sum("quantita"))["totale"] or Decimal("0")
        destinazioni_allocate = self.allocazioni_come_origine.values_list(
            "destinazione_id", flat=True,
        )
        legacy = self.derivate.exclude(
            stato=self.Stato.ANNULLATA,
        ).exclude(pk__in=destinazioni_allocate).aggregate(
            totale=models.Sum("quantita_origine"),
        )["totale"] or Decimal("0")
        return da_allocazioni + legacy

    @property
    def quantita_disponibile(self):
        if self.quantita is None:
            return Decimal("0")
        return max(Decimal("0"), self.quantita - self.quantita_trasferita)


class AllocazioneOrigineUnita(models.Model):
    origine = models.ForeignKey(
        UnitaProduzione, on_delete=models.PROTECT, related_name="allocazioni_come_origine",
    )
    destinazione = models.ForeignKey(
        UnitaProduzione, on_delete=models.PROTECT, related_name="allocazioni_origine",
    )
    quantita = models.DecimalField(max_digits=14, decimal_places=3)
    creata_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("destinazione", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("origine", "destinazione"), name="v2_unica_allocazione_origine_unita",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita__gt=0), name="v2_quantita_allocazione_positiva",
            ),
            models.CheckConstraint(
                condition=~models.Q(origine=models.F("destinazione")),
                name="v2_allocazione_unita_non_riflessiva",
            ),
        ]

    def clean(self):
        if self.origine_id and self.destinazione_id:
            if self.origine.ordine_id != self.destinazione.ordine_id:
                raise ValidationError("Origine e destinazione devono appartenere allo stesso ordine.")
            stesso_riversamento_roboqbo = (
                self.origine.fase_id == self.destinazione.fase_id
                and self.origine.tipo == "BATCH"
                and self.destinazione.tipo == "TANK"
            )
            if (
                self.origine.fase.sequenza >= self.destinazione.fase.sequenza
                and not stesso_riversamento_roboqbo
            ):
                raise ValidationError("L'origine deve precedere la destinazione nel flusso.")

    def __str__(self):
        return f"{self.origine.codice} → {self.destinazione.codice}: {self.quantita}"


class LottoLavorazione(models.Model):
    class Stato(models.TextChoices):
        APERTO = "APERTO", "Aperto"
        CHIUSO = "CHIUSO", "Chiuso"

    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="lotti_lavorazione",
    )
    codice = models.CharField(max_length=50)
    stato = models.CharField(max_length=8, choices=Stato.choices, default=Stato.APERTO)
    aperto_il = models.DateTimeField(auto_now_add=True)
    chiuso_il = models.DateTimeField(null=True, blank=True)
    aperto_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="lotti_lavorazione_v2_aperti",
    )
    chiuso_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="lotti_lavorazione_v2_chiusi",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("ordine", "aperto_il")
        constraints = [
            models.UniqueConstraint(
                fields=("ordine", "codice"), name="v2_unico_lotto_lavorazione_ordine",
            ),
        ]

    def __str__(self):
        return self.codice


class AppartenenzaUnitaLotto(models.Model):
    lotto_lavorazione = models.ForeignKey(
        LottoLavorazione, on_delete=models.PROTECT, related_name="unita_collegate",
    )
    unita = models.OneToOneField(
        UnitaProduzione, on_delete=models.PROTECT, related_name="appartenenza_lotto",
    )


class LottoCommerciale(models.Model):
    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="lotti_commerciali",
    )
    codice_proposto = models.CharField(max_length=50)
    codice = models.CharField(max_length=50)
    vasetti_conformi = models.PositiveIntegerField(default=0)
    vasetti_scartati = models.PositiveIntegerField(default=0)
    capsule_scartate = models.PositiveIntegerField(default=0)
    chiuso_il = models.DateTimeField(default=timezone.now)
    chiuso_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="lotti_commerciali_v2_chiusi",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("chiuso_il", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("ordine", "codice"), name="v2_unico_lotto_commerciale_ordine",
            ),
        ]

    @property
    def vasetti_consumati(self):
        return self.vasetti_conformi + self.vasetti_scartati

    @property
    def capsule_consumate(self):
        return self.vasetti_conformi + self.vasetti_scartati + self.capsule_scartate

    def __str__(self):
        return self.codice


class OrigineLottoCommerciale(models.Model):
    lotto_commerciale = models.ForeignKey(
        LottoCommerciale, on_delete=models.PROTECT, related_name="origini_lavorazione",
    )
    lotto_lavorazione = models.ForeignKey(
        LottoLavorazione, on_delete=models.PROTECT, related_name="destinazioni_commerciali",
    )
    autorizzazione_eccezione = models.BooleanField(default=False)
    motivazione_eccezione = models.TextField(blank=True)
    autorizzata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="unioni_lotti_v2_autorizzate",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("lotto_commerciale", "lotto_lavorazione"),
                name="v2_unica_origine_lotto_commerciale",
            ),
        ]


class ConsuntivoEtichettatura(models.Model):
    lotto_commerciale = models.OneToOneField(
        LottoCommerciale, on_delete=models.PROTECT, related_name="consuntivo_etichettatura",
    )
    vasetti_conformi = models.PositiveIntegerField()
    vasetti_scartati = models.PositiveIntegerField(default=0)
    etichette_scartate = models.PositiveIntegerField(default=0)
    registrato_il = models.DateTimeField(auto_now_add=True)
    registrato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="consuntivi_etichettatura_v2",
    )

    @property
    def etichette_consumate(self):
        return self.vasetti_conformi + self.vasetti_scartati + self.etichette_scartate


class RilevazioneControllo(models.Model):
    class Esito(models.TextChoices):
        CONFORME = "CONFORME", "Conforme"
        ALLERTA = "ALLERTA", "Allerta"
        NON_CONFORME = "NON_CONFORME", "Non conforme"
        NON_APPLICABILE = "NON_APPLICABILE", "Non applicabile"

    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="rilevazioni",
    )
    unita = models.ForeignKey(
        UnitaProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="rilevazioni",
    )
    definizione = models.ForeignKey(
        DefinizioneControllo, on_delete=models.PROTECT, related_name="rilevazioni",
    )
    valore = models.JSONField()
    regole_applicate = models.JSONField(default=dict, blank=True)
    esito = models.CharField(max_length=17, choices=Esito.choices)
    rilevato_il = models.DateTimeField(auto_now_add=True)
    rilevato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="controlli_produzione_v2",
    )
    note = models.TextField(blank=True)

    def clean(self):
        if self.definizione_id and self.fase_id:
            if self.definizione.stazione_id != self.fase.passaggio.stazione_id:
                raise ValidationError("Il controllo non appartiene alla stazione della fase.")
        if self.unita_id and self.unita.fase_id != self.fase_id:
            raise ValidationError("L'unità non appartiene alla fase del controllo.")


class ConsumoMateriale(models.Model):
    class Stato(models.TextChoices):
        PRENOTATO = "PRENOTATO", "Prenotato"
        PRELEVATO = "PRELEVATO", "Prelevato"
        CONSUMATO = "CONSUMATO", "Consumato"
        REINTEGRATO = "REINTEGRATO", "Reintegrato"
        SCARTATO = "SCARTATO", "Scartato"

    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="materiali",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="materiali",
    )
    articolo = models.ForeignKey(
        "magazzino.Articolo", on_delete=models.PROTECT,
        related_name="consumi_produzione_v2",
    )
    lotto = models.ForeignKey(
        "magazzino.Lotto", on_delete=models.PROTECT, null=True, blank=True,
        related_name="consumi_produzione_v2",
    )
    giacenza = models.ForeignKey(
        "magazzino.Giacenza", on_delete=models.PROTECT, null=True, blank=True,
        related_name="impegni_produzione_v2",
    )
    ubicazione = models.ForeignKey(
        "magazzino.Ubicazione", on_delete=models.PROTECT, null=True, blank=True,
        related_name="consumi_produzione_v2",
    )
    quantita = models.DecimalField(max_digits=14, decimal_places=6)
    scaffale = models.CharField(max_length=30, blank=True)
    piano = models.CharField(max_length=30, blank=True)
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.PRENOTATO)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantita__gt=0), name="v2_quantita_materiale_positiva",
            ),
        ]

    def clean(self):
        if self.fase_id and self.ordine_id and self.fase.ordine_id != self.ordine_id:
            raise ValidationError("La fase non appartiene all'ordine del consumo.")
        if self.lotto_id and self.articolo_id and self.lotto.articolo_id != self.articolo_id:
            raise ValidationError("Il lotto non appartiene all'articolo selezionato.")
        if self.giacenza_id:
            if self.giacenza.lotto_id != self.lotto_id:
                raise ValidationError("La posizione non appartiene al lotto selezionato.")
            if self.giacenza.ubicazione_id != self.ubicazione_id:
                raise ValidationError("La posizione non appartiene all'ubicazione selezionata.")


class FabbisognoMateriale(models.Model):
    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="fabbisogni",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="fabbisogni",
    )
    articolo = models.ForeignKey(
        "magazzino.Articolo", on_delete=models.PROTECT,
        related_name="fabbisogni_produzione_v2",
    )
    quantita_prevista = models.DecimalField(max_digits=14, decimal_places=6)
    unita_misura = models.CharField(max_length=5)
    origine_ricetta = models.ForeignKey(
        "magazzino.RigaRicetta", on_delete=models.PROTECT,
        related_name="fabbisogni_produzione_v2",
    )
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("ordine", "articolo"), name="v2_unico_fabbisogno_articolo_ordine",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita_prevista__gt=0),
                name="v2_quantita_fabbisogno_positiva",
            ),
        ]

    @property
    def quantita_impegnata(self):
        return self.ordine.materiali.filter(
            articolo=self.articolo,
            stato__in=(
                ConsumoMateriale.Stato.PRENOTATO,
                ConsumoMateriale.Stato.CONSUMATO,
                ConsumoMateriale.Stato.SCARTATO,
            ),
        ).aggregate(totale=models.Sum("quantita"))["totale"] or Decimal("0")

    @property
    def quantita_residua(self):
        return max(self.quantita_prevista - self.quantita_impegnata, Decimal("0"))


class MovimentoProduzione(models.Model):
    consumo = models.ForeignKey(
        ConsumoMateriale, on_delete=models.PROTECT, related_name="collegamenti_movimento",
    )
    movimento = models.OneToOneField(
        "magazzino.Movimento", on_delete=models.PROTECT,
        related_name="collegamento_produzione_v2",
    )
    causale = models.CharField(max_length=30)
    creato_il = models.DateTimeField(auto_now_add=True)


class OutputProduzione(models.Model):
    class Stato(models.TextChoices):
        DICHIARATO = "DICHIARATO", "Dichiarato"
        CARICATO = "CARICATO", "Caricato in magazzino"
        ANNULLATO = "ANNULLATO", "Annullato"

    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="output",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, related_name="output",
    )
    unita = models.ForeignKey(
        UnitaProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="output",
    )
    articolo = models.ForeignKey(
        "magazzino.Articolo", on_delete=models.PROTECT,
        related_name="output_produzione_v2",
    )
    codice_lotto = models.CharField(max_length=50)
    quantita = models.DecimalField(max_digits=14, decimal_places=6)
    ubicazione = models.ForeignKey(
        "magazzino.Ubicazione", on_delete=models.PROTECT,
        related_name="output_produzione_v2",
    )
    scaffale = models.CharField(max_length=30, blank=True)
    piano = models.CharField(max_length=30, blank=True)
    lotto = models.OneToOneField(
        "magazzino.Lotto", on_delete=models.PROTECT, null=True, blank=True,
        related_name="output_produzione_v2",
    )
    stato = models.CharField(max_length=10, choices=Stato.choices, default=Stato.DICHIARATO)
    creato_il = models.DateTimeField(auto_now_add=True)
    caricato_il = models.DateTimeField(null=True, blank=True)
    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="output_produzione_v2_creati",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("creato_il", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("articolo", "codice_lotto"), name="v2_unico_output_lotto_articolo",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita__gt=0), name="v2_quantita_output_positiva",
            ),
        ]

    def clean(self):
        if self.fase_id and self.ordine_id and self.fase.ordine_id != self.ordine_id:
            raise ValidationError("La fase non appartiene all'ordine dell'output.")
        if self.unita_id and self.unita.fase_id != self.fase_id:
            raise ValidationError("L'unità non appartiene alla fase dell'output.")


class MovimentoOutput(models.Model):
    output = models.ForeignKey(
        OutputProduzione, on_delete=models.PROTECT, related_name="collegamenti_movimento",
    )
    movimento = models.OneToOneField(
        "magazzino.Movimento", on_delete=models.PROTECT,
        related_name="collegamento_output_produzione_v2",
    )
    creato_il = models.DateTimeField(auto_now_add=True)


class NonConformita(models.Model):
    class Tipo(models.TextChoices):
        QUALITA = "QUALITA", "Controllo qualità"
        UNITA = "UNITA", "Unità produttiva"
        MATERIALE = "MATERIALE", "Materiale"
        RESA = "RESA", "Resa produttiva"
        ALTRO = "ALTRO", "Altro"

    class Stato(models.TextChoices):
        APERTA = "APERTA", "Aperta"
        IN_GESTIONE = "IN_GESTIONE", "In gestione"
        CHIUSA = "CHIUSA", "Chiusa"

    class Esito(models.TextChoices):
        REINTEGRO = "REINTEGRO", "Reintegro"
        SCARTO = "SCARTO", "Scarto"
        DEROGA = "DEROGA", "Deroga"
        ANNULLAMENTO = "ANNULLAMENTO", "Annullamento"

    class DecisioneFlusso(models.TextChoices):
        PROSEGUE_TUTTI = "PROSEGUE_TUTTI", "Prosegue con tutti i batch"
        SENZA_SCARTATI = "SENZA_SCARTATI", "Prosegue senza i batch scartati"
        SOLO_REINTEGRATI = "SOLO_REINTEGRATI", "Prosegue solo con i batch reintegrati"
        PRODUZIONE_ABORTITA = "PRODUZIONE_ABORTITA", "Produzione abortita"

    codice = models.CharField(max_length=50, unique=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.ALTRO)
    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="non_conformita",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="non_conformita",
    )
    unita = models.ForeignKey(
        UnitaProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="non_conformita",
    )
    consumo = models.ForeignKey(
        ConsumoMateriale, on_delete=models.PROTECT, null=True, blank=True,
        related_name="non_conformita",
    )
    rilevazione = models.ForeignKey(
        RilevazioneControllo, on_delete=models.PROTECT, null=True, blank=True,
        related_name="non_conformita",
    )
    stato = models.CharField(max_length=12, choices=Stato.choices, default=Stato.APERTA)
    motivo = models.TextField()
    esito = models.CharField(max_length=12, choices=Esito.choices, blank=True)
    azione = models.TextField(blank=True)
    decisione_flusso = models.CharField(
        max_length=21, choices=DecisioneFlusso.choices, blank=True,
    )
    stato_ordine_precedente = models.CharField(max_length=15, blank=True)
    stato_fase_precedente = models.CharField(max_length=12, blank=True)
    stato_unita_precedente = models.CharField(max_length=15, blank=True)
    aperta_il = models.DateTimeField(auto_now_add=True)
    chiusa_il = models.DateTimeField(null=True, blank=True)
    aperta_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="nc_produzione_v2_aperte",
    )
    chiusa_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="nc_produzione_v2_chiuse",
    )

    def clean(self):
        for oggetto in (self.fase, self.unita, self.consumo):
            if oggetto is not None and oggetto.ordine_id != self.ordine_id:
                raise ValidationError("Tutti gli elementi della NC devono appartenere allo stesso ordine.")
        if self.rilevazione_id and self.rilevazione.fase.ordine_id != self.ordine_id:
            raise ValidationError("La rilevazione della NC non appartiene allo stesso ordine.")


class EventoProduzione(models.Model):
    ordine = models.ForeignKey(
        OrdineProduzione, on_delete=models.PROTECT, related_name="eventi",
    )
    fase = models.ForeignKey(
        FaseProduzione, on_delete=models.PROTECT, null=True, blank=True,
        related_name="eventi",
    )
    tipo = models.CharField(max_length=40)
    dati = models.JSONField(default=dict, blank=True)
    registrato_il = models.DateTimeField(default=timezone.now, editable=False)
    hash_precedente = models.CharField(max_length=64, blank=True)
    hash_evento = models.CharField(max_length=64, blank=True, db_index=True)
    operatore = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventi_produzione_v2",
    )

    class Meta:
        ordering = ("registrato_il", "id")

    @classmethod
    def registra(cls, ordine, operatore, tipo, fase=None, dati=None):
        precedente = cls.objects.filter(ordine=ordine).order_by("-id").first()
        evento = cls(
            ordine=ordine, fase=fase, tipo=tipo, dati=dati or {}, operatore=operatore,
            hash_precedente=precedente.hash_evento if precedente else "",
        )
        evento.save()
        return evento

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Il registro eventi è immutabile.")
        if not self.registrato_il:
            self.registrato_il = timezone.now()
        if not self.hash_evento:
            self.hash_evento = self.calcola_hash()
        return super().save(*args, **kwargs)

    def calcola_hash(self):
        contenuto = {
            "ordine_id": self.ordine_id,
            "fase_id": self.fase_id,
            "tipo": self.tipo,
            "dati": self.dati,
            "registrato_il": self.registrato_il.isoformat(),
            "operatore_id": self.operatore_id,
            "hash_precedente": self.hash_precedente,
        }
        serializzato = json.dumps(
            contenuto, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        )
        return hashlib.sha256(serializzato.encode("utf-8")).hexdigest()

    @classmethod
    def verifica_catena(cls, ordine):
        precedente = ""
        numero = 0
        for evento in cls.objects.filter(ordine=ordine).order_by("registrato_il", "id"):
            numero += 1
            if evento.hash_precedente != precedente or evento.hash_evento != evento.calcola_hash():
                return False, numero
            precedente = evento.hash_evento
        return True, numero
