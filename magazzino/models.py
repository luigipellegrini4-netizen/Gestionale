from django.conf import settings
from django.db import models
from decimal import Decimal
import uuid


class Articolo(models.Model):

    class Categoria(models.TextChoices):
        MATERIA_PRIMA = "MATERIA_PRIMA", "Materia prima"
        MOCA = "MOCA", "MOCA"
        IGIENE = "IGIENE", "Igiene"
        SEMILAVORATO = "SEMILAVORATO", "Semilavorato"
        PACKAGING = "PACKAGING", "Packaging"
        CONSUMABILI = "CONSUMABILI", "Consumabili"
        RICAMBI = "RICAMBI", "Ricambi"
        PRODOTTO_FINITO = "PRODOTTO_FINITO", "Prodotto finito"

    class UnitaMisura(models.TextChoices):
        KG = "KG", "Kilogrammi"
        L = "L", "Litri"
        PZ = "PZ", "Pezzi"

    class TipoPackaging(models.TextChoices):
        ETICHETTA = "ETICHETTA", "Etichetta"
        SCATOLA = "SCATOLA", "Scatola"
        COFANETTO = "COFANETTO", "Cofanetto"
        ALTRO = "ALTRO", "Altro"

    tipo_packaging = models.CharField(
        max_length=20,
        choices=TipoPackaging.choices,
        blank=True,
    )

    codice = models.CharField(
        max_length=30,
        unique=True,
    )

    descrizione = models.CharField(
        max_length=200,
    )

    nome_produzione = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nome semplice mostrato nelle ricette e nelle produzioni.",
    )

    categoria = models.CharField(
        max_length=25,
        choices=Categoria.choices,
    )

    unita_misura = models.CharField(
        max_length=5,
        choices=UnitaMisura.choices,
    )

    scorta_minima = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
    )

    attivo = models.BooleanField(
        default=True,
    )

    tracciabilita_lotto = models.BooleanField(
        default=True,
        help_text="Se disattivata, MIRA genera un riferimento interno senza chiedere il lotto.",
    )

    note = models.TextField(
        blank=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(scorta_minima__gte=0),
                name="articolo_scorta_minima_non_negativa",
            ),
        ]

    def __str__(self):
        return f"{self.codice} - {self.descrizione}"

    @property
    def nome_per_produzione(self):
        return self.nome_produzione or self.descrizione

class Fornitore(models.Model):

    codice = models.CharField(
        max_length=30,
        unique=True,
    )

    ragione_sociale = models.CharField(
        max_length=200,
    )

    partita_iva = models.CharField(
        max_length=20,
        blank=True,
    )

    telefono = models.CharField(
        max_length=50,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    indirizzo = models.CharField(
        max_length=250,
        blank=True,
    )

    attivo = models.BooleanField(
        default=True,
    )

    note = models.TextField(
        blank=True,
    )

    def __str__(self):
        return f"{self.codice} - {self.ragione_sociale}"


class Ubicazione(models.Model):

    class TipoMagazzino(models.TextChoices):
        MP = "MP", "Materie prime"
        IGIENE = "IGIENE", "Igiene"
        MOCA = "MOCA", "MOCA"
        SEMILAVORATI = "SEMILAVORATI", "Semilavorati"
        PRODUZIONE = "PRODUZIONE", "Produzione"
        PACKAGING = "PACKAGING", "Packaging"
        PRODOTTI_FINITI = "PRODOTTI_FINITI", "Prodotti finiti"

    nome = models.CharField(
        max_length=100,
        unique=True,
    )

    tipo_magazzino = models.CharField(
        max_length=20,
        choices=TipoMagazzino.choices,
    )

    attiva = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.nome

class Lotto(models.Model):

    class Tipo(models.TextChoices):
        ACQUISTO = "ACQUISTO", "Acquisto"
        PRODUZIONE = "PRODUZIONE", "Produzione"

    class Fase(models.TextChoices):
        NON_APPLICABILE = "", "Non applicabile"
        INVASETTATO = "INVASETTATO", "Invasettato"
        ETICHETTATO = "ETICHETTATO", "Etichettato"
        INSCATOLATO = "INSCATOLATO", "Inscatolato"

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="lotti",
    )

    codice_lotto = models.CharField(
        max_length=50,
    )

    tipo = models.CharField(
        max_length=15,
        choices=Tipo.choices,
    )

    fase = models.CharField(
        max_length=20,
        choices=Fase.choices,
        blank=True,
        default=Fase.NON_APPLICABILE,
    )

    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.PROTECT,
        related_name="lotti",
        null=True,
        blank=True,
    )

    data_arrivo = models.DateField(
        null=True,
        blank=True,
    )

    data_produzione = models.DateField(
        null=True,
        blank=True,
    )

    data_scadenza = models.DateField(
        null=True,
        blank=True,
    )

    quantita_iniziale = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    fattura = models.CharField(max_length=100, blank=True)

    ddt = models.CharField("DDT", max_length=100, blank=True)

    numero_colli = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    unita_acquisto_per_collo = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    peso_unita_acquisto = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )

    capacita_imballo = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Numero di prodotti contenuti nella singola scatola o cofanetto.",
    )

    note = models.TextField(
        blank=True,
    )

    @property
    def numero_unita_acquisto_totali(self):
        if self.numero_colli and self.unita_acquisto_per_collo:
            return self.numero_colli * self.unita_acquisto_per_collo
        return None

    @property
    def quantita_singola_uda(self):
        if self.peso_unita_acquisto:
            return self.peso_unita_acquisto
        if self.articolo.unita_misura == Articolo.UnitaMisura.PZ:
            return Decimal("1")
        return None

    @property
    def codice_visualizzato(self):
        if not self.articolo.tracciabilita_lotto:
            return "Non tracciato"
        return self.codice_lotto

    def __str__(self):
        return f"{self.articolo.codice} - {self.codice_visualizzato}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["articolo", "codice_lotto"],
                name="unico_lotto_per_articolo",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita_iniziale__gt=0),
                name="lotto_quantita_iniziale_positiva",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(numero_colli__isnull=True)
                    | models.Q(numero_colli__gt=0)
                ),
                name="lotto_numero_colli_positivo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(unita_acquisto_per_collo__isnull=True)
                    | models.Q(unita_acquisto_per_collo__gt=0)
                ),
                name="lotto_uda_per_collo_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(peso_unita_acquisto__isnull=True)
                    | models.Q(peso_unita_acquisto__gt=0)
                ),
                name="lotto_peso_uda_positivo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(capacita_imballo__isnull=True)
                    | models.Q(capacita_imballo__gt=0)
                ),
                name="lotto_capacita_imballo_positiva",
            ),
        ]


