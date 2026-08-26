from django import forms
from django.db.models import Q

from .models import (
    Articolo,
    Fornitore,
    Ubicazione,
    Lotto,
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

    ubicazione_destinazione = forms.ModelChoiceField(
        queryset=Ubicazione.objects.filter(
            attiva=True,
        ).order_by(
            "nome",
        ),
        label="Ubicazione destinazione",
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


class RicettaForm(forms.ModelForm):

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
            "articolo": "Articolo",
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
                    Articolo.Categoria.PRODOTTO_NUDO,
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

    articolo = forms.ModelChoiceField(
        queryset=Articolo.objects.filter(
            categoria=Articolo.Categoria.PRODOTTO_NUDO,
            attivo=True,
        ).order_by(
            "descrizione",
        ),
        label="Prodotto da realizzare",
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
            articolo__categoria=Articolo.Categoria.PRODOTTO_NUDO,
            articolo__attivo=True,
            giacenze__quantita__gt=0,
        ).select_related(
            "articolo",
        ).distinct().order_by(
            "articolo__codice",
            "codice_lotto",
        ),
        label="Lotto prodotto nudo",
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
        label="Ubicazione prodotto nudo",
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
            "categoria",
            "unita_misura",
            "scorta_minima",
            "criterio_rotazione",
            "tipo_packaging",
            "pezzi_per_imballo",
            "prodotto_finito_collegato",
            "attivo",
            "note",
        ]

        labels = {
            "codice": "Codice",
            "descrizione": "Descrizione",
            "categoria": "Categoria",
            "unita_misura": "Unità di misura",
            "scorta_minima": "Scorta minima",
            "criterio_rotazione": "Criterio rotazione",
            "tipo_packaging": "Tipo packaging",
            "pezzi_per_imballo": "Pezzi per imballo",
            "prodotto_finito_collegato": "Prodotto finito collegato",
            "attivo": "Articolo attivo",
            "note": "Note",
        }
