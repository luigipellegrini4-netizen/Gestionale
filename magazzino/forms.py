from django import forms
from django.db.models import Q

from .models import (
    Articolo,
    Fornitore,
    Ubicazione,
    Lotto,
    Giacenza,
    Ricetta,
    RigaRicetta,
)

from datetime import date

from decimal import Decimal

class CaricoLottoForm(forms.Form):

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.filter(
            attivo=True,
        ).order_by(
            "codice",
        ),
        label="Articolo",
    )

    codice_lotto = forms.CharField(
        max_length=50,
        label="Codice lotto",
    )

    fornitore = forms.ModelChoiceField(
        queryset=Fornitore.objects.filter(
            attivo=True,
        ).order_by(
            "ragione_sociale",
        ),
        label="Fornitore",
        required=False,
    )

    quantita = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità",
    )

    ubicazione = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
        ).order_by(
            "nome",
        ),
        label="Ubicazione",
    )

    scaffale = forms.CharField(
        max_length=30,
        required=False,
        label="Scaffale",
    )

    piano = forms.CharField(
        max_length=30,
        required=False,
        label="Piano",
    )

    data_arrivo = forms.DateField(
        label="Data arrivo",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    data_scadenza = forms.DateField(
        label="Data scadenza",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
        required=False,
    )

    causale = forms.CharField(
        max_length=200,
        label="Causale",
        initial="Carico",
        required=False,
    )

    note = forms.CharField(
        label="Note",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class TrasferimentoForm(forms.Form):

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.filter(attivo=True).order_by(
            "codice",
        ),
        label="Articolo da trasferire",
    )

    giacenza = forms.ModelChoiceField(
        queryset=Giacenza.objects.none(),
        label="Lotto e posizione di origine",
        empty_label="Seleziona prima un articolo",
    )

    ubicazione_destinazione = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
        ).order_by(
            "nome",
        ),
        label="Ubicazione destinazione",
    )

    scaffale_destinazione = forms.CharField(
        max_length=30,
        required=False,
        label="Scaffale destinazione",
    )

    piano_destinazione = forms.CharField(
        max_length=30,
        required=False,
        label="Piano destinazione",
    )

    quantita = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità",
    )

    note = forms.CharField(
        label="Note",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        articolo_id = self.data.get("articolo") or self.initial.get(
            "articolo"
        )
        if articolo_id:
            try:
                articolo_id = int(articolo_id)
            except (TypeError, ValueError):
                pass
            else:
                self.fields["giacenza"].queryset = (
                    Giacenza.objects.select_related(
                        "lotto__articolo",
                        "ubicazione",
                    )
                    .filter(
                        lotto__articolo_id=articolo_id,
                        quantita__gt=0,
                        ubicazione__attiva=True,
                    )
                    .order_by("lotto__codice_lotto", "ubicazione__nome")
                )

    def clean(self):
        cleaned_data = super().clean()
        articolo = cleaned_data.get("articolo")
        giacenza = cleaned_data.get("giacenza")
        destinazione = cleaned_data.get("ubicazione_destinazione")
        quantita = cleaned_data.get("quantita")

        if (
            articolo
            and giacenza
            and giacenza.lotto.articolo_id != articolo.pk
        ):
            self.add_error(
                "giacenza",
                "Il lotto non appartiene all'articolo selezionato.",
            )
        if giacenza and giacenza.quantita <= 0:
            self.add_error(
                "giacenza",
                "Il lotto selezionato non ha giacenza disponibile.",
            )
        if giacenza and destinazione == giacenza.ubicazione:
            self.add_error(
                "ubicazione_destinazione",
                "Il magazzino di destinazione deve essere diverso dall'origine.",
            )
        if giacenza and quantita and quantita > giacenza.quantita:
            self.add_error(
                "quantita",
                f"Disponibilità insufficiente: massimo {giacenza.quantita}.",
            )
        return cleaned_data


class ConsumoForm(forms.Form):

    lotto = forms.ModelChoiceField(
        queryset=Lotto.objects.select_related(
            "articolo",
        ).order_by(
            "codice_lotto",
        ),
        label="Lotto",
    )

    ubicazione_origine = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
        ).order_by(
            "nome",
        ),
        label="Ubicazione origine",
    )

    scaffale_origine = forms.CharField(
        max_length=30,
        required=False,
        label="Scaffale origine",
    )

    piano_origine = forms.CharField(
        max_length=30,
        required=False,
        label="Piano origine",
    )

    quantita = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità",
    )

    causale = forms.CharField(
        label="Causale",
        initial="Consumo",
        required=False,
    )

    note = forms.CharField(
        label="Note",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class ArticoloProduzioneChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, articolo):
        return f"{articolo.codice} - {articolo.nome_per_produzione}"