class Giacenza(models.Model):

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="giacenze",
    )

    ubicazione = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="giacenze",
    )

    quantita = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0,
    )

    scaffale = models.CharField(max_length=30, blank=True)
    piano = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lotto", "ubicazione", "scaffale", "piano"],
                name="unica_giacenza_lotto_ubicazione",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita__gte=0),
                name="giacenza_quantita_non_negativa",
            ),
        ]

    def __str__(self):
        return f"{self.lotto} - {self.ubicazione}: {self.quantita}"


class Movimento(models.Model):

    class Tipo(models.TextChoices):
        CARICO = "CARICO", "Carico"
        TRASFERIMENTO = "TRASFERIMENTO", "Trasferimento"
        CONSUMO = "CONSUMO", "Consumo"
        PRODUZIONE = "PRODUZIONE", "Produzione"
        PACKAGING = "PACKAGING", "Packaging"
        RICONFEZIONAMENTO = "RICONFEZIONAMENTO", "Riconfezionamento"
        VENDITA = "VENDITA", "Vendita"
        RETTIFICA = "RETTIFICA", "Rettifica"
        QUARANTENA = "QUARANTENA", "Quarantena per non conformità"
        REINTEGRO = "REINTEGRO", "Reintegro da quarantena"
        SCARTO_NC = "SCARTO_NC", "Scarto per non conformità"

    data_ora = models.DateTimeField(
        auto_now_add=True,
    )

    tipo = models.CharField(
        max_length=25,
        choices=Tipo.choices,
    )

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="movimenti",
    )

    quantita = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    ubicazione_origine = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="movimenti_origine",
        null=True,
        blank=True,
    )

    ubicazione_destinazione = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="movimenti_destinazione",
        null=True,
        blank=True,
    )

    causale = models.CharField(
        max_length=200,
        blank=True,
    )

    note = models.TextField(
        blank=True,
    )

    scaffale_origine = models.CharField(max_length=30, blank=True)
    piano_origine = models.CharField(max_length=30, blank=True)
    scaffale_destinazione = models.CharField(max_length=30, blank=True)
    piano_destinazione = models.CharField(max_length=30, blank=True)

    eseguito_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="movimenti_magazzino",
        null=True,
        blank=True,
    )

    class Meta:
        permissions = [
            (
                "operare_magazzino",
                "Può eseguire operazioni e modifiche di magazzino",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantita__gt=0),
                name="movimento_quantita_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.data_ora:%Y-%m-%d %H:%M} - {self.tipo} - {self.lotto}"


class NonConformitaLotto(models.Model):
    class UnitaQuarantena(models.TextChoices):
        UDA = "UDA", "UDA"
        KG = "KG", "kg"

    class Stato(models.TextChoices):
        APERTA = "APERTA", "Aperta"
        IN_LAVORAZIONE = "IN_LAVORAZIONE", "In lavorazione"
        CHIUSA = "CHIUSA", "Chiusa"

    class Ambito(models.TextChoices):
        PRODUZIONE = "PRODUZIONE", "Produzione"
        COMMERCIALE = "COMMERCIALE", "Commerciale"

    class Tipo(models.TextChoices):
        RECLAMO_CLIENTE = "RECLAMO_CLIENTE", "Reclamo del Cliente"
        VERSO_FORNITORE = "VERSO_FORNITORE", "Verso fornitore"
        INTERNO = "INTERNO", "Interno (Processo/Prodotto)"
        STRUTTURALE = "STRUTTURALE", "Strutturale"
        ALTRO = "ALTRO", "Altro"

    class EsitoEfficacia(models.TextChoices):
        EFFICACE = "EFFICACE", "Efficace"
        NON_EFFICACE = "NON_EFFICACE", "Non efficace"
        NON_APPLICABILE = "NON_APPLICABILE", "Non applicabile"

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="non_conformita",
        null=True,
        blank=True,
    )
    produzione = models.ForeignKey(
        "Produzione",
        on_delete=models.PROTECT,
        related_name="non_conformita",
        null=True,
        blank=True,
    )
    batch = models.OneToOneField(
        "BatchProduzione",
        on_delete=models.PROTECT,
        related_name="non_conformita",
        null=True,
        blank=True,
    )
    lotto_temporaneo = models.CharField(max_length=50, blank=True)
    produzione_puo_proseguire = models.BooleanField(null=True, blank=True)
    numero_batch_origine = models.PositiveSmallIntegerField(null=True, blank=True)
    stato = models.CharField(
        max_length=20,
        choices=Stato.choices,
        default=Stato.APERTA,
        db_index=True,
    )
    ambito = models.CharField(
        max_length=15,
        choices=Ambito.choices,
        default=Ambito.PRODUZIONE,
        db_index=True,
    )
    tipo_nc = models.CharField(
        max_length=25,
        choices=Tipo.choices,
        default=Tipo.INTERNO,
        db_index=True,
    )
    ubicazione_origine = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="non_conformita_lotti",
        null=True,
        blank=True,
    )
    scaffale_origine = models.CharField(max_length=30, blank=True)
    piano_origine = models.CharField(max_length=30, blank=True)
    numero_uda_quarantena = models.PositiveIntegerField(null=True, blank=True)
    quantita_quarantena = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    quantita_per_uda = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    unita_quarantena = models.CharField(
        max_length=5, choices=UnitaQuarantena.choices, blank=True,
    )
    motivo = models.TextField()
    note_apertura = models.TextField(blank=True)
    aperta_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="non_conformita_aperte",
    )
    data_apertura = models.DateTimeField(auto_now_add=True)
    numero_uda_scartate = models.PositiveIntegerField(null=True, blank=True)
    numero_uda_reintegrate = models.PositiveIntegerField(null=True, blank=True)
    quantita_scartata = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    quantita_reintegrata = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    decisione = models.TextField(blank=True)
    gestita_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="non_conformita_gestite",
        null=True,
        blank=True,
    )
    data_chiusura = models.DateTimeField(null=True, blank=True)
    analisi_cause = models.TextField(blank=True)
    azione_risoluzione = models.TextField(blank=True)
    responsabile_azione = models.CharField(max_length=200, blank=True)
    data_inizio_gestione = models.DateField(null=True, blank=True)
    azione_immediata = models.BooleanField(default=False)
    scadenza_prevista = models.DateField(null=True, blank=True)
    esito_efficacia = models.CharField(
        max_length=20,
        choices=EsitoEfficacia.choices,
        blank=True,
    )
    verifica_efficacia = models.TextField(blank=True)
    data_verifica = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ("-data_apertura", "-id")
        permissions = [
            (
                "gestire_non_conformita",
                "Può decidere scarto e reintegro delle non conformità",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(numero_uda_quarantena__isnull=True) | models.Q(numero_uda_quarantena__gt=0)),
                name="nc_numero_uda_quarantena_positivo",
            ),
            models.CheckConstraint(
                condition=(models.Q(quantita_quarantena__isnull=True) | models.Q(quantita_quarantena__gt=0)),
                name="nc_quantita_quarantena_positiva",
            ),
            models.CheckConstraint(
                condition=(models.Q(quantita_per_uda__isnull=True) | models.Q(quantita_per_uda__gt=0)),
                name="nc_quantita_per_uda_positiva",
            ),
        ]

    def __str__(self):
        riferimento = self.lotto if self.lotto else self.get_tipo_nc_display()
        return f"NC {self.pk or 'nuova'} - {riferimento} - {self.get_stato_display()}"


