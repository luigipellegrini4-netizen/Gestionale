from django.conf import settings
from django.db import models


class Articolo(models.Model):

    class Categoria(models.TextChoices):
        MATERIA_PRIMA = "MATERIA_PRIMA", "Materia prima"
        MOCA = "MOCA", "MOCA"
        IGIENE = "IGIENE", "Igiene"
        SEMILAVORATO = "SEMILAVORATO", "Semilavorato"
        PACKAGING = "PACKAGING", "Packaging"
        PRODOTTO_NUDO = "PRODOTTO_NUDO", "Prodotto nudo"
        PRODOTTO_FINITO = "PRODOTTO_FINITO", "Prodotto finito"

    class UnitaMisura(models.TextChoices):
        KG = "KG", "Kilogrammi"
        L = "L", "Litri"
        PZ = "PZ", "Pezzi"

    class CriterioRotazione(models.TextChoices):
        FIFO = "FIFO", "FIFO"
        FEFO = "FEFO", "FEFO"
        NESSUNO = "NESSUNO", "Nessuno"

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

    prodotto_finito_collegato = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="prodotti_nudi_collegati",
        limit_choices_to={
            "categoria": "PRODOTTO_FINITO",
        },
    )

    codice = models.CharField(
        max_length=30,
        unique=True,
    )

    descrizione = models.CharField(
        max_length=200,
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

    criterio_rotazione = models.CharField(
        max_length=10,
        choices=CriterioRotazione.choices,
        default=CriterioRotazione.FIFO,
    )

    pezzi_per_imballo = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    attivo = models.BooleanField(
        default=True,
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

    scaffale = models.CharField(
        max_length=30,
        blank=True,
    )

    piano = models.CharField(
        max_length=30,
        blank=True,
    )

    attiva = models.BooleanField(
        default=True,
    )

    def __str__(self):
        posizione = self.nome

        if self.scaffale:
            posizione += f" - Scaffale {self.scaffale}"

        if self.piano:
            posizione += f" - Piano {self.piano}"

        return posizione


class Lotto(models.Model):

    class Tipo(models.TextChoices):
        ACQUISTO = "ACQUISTO", "Acquisto"
        PRODUZIONE = "PRODUZIONE", "Produzione"

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

    note = models.TextField(
        blank=True,
    )

    def __str__(self):
        return f"{self.articolo.codice} - {self.codice_lotto}"

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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lotto", "ubicazione"],
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

    note = models.TextField(
        blank=True,
    )

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

    class Stato(models.TextChoices):
        BOZZA = "BOZZA", "Bozza"
        CONFERMATA = "CONFERMATA", "Confermata"

    articolo = models.ForeignKey(
        Articolo,
        on_delete=models.PROTECT,
        related_name="produzioni",
        limit_choices_to={
            "categoria": "PRODOTTO_NUDO",
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


class PrelievoProduzione(models.Model):

    produzione = models.ForeignKey(
        Produzione,
        on_delete=models.CASCADE,
        related_name="prelievi",
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