class RicettaForm(forms.ModelForm):

    articolo = ArticoloProduzioneChoiceField(
        queryset=Articolo.objects.none(),
        label="Prodotto",
    )

    class Meta:
        model = Ricetta

        fields = [
            "articolo",
            "nome",
            "versione",
            "attiva",
            "note",
        ]

        labels = {
            "articolo": "Prodotto",
            "nome": "Nome ricetta",
            "versione": "Versione",
            "attiva": "Ricetta attiva",
            "note": "Note",
        }

        widgets = {
            "note": forms.Textarea(
                attrs={
                    "rows": 3,
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["articolo"].queryset = (
            Articolo.objects.filter(
                attivo=True,
                categoria__in=[
                    Articolo.Categoria.SEMILAVORATO,
                    Articolo.Categoria.PRODOTTO_FINITO,
                ],
            ).order_by(
                "codice",
            )
        )

    def clean(self):
        cleaned_data = super().clean()
        articolo = cleaned_data.get("articolo")
        attiva = cleaned_data.get("attiva")

        if articolo is not None and attiva:
            altre_attive = Ricetta.objects.filter(
                articolo=articolo,
                attiva=True,
            ).exclude(pk=self.instance.pk)

            if altre_attive.exists():
                self.add_error(
                    "attiva",
                    "Esiste già una ricetta attiva per questo articolo.",
                )

        return cleaned_data


class RigaRicettaForm(forms.ModelForm):

    class Meta:
        model = RigaRicetta

        fields = [
            "articolo",
            "quantita",
            "ingrediente_prodotto",
            "note",
        ]

        labels = {
            "articolo": "Ingrediente / materiale",
            "quantita": "Quantità",
            "ingrediente_prodotto": "Entra nel prodotto",
            "note": "Note",
        }

        widgets = {
            "quantita": forms.NumberInput(
                attrs={
                    "step": "0.000001",
                    "min": "0.000001",
                },
            ),
            "note": forms.Textarea(
                attrs={
                    "rows": 2,
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["articolo"].queryset = (
            Articolo.objects.filter(
                attivo=True,
            ).order_by(
                "categoria",
                "codice",
            )
        )

    def clean_quantita(self):
        quantita = self.cleaned_data["quantita"]
        if quantita <= 0:
            raise forms.ValidationError(
                "La quantità deve essere maggiore di zero."
            )
        return quantita


# ============================================================
# PRODUZIONE MARMELLATE / PRODOTTO NUDO
# ============================================================

class ProduzioneForm(forms.Form):

    articolo = ArticoloProduzioneChoiceField(
        queryset=Articolo.objects.filter(
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            attivo=True,
        ).order_by(
            "descrizione",
        ),
        label="Prodotto",
    )

    data_produzione = forms.DateField(
        label="Data produzione",
        initial=date.today,
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    note = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
        label="Note",
    )


class IngredienteProduzioneForm(forms.Form):

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.none(),
        label="Ingrediente / materiale MOCA",
    )

    quantita_richiesta = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità da prelevare",
    )

    def __init__(self, *args, produzione=None, **kwargs):
        super().__init__(*args, **kwargs)

        if produzione is None:
            self.fields["articolo"].queryset = Articolo.objects.none()
            return

        ricetta = (
            produzione.articolo.ricette
            .filter(attiva=True)
            .prefetch_related("righe__articolo")
            .first()
        )

        ingredienti_ids = []

        if ricetta is not None:
            ingredienti_ids = list(
                ricetta.righe.values_list(
                    "articolo_id",
                    flat=True,
                )
            )

        self.fields["articolo"].queryset = (
            Articolo.objects.filter(
                attivo=True,
            ).filter(
                Q(pk__in=ingredienti_ids)
                | Q(
                    categoria=Articolo.Categoria.MOCA,
                )
            ).distinct().order_by(
                "categoria",
                "descrizione",
            )
        )


class AperturaTankForm(forms.Form):
    numero_batch = forms.IntegerField(
        min_value=1,
        max_value=5,
        initial=5,
        label="Numero di batch",
        help_text="Un tank può contenere da 1 a 5 batch Robocubo.",
    )


class ControlloTankForm(forms.Form):
    gradi_brix = forms.DecimalField(
        min_value=0,
        max_digits=5,
        decimal_places=2,
        label="Gradi Brix",
    )
    ph = forms.DecimalField(
        min_value=0,
        max_value=14,
        max_digits=4,
        decimal_places=2,
        label="pH",
    )


class ScartoProduzioneForm(forms.Form):

    quantita_scarto = forms.DecimalField(
        max_digits=12,
        decimal_places=6,
        min_value=Decimal("0"),
        label="Scarto",
        widget=forms.NumberInput(
            attrs={
                "step": "0.000001",
                "min": "0",
            },
        ),
    )

    note = forms.CharField(
        required=False,
        label="Note scarto",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
            },
        ),
    )

    def __init__(
        self,
        *args,
        prelievo=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if prelievo is not None:
            self.fields["quantita_scarto"].max_value = (
                prelievo.quantita_prelevata
            )


class ConfermaProduzioneForm(forms.Form):

    pastorizzazione_completata = forms.BooleanField(
        label="Pastorizzazione completata",
    )

    vuoto_controllato = forms.BooleanField(
        label="Controllo del vuoto completato",
    )

    quantita_prodotta = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Vasetti prodotti",
    )

    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class ConfezionamentoForm(forms.Form):

    lotto_origine = forms.ModelChoiceField(
        queryset=Lotto.objects.filter(
            articolo__categoria=Articolo.Categoria.PRODOTTO_FINITO,
            fase=Lotto.Fase.INVASETTATO,
            articolo__attivo=True,
            giacenze__quantita__gt=0,
        ).select_related(
            "articolo",
        ).distinct().order_by(
            "articolo__codice",
            "codice_lotto",
        ),
        label="Lotto invasettato da etichettare",
    )

    quantita_confezionata = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità da confezionare",
    )

    lotto_etichetta = forms.ModelChoiceField(
        queryset=Lotto.objects.filter(
            articolo__categoria=Articolo.Categoria.PACKAGING,
            articolo__tipo_packaging=Articolo.TipoPackaging.ETICHETTA,
            articolo__attivo=True,
            giacenze__quantita__gt=0,
        ).select_related(
            "articolo",
        ).distinct().order_by(
            "articolo__codice",
            "codice_lotto",
        ),
        label="Lotto etichette",
    )

    ubicazione_origine = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
            tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING,
        ).order_by(
            "nome",
        ),
        label="Ubicazione prodotto invasettato",
    )

    ubicazione_destinazione = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        ).order_by(
            "nome",
        ),
        label="Ubicazione prodotto finito",
    )

    data_confezionamento = forms.DateField(
        label="Data confezionamento",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
        required=False,
    )

    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class InscatolamentoForm(forms.Form):

    lotto_prodotto = forms.ModelChoiceField(
        queryset=Lotto.objects.filter(
            articolo__categoria=Articolo.Categoria.PRODOTTO_FINITO,
            fase=Lotto.Fase.ETICHETTATO,
            articolo__attivo=True,
            giacenze__quantita__gt=0,
            giacenze__ubicazione__tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        ).select_related(
            "articolo",
        ).distinct().order_by(
            "articolo__codice",
            "codice_lotto",
        ),
        label="Lotto prodotto finito",
    )

    lotto_imballo = forms.ModelChoiceField(
        queryset=Lotto.objects.filter(
            articolo__categoria=Articolo.Categoria.PACKAGING,
            articolo__tipo_packaging__in=[
                Articolo.TipoPackaging.SCATOLA,
                Articolo.TipoPackaging.COFANETTO,
            ],
            articolo__attivo=True,
            giacenze__quantita__gt=0,
        ).select_related(
            "articolo",
        ).distinct().order_by(
            "articolo__codice",
            "codice_lotto",
        ),
        label="Lotto scatola / cofanetto",
    )

    quantita_prodotti = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Pezzi da inscatolare",
    )

    ubicazione_prodotto = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        ).order_by(
            "nome",
        ),
        label="Ubicazione prodotto finito",
    )

    ubicazione_imballo = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
            tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING,
        ).order_by(
            "nome",
        ),
        label="Ubicazione imballo",
    )

    data_inscatolamento = forms.DateField(
        required=False,
        label="Data inscatolamento",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


# ============================================================
# PRODUZIONE SEMILAVORATI
# ============================================================

class ProduzioneSemilavoratoForm(forms.Form):

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.filter(
            categoria=Articolo.Categoria.SEMILAVORATO,
            attivo=True,
        ).order_by(
            "descrizione",
        ),
        label="Semilavorato da produrre",
    )

    data_produzione = forms.DateField(
        label="Data produzione",
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class IngredienteSemilavoratoForm(forms.Form):

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.none(),
        label="Ingrediente",
    )

    quantita_richiesta = forms.DecimalField(
        max_digits=12,
        decimal_places=6,
        min_value=Decimal("0.000001"),
        label="Quantità da prelevare",
        widget=forms.NumberInput(
            attrs={
                "step": "0.000001",
                "min": "0.000001",
            },
        ),
    )

    def __init__(
        self,
        *args,
        produzione=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if produzione is None:
            return

        ricetta = (
            produzione.articolo.ricette
            .filter(
                attiva=True,
            )
            .first()
        )

        if ricetta is None:
            return

        articoli_ricetta = (
            ricetta.righe
            .values_list(
                "articolo_id",
                flat=True,
            )
        )

        self.fields["articolo"].queryset = (
            Articolo.objects
            .filter(
                pk__in=articoli_ricetta,
                attivo=True,
            )
            .order_by(
                "descrizione",
            )
        )


class ScartoProduzioneSemilavoratoForm(forms.Form):

    quantita_scarto = forms.DecimalField(
        max_digits=12,
        decimal_places=6,
        min_value=Decimal("0"),
        label="Scarto",
        widget=forms.NumberInput(
            attrs={
                "step": "0.000001",
                "min": "0",
            },
        ),
    )

    note = forms.CharField(
        required=False,
        label="Note scarto",
        widget=forms.Textarea(
            attrs={
                "rows": 2,
            },
        ),
    )

    def __init__(
        self,
        *args,
        prelievo=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if prelievo is not None:
            self.fields["quantita_scarto"].max_value = (
                prelievo.quantita_prelevata
            )

class ConfermaProduzioneSemilavoratoForm(forms.Form):

    quantita_prodotta = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità prodotta",
    )

    ubicazione_destinazione = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
            tipo_magazzino=Ubicazione.TipoMagazzino.SEMILAVORATI,
        ).order_by(
            "nome",
        ),
        label="Cella destinazione",
    )

    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            },
        ),
    )