class Ricetta(models.Model):

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="ricette",
    )

    nome = models.CharField(
        max_length=200,
    )

    versione = models.CharField(
        max_length=30,
        default="1",
    )

    attiva = models.BooleanField(
        default=True,
    )

    articolo_ricetta_attiva = models.GeneratedField(
        expression=models.Case(
            models.When(attiva=True, then=models.F("articolo")),
            default=models.Value(None),
        ),
        output_field=models.BigIntegerField(),
        db_persist=True,
        unique=True,
        editable=False,
        blank=True,
    )

    note = models.TextField(
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["articolo", "versione"],
                name="unica_versione_ricetta_per_articolo",
            ),
        ]

    def __str__(self):
        return f"{self.articolo.codice} - {self.nome} v{self.versione}"


class RigaRicetta(models.Model):

    ricetta = models.ForeignKey(
        Ricetta,
        on_delete=models.CASCADE,
        related_name="righe",
    )

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="righe_ricetta",
    )

    quantita = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    note = models.TextField(
        blank=True,
    )

    ingrediente_prodotto = models.BooleanField(
        default=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["ricetta", "articolo"],
                name="unico_articolo_per_ricetta",
            ),
            models.CheckConstraint(
                condition=models.Q(quantita__gt=0),
                name="riga_ricetta_quantita_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.ricetta} - {self.articolo.codice}: {self.quantita}"


class Produzione(models.Model):

    class Fase(models.TextChoices):
        PREPARAZIONE = "PREPARAZIONE", "Preparazione"
        ROBOQUBO = "ROBOQUBO", "RoboQbo"
        INVASETTAMENTO = "INVASETTAMENTO", "Invasettamento"
        COMPLETATA = "COMPLETATA", "Completata"

    class Stato(models.TextChoices):
        BOZZA = "BOZZA", "Bozza"
        CONFERMATA = "CONFERMATA", "Confermata"
        ABORTITA = "ABORTITA", "Abortita per non conformità"

    class StatoRoboqubo(models.TextChoices):
        NORMALE = "NORMALE", "In corso"
        CON_NC = "CON_NC", "In corso con NC aperta"
        SOSPESA = "SOSPESA", "Sospesa per NC"
        CONCLUSA = "CONCLUSA", "Conclusa"

    class StatoInvasettamento(models.TextChoices):
        NON_AVVIATO = "NON_AVVIATO", "Non avviato"
        IN_CORSO = "IN_CORSO", "In corso"
        CONGELATO = "CONGELATO", "Congelato per NC"
        CONCLUSO = "CONCLUSO", "Concluso"

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="produzioni",
        limit_choices_to={
            "categoria": "PRODOTTO_FINITO",
        },
    )

    lotto = models.OneToOneField(
        Lotto,
        on_delete=models.PROTECT,
        related_name="produzione",
        null=True,
        blank=True,
    )

    quantita_prodotta = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )

    data_produzione = models.DateField()

    fase = models.CharField(max_length=20, choices=Fase.choices, default=Fase.PREPARAZIONE)
    lotto_provvisorio = models.CharField(max_length=50, blank=True)
    numero_batch_previsti = models.PositiveSmallIntegerField(default=1)
    preparazione_chiusa_il = models.DateTimeField(null=True, blank=True)
    roboqubo_chiuso_il = models.DateTimeField(null=True, blank=True)
    stato_roboqubo = models.CharField(
        max_length=15,
        choices=StatoRoboqubo.choices,
        default=StatoRoboqubo.NORMALE,
        db_index=True,
    )
    stato_invasettamento = models.CharField(
        max_length=15,
        choices=StatoInvasettamento.choices,
        default=StatoInvasettamento.NON_AVVIATO,
        db_index=True,
    )
    invasettamento_congelato = models.BooleanField(default=False)
    richiede_lotto_ripresa = models.BooleanField(default=False)
    chiusa_per_nc = models.BooleanField(default=False)
    derivata_da = models.ForeignKey(
        "self", on_delete=models.PROTECT, related_name="produzioni_derivate",
        null=True, blank=True,
    )
    bloccata_da_nc = models.ForeignKey(
        NonConformitaLotto, on_delete=models.PROTECT, related_name="produzioni_bloccate",
        null=True, blank=True,
    )
    moca_igienizzati = models.BooleanField(default=False)
    moca_igienizzati_il = models.DateTimeField(null=True, blank=True)
    moca_igienizzati_da = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="produzioni_moca_igienizzati",
    )
    pezzi_difettosi_finali = models.PositiveIntegerField(default=0)
    capsule_difettose_finali = models.PositiveIntegerField(default=0)
    difetti_registrati_il = models.DateTimeField(null=True, blank=True)

    ubicazione_destinazione = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="produzioni_destinazione",
        null=True,
        blank=True,
        limit_choices_to={
            "tipo_magazzino": "PACKAGING",
        },
    )

    stato = models.CharField(
        max_length=15,
        choices=Stato.choices,
        default=Stato.BOZZA,
    )

    note = models.TextField(
        blank=True,
    )

    quantita_ottenuta_kg = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
    )
    peso_netto_vasetto_g = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )
    quantita_teorica_kg = models.DecimalField(
        max_digits=12, decimal_places=3, null=True, blank=True,
    )
    quantita_batch_reintegrato_kg = models.DecimalField(
        max_digits=12, decimal_places=6, default=0,
    )
    resa_percentuale = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True,
    )

    pastorizzazione_completata = models.BooleanField(default=False)
    vuoto_controllato = models.BooleanField(default=False)
    data_ora_pastorizzazione = models.DateTimeField(null=True, blank=True)
    data_ora_verifica_vuoto = models.DateTimeField(null=True, blank=True)

    data_creazione = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        permissions = [
            ("operare_roboqubo", "Può registrare i cicli RoboQbo"),
            ("operare_invasettamento", "Può registrare l'invasettamento"),
            ("gestire_produzioni", "Può verificare e correggere le produzioni"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(quantita_ottenuta_kg__isnull=True)
                    | models.Q(quantita_ottenuta_kg__gt=0)
                ),
                name="produzione_quantita_ottenuta_positiva",
            ),
        ]

    def __str__(self):
        lotto = self.lotto.codice_lotto if self.lotto else "SENZA LOTTO"
        return (
            f"{self.articolo.codice} - "
            f"{lotto} - "
            f"{self.stato}"
        )


class TankProduzione(models.Model):
    class StatoInvasettamento(models.TextChoices):
        DISPONIBILE = "DISPONIBILE", "Disponibile"
        INVASETTATO = "INVASETTATO", "Invasettato"

    produzione = models.ForeignKey(
        Produzione,
        on_delete=models.CASCADE,
        related_name="tank",
    )
    numero = models.PositiveSmallIntegerField()
    numero_batch = models.PositiveSmallIntegerField()
    gradi_brix = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    ph = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
    )
    data_ora_controlli = models.DateTimeField(null=True, blank=True)
    chiuso_il = models.DateTimeField(null=True, blank=True)
    annullato = models.BooleanField(default=False)
    motivo_annullamento = models.TextField(blank=True)
    data_ora_annullamento = models.DateTimeField(null=True, blank=True)
    annullato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tank_produzione_annullati",
        null=True,
        blank=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    stato_invasettamento = models.CharField(
        max_length=15,
        choices=StatoInvasettamento.choices,
        default=StatoInvasettamento.DISPONIBILE,
        db_index=True,
    )
    invasettato_il = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["numero"]
        constraints = [
            models.UniqueConstraint(
                fields=["produzione", "numero"],
                name="unico_numero_tank_per_produzione",
            ),
            models.CheckConstraint(
                condition=models.Q(numero_batch__gte=1),
                name="tank_numero_batch_positivo",
            ),
            models.CheckConstraint(
                condition=models.Q(gradi_brix__isnull=True)
                | models.Q(gradi_brix__gte=0),
                name="tank_brix_non_negativo",
            ),
            models.CheckConstraint(
                condition=models.Q(ph__isnull=True)
                | models.Q(ph__gte=0, ph__lte=14),
                name="tank_ph_valido",
            ),
        ]

    @property
    def controllato(self):
        return self.gradi_brix is not None and self.ph is not None

    @property
    def brix_conforme(self):
        return self.controllato and Decimal("40") <= self.gradi_brix <= Decimal("45")

    @property
    def ph_in_allerta(self):
        return self.controllato and Decimal("4.10") < self.ph <= Decimal("4.40")

    @property
    def ph_non_conforme(self):
        return self.controllato and self.ph > Decimal("4.40")

    @property
    def non_conforme(self):
        return self.controllato and (not self.brix_conforme or self.ph_non_conforme)

    @property
    def conforme(self):
        return self.controllato and self.brix_conforme and self.ph <= Decimal("4.10")

    @property
    def esito_controlli(self):
        if not self.controllato:
            return "APERTO"
        if self.non_conforme:
            return "NC"
        if self.ph_in_allerta:
            return "ALLERTA"
        return "CONFORME"

    def __str__(self):
        return f"Produzione {self.produzione_id} - Tank {self.numero}"