class ArticoloForm(forms.ModelForm):

    class Meta:
        model = Articolo

        fields = [
            "codice",
            "descrizione",
            "nome_produzione",
            "categoria",
            "unita_misura",
            "quantita_per_confezione",
            "scorta_minima",
            "criterio_rotazione",
            "tipo_packaging",
            "pezzi_per_imballo",
            "attivo",
            "note",
        ]

        labels = {
            "codice": "Codice",
            "descrizione": "Descrizione",
            "nome_produzione": "Nome prodotto in ricette e produzione",
            "categoria": "Categoria",
            "unita_misura": "Unità di misura",
            "quantita_per_confezione": "Quantità per confezione",
            "scorta_minima": "Scorta minima",
            "criterio_rotazione": "Criterio rotazione",
            "tipo_packaging": "Tipo packaging",
            "pezzi_per_imballo": "Confezioni per imballo",
            "attivo": "Articolo attivo",
            "note": "Note",
        }

        help_texts = {
            "quantita_per_confezione": (
                "Quantità contenuta in ogni confezione, espressa nell'unità "
                "di misura dell'articolo. Esempio: 1 kg per un sacchetto di zucchero."
            ),
            "pezzi_per_imballo": (
                "Numero di confezioni contenute in un imballo. "
                "Esempio: 25 sacchetti da 1 kg di zucchero per imballo."
            ),
        }

    def clean_quantita_per_confezione(self):
        quantita = self.cleaned_data.get("quantita_per_confezione")
        if quantita is not None and quantita <= 0:
            raise forms.ValidationError(
                "La quantità per confezione deve essere maggiore di zero."
            )
        return quantita