class EsitoControllo(models.TextChoices):
    C = "C", "Conforme"
    NC = "NC", "Non conforme"
    NA = "NA", "Non applicabile"


class BatchProduzione(models.Model):
    class Stato(models.TextChoices):
        DA_LAVORARE = "DA_LAVORARE", "Da lavorare"
        CONFORME = "CONFORME", "Conforme"
        QUARANTENA = "QUARANTENA", "In quarantena"
        SOSPESO = "SOSPESO", "Sospeso per NC"
        SCARTATO = "SCARTATO", "Scartato"
        REINTEGRATO = "REINTEGRATO", "Reintegrato"
        ANNULLATO = "ANNULLATO", "Annullato per non conformità"

    produzione = models.ForeignKey(Produzione, on_delete=models.CASCADE, related_name="batch")
    tank = models.ForeignKey(TankProduzione, on_delete=models.CASCADE, related_name="batch", null=True, blank=True)
    numero = models.PositiveSmallIntegerField()
    ora_inizio = models.TimeField(null=True, blank=True)
    ora_fine = models.TimeField(null=True, blank=True)
    temperatura_conformita = models.DecimalField(max_digits=5, decimal_places=2, default=82)
    durata_conformita_secondi = models.PositiveSmallIntegerField(default=60)
    esito_conformita = models.CharField(max_length=2, choices=EsitoControllo.choices, blank=True)
    note = models.TextField(blank=True)
    stato = models.CharField(
        max_length=15,
        choices=Stato.choices,
        default=Stato.CONFORME,
        db_index=True,
    )
    quarantena_il = models.DateTimeField(null=True, blank=True)
    risolto_il = models.DateTimeField(null=True, blank=True)
    registrato_il = models.DateTimeField(auto_now_add=True)
    registrato_da = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["numero"]
        constraints = [models.UniqueConstraint(fields=["produzione", "numero"], name="unico_batch_per_produzione")]


class MaterialeSospesoNonConformita(models.Model):
    class Esito(models.TextChoices):
        DA_VALUTARE = "DA_VALUTARE", "Da valutare"
        RIUTILIZZA = "RIUTILIZZA", "Riutilizzabile nella stessa produzione"
        CONSERVA = "CONSERVA", "Conserva in Magazzino produzione"
        SCARTA = "SCARTA", "Da scartare"

    non_conformita = models.ForeignKey(
        NonConformitaLotto, on_delete=models.CASCADE, related_name="materiali_sospesi",
    )
    prelievo = models.ForeignKey(
        "PrelievoProduzione", on_delete=models.PROTECT, related_name="sospensioni_nc",
    )
    lotto_originale = models.ForeignKey(
        Lotto, on_delete=models.PROTECT, related_name="materiali_recuperati_nc",
        null=True, blank=True,
    )
    lotto_recuperato = models.ForeignKey(
        Lotto, on_delete=models.PROTECT, related_name="materiali_sospesi_nc",
        null=True, blank=True,
    )
    quantita = models.DecimalField(max_digits=12, decimal_places=6)
    esito = models.CharField(max_length=15, choices=Esito.choices, default=Esito.DA_VALUTARE)
    nuova_data_scadenza = models.DateField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ("prelievo__lotto__articolo__codice", "id")
        constraints = [
            models.UniqueConstraint(
                fields=["non_conformita", "prelievo"], name="unico_materiale_sospeso_per_nc",
            ),
            models.CheckConstraint(condition=models.Q(quantita__gt=0), name="materiale_sospeso_quantita_positiva"),
        ]