class FornitoreForm(forms.ModelForm):
    class Meta:
        model = Fornitore
        fields = [
            "codice",
            "ragione_sociale",
            "partita_iva",
            "telefono",
            "email",
            "indirizzo",
            "attivo",
            "note",
        ]
        labels = {
            "codice": "Codice",
            "ragione_sociale": "Ragione sociale",
            "partita_iva": "Partita IVA",
            "telefono": "Telefono",
            "email": "Email",
            "indirizzo": "Indirizzo",
            "attivo": "Fornitore attivo",
            "note": "Note",
        }


class UbicazioneForm(forms.ModelForm):
    class Meta:
        model = Ubicazione
        fields = [
            "nome",
            "tipo_magazzino",
            "scaffale",
            "piano",
            "attiva",
        ]
        labels = {
            "nome": "Nome",
            "tipo_magazzino": "Tipo magazzino",
            "scaffale": "Scaffale",
            "piano": "Piano",
            "attiva": "Ubicazione attiva",
        }


class ImportazioneCSVForm(forms.Form):
    tipo = forms.ChoiceField(
        choices=[
            ("fornitori", "Fornitori"),
            ("articoli", "Articoli"),
            ("ubicazioni", "Ubicazioni"),
        ],
        label="Anagrafica",
    )
    file_csv = forms.FileField(label="File CSV")

    def clean_file_csv(self):
        file_csv = self.cleaned_data["file_csv"]
        if file_csv.size > 2 * 1024 * 1024:
            raise forms.ValidationError("Il file non può superare 2 MB.")
        if not file_csv.name.lower().endswith(".csv"):
            raise forms.ValidationError("Seleziona un file con estensione .csv.")
        return file_csv


class RipristinoBackupForm(forms.Form):
    file_json = forms.FileField(label="File backup JSON")
    conferma = forms.CharField(
        label="Conferma",
        help_text="Digita RIPRISTINA per sostituire i dati gestionali correnti.",
    )

    def clean_file_json(self):
        file_json = self.cleaned_data["file_json"]
        if file_json.size > 20 * 1024 * 1024:
            raise forms.ValidationError("Il backup non può superare 20 MB.")
        if not file_json.name.lower().endswith(".json"):
            raise forms.ValidationError("Seleziona un file .json.")
        return file_json

    def clean_conferma(self):
        conferma = self.cleaned_data["conferma"].strip()
        if conferma != "RIPRISTINA":
            raise forms.ValidationError("Digita esattamente RIPRISTINA.")
        return conferma