class LottoUscitaProduzione(models.Model):
    produzione = models.ForeignKey(Produzione, on_delete=models.PROTECT, related_name="lotti_uscita")
    lotto = models.OneToOneField(Lotto, on_delete=models.PROTECT, related_name="uscita_produzione")
    non_conformita = models.ForeignKey(
        NonConformitaLotto, on_delete=models.PROTECT, null=True, blank=True, related_name="lotti_uscita",
    )
    provvisorio = models.BooleanField(default=False)
    motivo_separazione = models.TextField(blank=True)
    numero_vasetti_buoni = models.PositiveIntegerField(null=True, blank=True)
    numero_vasetti_scartati = models.PositiveIntegerField(default=0)
    numero_capsule_difettose = models.PositiveIntegerField(default=0)
    peso_netto_vasetto_g = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    quantita_ottenuta_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    quantita_teorica_kg = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    resa_percentuale = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    note = models.TextField(blank=True)
    creato_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creato_il", "id")


class CarrelloProduzione(models.Model):
    produzione = models.ForeignKey(Produzione, on_delete=models.CASCADE, related_name="carrelli")
    numero = models.PositiveSmallIntegerField()
    numero_pezzi = models.PositiveIntegerField(default=0)
    temperatura_pastorizzazione = models.DecimalField(max_digits=5, decimal_places=2, default=71)
    durata_pastorizzazione_minuti = models.PositiveSmallIntegerField(default=4)
    esito_pastorizzazione = models.CharField(max_length=2, choices=EsitoControllo.choices)
    note_pastorizzazione = models.TextField(blank=True)
    pastorizzazione_registrata_il = models.DateTimeField(auto_now_add=True)
    esito_shock_vuoto = models.CharField(max_length=2, choices=EsitoControllo.choices, blank=True)
    pezzi_difettosi = models.PositiveIntegerField(default=0)
    note_shock_vuoto = models.TextField(blank=True)
    shock_vuoto_registrato_il = models.DateTimeField(null=True, blank=True)
    capsule_difettose = models.PositiveIntegerField(null=True, blank=True)
    chiuso_il = models.DateTimeField(null=True, blank=True)
    registrato_da = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    lotto_uscita = models.ForeignKey(
        LottoUscitaProduzione,
        on_delete=models.PROTECT,
        related_name="carrelli",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["numero"]
        constraints = [models.UniqueConstraint(fields=["produzione", "numero"], name="unico_carrello_per_produzione")]


class PrelievoProduzione(models.Model):

    produzione = models.ForeignKey(
        Produzione,
        on_delete=models.CASCADE,
        related_name="prelievi",
    )

    tank = models.ForeignKey(
        TankProduzione,
        on_delete=models.CASCADE,
        related_name="prelievi",
        null=True,
        blank=True,
    )

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="prelievi_produzione",
    )

    ubicazione_origine = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="prelievi_produzione",
    )

    scaffale_origine = models.CharField(max_length=30, blank=True)
    piano_origine = models.CharField(max_length=30, blank=True)

    quantita_prelevata = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )
    quantita_movimentata = models.DecimalField(
        max_digits=12, decimal_places=6, null=True, blank=True,
        help_text="Quantità fisicamente prelevata in UDA intere.",
    )
    quantita_resa_produzione = models.DecimalField(
        max_digits=12, decimal_places=6, default=0,
        help_text="Avanzo dell'UDA trasferito al Magazzino produzione.",
    )
    quantita_trasferita_nc = models.DecimalField(
        max_digits=12, decimal_places=6, default=0,
        help_text="Quota trasferita a una nuova produzione in seguito a NC.",
    )

    quantita_scarto = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        default=None,
    )

    note = models.TextField(
        blank=True,
    )

    def __str__(self):
        return (
            f"{self.produzione.articolo.codice} - "
            f"{self.lotto.articolo.codice} - "
            f"{self.lotto.codice_lotto} - "
            f"{self.quantita_prelevata}"
        )


# ============================================================
# PRODUZIONE SEMILAVORATI
# ============================================================

class ProduzioneSemilavorato(models.Model):

    class Stato(models.TextChoices):
        BOZZA = "BOZZA", "Bozza"
        CONFERMATA = "CONFERMATA", "Confermata"

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="produzioni_semilavorato",
        limit_choices_to={
            "categoria": "SEMILAVORATO",
        },
    )

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="produzioni_semilavorato",
        null=True,
        blank=True,
    )

    data_produzione = models.DateField()

    quantita_prodotta = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
    )

    ubicazione_destinazione = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="produzioni_semilavorato_destinazione",
        null=True,
        blank=True,
        limit_choices_to={
            "tipo_magazzino": "SEMILAVORATI",
        },
    )

    stato = models.CharField(
        max_length=15,
        choices=Stato.choices,
        default=Stato.BOZZA,
    )

    note = models.TextField(
        blank=True,
    )

    data_creazione = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        lotto = self.lotto.codice_lotto if self.lotto else "SENZA LOTTO"
        return (
            f"{self.articolo.codice} - "
            f"{lotto} - "
            f"{self.stato}"
        )


class PrelievoProduzioneSemilavorato(models.Model):

    produzione = models.ForeignKey(
        ProduzioneSemilavorato,
        on_delete=models.CASCADE,
        related_name="prelievi",
    )

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="prelievi_produzione_semilavorato",
    )

    ubicazione_origine = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="prelievi_produzione_semilavorato",
    )
    scaffale_origine = models.CharField(max_length=30, blank=True)
    piano_origine = models.CharField(max_length=30, blank=True)

    quantita_prelevata = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    quantita_scarto = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        null=True,
        blank=True,
        default=None,
    )

    note = models.TextField(
        blank=True,
    )

    def __str__(self):
        return (
            f"{self.produzione.articolo.codice} - "
            f"{self.lotto.articolo.codice} - "
            f"{self.lotto.codice_lotto} - "
            f"{self.quantita_prelevata}"
        )


class Confezionamento(models.Model):

    lotto_origine = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="confezionamenti_origine",
    )

    articolo_finito = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="confezionamenti",
    )

    lotto_finito = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="confezionamenti_destinazione",
    )

    quantita_confezionata = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    data_confezionamento = models.DateField()

    note = models.TextField(
        blank=True,
    )

    data_creazione = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"{self.lotto_origine.articolo.codice} - "
            f"{self.lotto_origine.codice_lotto} -> "
            f"{self.articolo_finito.codice} - "
            f"{self.quantita_confezionata}"
        )


class ConsumoConfezionamento(models.Model):

    confezionamento = models.ForeignKey(
        Confezionamento,
        on_delete=models.CASCADE,
        related_name="consumi",
    )

    lotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="consumi_confezionamento",
    )

    ubicazione = models.ForeignKey(
        Ubicazione,
        on_delete=models.PROTECT,
        related_name="consumi_confezionamento",
    )

    quantita_utilizzata = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    def __str__(self):
        return (
            f"{self.confezionamento} - "
            f"{self.lotto.articolo.codice} - "
            f"{self.quantita_utilizzata}"
        )


class Inscatolamento(models.Model):

    lotto_prodotto = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="inscatolamenti",
    )

    lotto_imballo = models.ForeignKey(
        Lotto,
        on_delete=models.PROTECT,
        related_name="utilizzi_inscatolamento",
    )

    quantita_prodotti = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    quantita_imballi = models.DecimalField(
        max_digits=12,
        decimal_places=6,
    )

    pezzi_per_imballo = models.PositiveIntegerField()

    data_inscatolamento = models.DateField()

    note = models.TextField(
        blank=True,
    )

    data_creazione = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"{self.lotto_prodotto} - "
            f"{self.quantita_imballi} imballi da "
            f"{self.pezzi_per_imballo}"
        )


class RegistroOperazione(models.Model):
    class Esito(models.TextChoices):
        RIUSCITA = "RIUSCITA", "Riuscita"
        RIFIUTATA = "RIFIUTATA", "Rifiutata"
        ERRORE = "ERRORE", "Errore"

    data_ora = models.DateTimeField(auto_now_add=True, db_index=True)
    utente = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="registro_operazioni_mira",
        null=True,
        blank=True,
    )
    azione = models.CharField(max_length=100, db_index=True)
    area = models.CharField(max_length=100, blank=True, db_index=True)
    descrizione = models.TextField()
    metodo = models.CharField(max_length=10, blank=True)
    percorso = models.CharField(max_length=500, blank=True)
    indirizzo_ip = models.GenericIPAddressField(null=True, blank=True)
    dettagli = models.JSONField(default=dict, blank=True)
    esito = models.CharField(max_length=15, choices=Esito.choices, default=Esito.RIUSCITA, db_index=True)
    modello = models.CharField(max_length=100, blank=True, db_index=True)
    record_id = models.CharField(max_length=100, blank=True, db_index=True)
    oggetto = models.CharField(max_length=500, blank=True)
    valori_precedenti = models.JSONField(default=dict, blank=True)
    valori_successivi = models.JSONField(default=dict, blank=True)
    motivazione = models.TextField(blank=True)
    codice_operazione = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user_agent = models.TextField(blank=True)
    errore = models.TextField(blank=True)

    class Meta:
        ordering = ["-data_ora", "-pk"]

    def __str__(self):
        return f"{self.data_ora} - {self.azione}"
