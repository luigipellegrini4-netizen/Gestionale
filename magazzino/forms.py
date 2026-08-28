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
    TankProduzione,
    NonConformitaLotto,
)

from datetime import date

from decimal import Decimal, ROUND_HALF_UP

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
        decimal_places=6,
        min_value=Decimal("0.000001"),
        label="Quantità totale del lotto",
    )

    numero_colli = forms.IntegerField(
        min_value=1,
        required=False,
        label="Numero di colli",
        help_text=(
            "Compilare almeno due dei tre campi: colli, unità per collo e peso UDA. "
            "Il valore mancante sarà calcolato automaticamente."
        ),
    )

    unita_acquisto_per_collo = forms.IntegerField(
        min_value=1,
        required=False,
        label="Numero di unità di acquisto per collo",
        help_text=(
            "Inserire 1 quando il collo coincide con l'unità di acquisto."
        ),
    )

    peso_unita_acquisto = forms.DecimalField(
        max_digits=12,
        decimal_places=6,
        min_value=Decimal("0.000001"),
        required=False,
        label="Peso della singola unità di acquisto (kg)",
    )

    fattura = forms.CharField(
        max_length=100,
        required=False,
        label="Numero fattura",
    )

    ddt = forms.CharField(
        max_length=100,
        required=False,
        label="Numero DDT",
        help_text="È obbligatorio compilare almeno Fattura oppure DDT.",
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


    def clean(self):
        cleaned_data = super().clean()
        errori = []
        fattura = (cleaned_data.get("fattura") or "").strip()
        ddt = (cleaned_data.get("ddt") or "").strip()
        cleaned_data["fattura"] = fattura
        cleaned_data["ddt"] = ddt
        if not fattura and not ddt:
            errori.append(
                "Inserire almeno un documento di acquisto: Fattura oppure DDT."
            )

        quantita = cleaned_data.get("quantita")
        numero_colli = cleaned_data.get("numero_colli")
        uda_per_collo = cleaned_data.get("unita_acquisto_per_collo")
        peso_uda = cleaned_data.get("peso_unita_acquisto")
        valori_presenti = sum(
            valore is not None
            for valore in (numero_colli, uda_per_collo, peso_uda)
        )

        if quantita is not None and valori_presenti < 2:
            errori.append(
                "Compilare almeno due campi tra numero di colli, numero di "
                "unità di acquisto per collo e peso della singola UDA."
            )
        elif quantita is not None and valori_presenti == 2:
            if numero_colli is None:
                valore = quantita / (Decimal(uda_per_collo) * peso_uda)
                intero = valore.to_integral_value()
                if valore != intero:
                    errori.append(
                        "Il numero di colli calcolato non è un numero intero. "
                        "Controllare i dati inseriti."
                    )
                else:
                    cleaned_data["numero_colli"] = int(intero)
            elif uda_per_collo is None:
                valore = quantita / (Decimal(numero_colli) * peso_uda)
                intero = valore.to_integral_value()
                if valore != intero:
                    errori.append(
                        "Il numero di unità di acquisto per collo calcolato non "
                        "è un numero intero. Controllare i dati inseriti."
                    )
                else:
                    cleaned_data["unita_acquisto_per_collo"] = int(intero)
            else:
                cleaned_data["peso_unita_acquisto"] = (
                    quantita / (Decimal(numero_colli) * Decimal(uda_per_collo))
                ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        elif quantita is not None and valori_presenti == 3:
            quantita_calcolata = (
                Decimal(numero_colli) * Decimal(uda_per_collo) * peso_uda
            )
            if abs(quantita_calcolata - quantita) > Decimal("0.000001"):
                errori.append(
                    "Numero di colli, unità di acquisto per collo e peso della "
                    "singola UDA non sono coerenti con la quantità totale."
                )

        if errori:
            raise forms.ValidationError(errori)
        return cleaned_data


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
        initial="Scarico materiale di consumo",
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


class GiacenzaNonConformitaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, giacenza):
        posizione = giacenza.ubicazione.nome
        if giacenza.scaffale:
            posizione += f" · Scaffale {giacenza.scaffale}"
        if giacenza.piano:
            posizione += f" · Piano {giacenza.piano}"
        return f"{posizione} — disponibile {giacenza.quantita}"


class AperturaNonConformitaLottoForm(forms.Form):
    ambito = forms.ChoiceField(
        choices=NonConformitaLotto.Ambito.choices,
        label="Segnalata in",
    )
    tipo_nc = forms.ChoiceField(
        choices=NonConformitaLotto.Tipo.choices,
        label="Tipo di non conformità",
    )
    giacenza = GiacenzaNonConformitaChoiceField(
        queryset=Giacenza.objects.none(),
        label="Posizione da cui prelevare le UDA",
    )
    numero_uda = forms.IntegerField(
        min_value=1,
        label="Numero di UDA da mettere in quarantena",
    )
    motivo = forms.CharField(
        label="Motivo della non conformità",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    note = forms.CharField(
        required=False,
        label="Note di apertura",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, lotto, **kwargs):
        super().__init__(*args, **kwargs)
        self.lotto = lotto
        self.fields["giacenza"].queryset = (
            Giacenza.objects.filter(lotto=lotto, quantita__gt=0)
            .select_related("ubicazione")
            .order_by("ubicazione__nome", "scaffale", "piano")
        )

    def clean(self):
        cleaned_data = super().clean()
        giacenza = cleaned_data.get("giacenza")
        numero_uda = cleaned_data.get("numero_uda")
        quantita_per_uda = self.lotto.quantita_singola_uda
        if quantita_per_uda is None:
            raise forms.ValidationError(
                "Il lotto non ha la quantità della singola UDA registrata e non "
                "può essere messo in quarantena per numero di UDA."
            )
        if giacenza and numero_uda:
            quantita = Decimal(numero_uda) * quantita_per_uda
            if quantita > giacenza.quantita:
                self.add_error(
                    "numero_uda",
                    "Le UDA richieste superano la giacenza disponibile nella "
                    "posizione selezionata.",
                )
        return cleaned_data


class GestioneNonConformitaLottoForm(forms.Form):
    analisi_cause = forms.CharField(
        required=False,
        label="Analisi delle cause",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    azione_risoluzione = forms.CharField(
        required=False,
        label="Azione intrapresa per la risoluzione",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    responsabile_azione = forms.CharField(
        max_length=200,
        required=False,
        label="Responsabilità",
    )
    data_inizio_gestione = forms.DateField(
        required=False,
        label="Data inizio gestione AC",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    azione_immediata = forms.BooleanField(
        required=False,
        label="Tempi previsti: azione immediata",
        help_text=(
            "Se l'azione non è immediata, lasciare deselezionato e indicare "
            "la data nel campo seguente."
        ),
    )
    scadenza_prevista = forms.DateField(
        required=False,
        label="Tempi previsti: oppure entro il",
        help_text="Compilare questo campo in alternativa ad Azione immediata.",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    numero_uda_scartate = forms.IntegerField(
        min_value=0,
        required=False,
        label="Numero di UDA da scartare",
    )
    numero_uda_reintegrate = forms.IntegerField(
        min_value=0,
        required=False,
        label="Numero di UDA da reintegrare",
    )
    decisione = forms.CharField(
        required=False,
        label="Decisione sulle UDA in quarantena",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    esito_efficacia = forms.ChoiceField(
        required=False,
        choices=NonConformitaLotto.EsitoEfficacia.choices,
        label="Verifica efficacia",
    )
    verifica_efficacia = forms.CharField(
        required=False,
        label="Descrizione della verifica di efficacia",
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    data_verifica = forms.DateField(
        required=False,
        label="Data verifica",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, non_conformita, **kwargs):
        super().__init__(*args, **kwargs)
        self.non_conformita = non_conformita

    def clean(self):
        cleaned_data = super().clean()
        scartate = cleaned_data.get("numero_uda_scartate")
        reintegrate = cleaned_data.get("numero_uda_reintegrate")
        if (
            self.data.get("azione") == "chiudi"
            and self.non_conformita.numero_uda_quarantena
        ):
            if scartate is None or reintegrate is None:
                raise forms.ValidationError(
                    "Indicare quante UDA scartare e quante reintegrare."
                )
            if scartate + reintegrate != self.non_conformita.numero_uda_quarantena:
                raise forms.ValidationError(
                    "La somma delle UDA scartate e reintegrate deve coincidere "
                    f"con le {self.non_conformita.numero_uda_quarantena} UDA "
                    "in quarantena."
                )
        if self.data.get("azione") == "chiudi":
            obbligatori = {
                "analisi_cause": "Compilare l'analisi delle cause.",
                "azione_risoluzione": "Compilare l'azione intrapresa.",
                "responsabile_azione": "Indicare il responsabile dell'azione.",
                "data_inizio_gestione": "Indicare la data di inizio gestione.",
                "esito_efficacia": "Indicare l'esito della verifica.",
                "verifica_efficacia": "Descrivere la verifica di efficacia.",
                "data_verifica": "Indicare la data della verifica.",
            }
            for campo, messaggio in obbligatori.items():
                if not cleaned_data.get(campo):
                    self.add_error(campo, messaggio)
            if not cleaned_data.get("azione_immediata") and not cleaned_data.get(
                "scadenza_prevista"
            ):
                self.add_error(
                    "scadenza_prevista",
                    "Indicare una scadenza oppure selezionare Azione immediata.",
                )
        return cleaned_data


class AperturaNonConformitaGeneraleForm(forms.ModelForm):
    ricerca_lotto = forms.CharField(
        required=False,
        label="Cerca lotto",
        help_text="Cerca per codice lotto, codice articolo o descrizione.",
        widget=forms.TextInput(attrs={"autocomplete": "off"}),
    )
    lotto = forms.ModelChoiceField(
        queryset=Lotto.objects.none(),
        required=False,
        label="Lotto coinvolto (facoltativo)",
        empty_label="Nessun lotto selezionato",
    )
    giacenza = GiacenzaNonConformitaChoiceField(
        queryset=Giacenza.objects.none(),
        required=False,
        label="Posizione da mettere in quarantena",
    )
    numero_uda = forms.IntegerField(
        min_value=1,
        required=False,
        label="Numero di UDA da mettere in quarantena",
    )

    class Meta:
        model = NonConformitaLotto
        fields = [
            "ambito", "tipo_nc", "ricerca_lotto", "lotto", "giacenza",
            "numero_uda", "motivo", "note_apertura",
        ]
        labels = {
            "ambito": "Segnalata in",
            "tipo_nc": "Tipo di non conformità",
            "lotto": "Lotto coinvolto (facoltativo)",
            "motivo": "Descrizione della non conformità",
            "note_apertura": "Trattamento immediato",
        }
        widgets = {
            "motivo": forms.Textarea(attrs={"rows": 5}),
            "note_apertura": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lotto_id = self.data.get("lotto") if self.is_bound else None
        if lotto_id and str(lotto_id).isdigit():
            self.fields["lotto"].queryset = Lotto.objects.filter(pk=lotto_id)
            self.fields["giacenza"].queryset = (
                Giacenza.objects.filter(lotto_id=lotto_id, quantita__gt=0)
                .select_related("ubicazione", "lotto__articolo")
                .order_by("ubicazione__nome", "scaffale", "piano")
            )

    def clean(self):
        cleaned_data = super().clean()
        lotto = cleaned_data.get("lotto")
        giacenza = cleaned_data.get("giacenza")
        numero_uda = cleaned_data.get("numero_uda")
        if lotto:
            if giacenza is None:
                self.add_error(
                    "giacenza",
                    "Selezionare la posizione delle UDA da mettere in quarantena.",
                )
            if numero_uda is None:
                self.add_error(
                    "numero_uda",
                    "Indicare il numero di UDA da mettere in quarantena.",
                )
            if lotto.quantita_singola_uda is None:
                self.add_error(
                    "lotto",
                    "Il lotto non ha la quantità della singola UDA registrata.",
                )
            elif giacenza and numero_uda:
                quantita = Decimal(numero_uda) * lotto.quantita_singola_uda
                if quantita > giacenza.quantita:
                    self.add_error(
                        "numero_uda",
                        "Le UDA superano la giacenza disponibile nella posizione.",
                    )
        elif giacenza or numero_uda:
            raise forms.ValidationError(
                "Se sono indicate UDA in quarantena è necessario selezionare il lotto."
            )
        return cleaned_data


class ArticoloProduzioneChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, articolo):
        return f"{articolo.codice} - {articolo.nome_per_produzione}"


class RicettaForm(forms.ModelForm):

    tipo_prodotto = forms.ChoiceField(
        choices=[
            ("", "Seleziona il tipo di prodotto"),
            (Articolo.Categoria.SEMILAVORATO, "Semilavorati"),
            (Articolo.Categoria.PRODOTTO_FINITO, "Prodotti finiti"),
        ],
        label="Tipo di prodotto",
    )


    articolo = ArticoloProduzioneChoiceField(
        queryset=Articolo.objects.none(),
        label="Prodotto",
    )

    class Meta:
        model = Ricetta

        fields = [
            "tipo_prodotto",
            "articolo",
            "nome",
            "attiva",
            "note",
        ]

        labels = {
            "articolo": "Prodotto",
            "nome": "Nome ricetta",
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
        tipo = (
            self.data.get(self.add_prefix("tipo_prodotto"))
            if self.is_bound
            else None
        )
        if self.instance.pk:
            tipo = tipo or self.instance.articolo.categoria
            self.fields["tipo_prodotto"].initial = tipo
        else:
            tipo = tipo or self.initial.get("tipo_prodotto")

        categorie_ammesse = {
            Articolo.Categoria.SEMILAVORATO,
            Articolo.Categoria.PRODOTTO_FINITO,
        }
        queryset = Articolo.objects.none()
        if tipo in categorie_ammesse:
            queryset = Articolo.objects.filter(
                attivo=True,
                categoria=tipo,
            ).order_by("codice")
        self.fields["articolo"].queryset = queryset

        if self.instance.pk:
            self.fields["tipo_prodotto"].disabled = True
            self.fields["articolo"].disabled = True

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

    def save(self, commit=True):
        nuova = self.instance.pk is None
        ricetta = super().save(commit=False)
        if nuova:
            versioni = Ricetta.objects.filter(
                articolo=ricetta.articolo,
            ).values_list("versione", flat=True)
            versioni_numeriche = [
                int(versione)
                for versione in versioni
                if str(versione).isdigit()
            ]
            ricetta.versione = str(max(versioni_numeriche, default=0) + 1)
        if commit:
            ricetta.save()
            self.save_m2m()
        return ricetta


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
            "quantita": "Quantità per 1 batch",
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
        label="Data di inizio produzione",
        initial=date.today,
        widget=forms.DateInput(
            attrs={
                "type": "date",
            },
        ),
    )

    numero_batch_previsti = forms.IntegerField(
        min_value=1,
        label="Numero di batch da produrre",
        help_text="Indica il totale previsto: può essere anche 15, 20, 30 o più.",
    )

    lotto_provvisorio = forms.CharField(
        required=False,
        max_length=50,
        label="Numero lotto provvisorio",
        help_text="Se lasciato vuoto, MIRA propone il giorno successivo alla data di inizio.",
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
        initial=5,
        label="Numero di batch",
        help_text="Numero di cicli Robocubo destinati al tank.",
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


class BatchProduzioneForm(forms.Form):
    ora_inizio = forms.TimeField(label="Ora inizio", widget=forms.TimeInput(attrs={"type": "time"}))
    ora_fine = forms.TimeField(label="Ora fine", widget=forms.TimeInput(attrs={"type": "time"}))
    esito_conformita = forms.ChoiceField(
        label="Tracciato di conformità 82 °C × 60 secondi",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
    note = forms.CharField(required=False, label="Note", widget=forms.Textarea(attrs={"rows": 2}))

    def clean(self):
        dati = super().clean()
        if dati.get("ora_inizio") and dati.get("ora_fine") and dati["ora_fine"] < dati["ora_inizio"]:
            raise forms.ValidationError("L'ora di fine non può precedere l'ora di inizio.")
        return dati


class TankInvasettamentoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"Tank {obj.numero}"


class CarrelloProduzioneForm(forms.Form):
    tank = TankInvasettamentoChoiceField(
        queryset=TankProduzione.objects.none(),
        label="Tank da invasettare",
        empty_label="Seleziona il tank",
    )
    numero_pezzi = forms.IntegerField(min_value=1, initial=500, label="Numero vasetti nel carrello")
    esito_pastorizzazione = forms.ChoiceField(
        label="2ª pastorizzazione: 71 °C × 4 minuti",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
    note_pastorizzazione = forms.CharField(required=False, label="Note pastorizzazione", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, produzione=None, **kwargs):
        super().__init__(*args, **kwargs)
        if produzione is not None:
            self.fields["tank"].queryset = produzione.tank.filter(
                annullato=False, data_ora_controlli__isnull=False,
                carrelli__isnull=True,
            ).order_by("numero")


class ChiusuraCarrelloForm(forms.Form):
    esito_shock_vuoto = forms.ChoiceField(
        label="Shock termico e presenza vuoto",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
    pezzi_difettosi = forms.IntegerField(min_value=0, initial=0, label="N° pezzi difettosi")
    capsule_difettose = forms.IntegerField(min_value=0, initial=0, label="N° capsule difettose")
    note_shock_vuoto = forms.CharField(required=False, label="Note shock termico / vuoto", widget=forms.Textarea(attrs={"rows": 2}))


class ModificaTankForm(forms.ModelForm):
    class Meta:
        model = TankProduzione
        fields = ["numero_batch", "gradi_brix", "ph"]
        labels = {
            "numero_batch": "Numero di batch",
            "gradi_brix": "Gradi Brix",
            "ph": "pH",
        }

    def clean(self):
        cleaned_data = super().clean()
        brix = cleaned_data.get("gradi_brix")
        ph = cleaned_data.get("ph")
        if (brix is None) != (ph is None):
            raise forms.ValidationError("Gradi Brix e pH devono essere compilati insieme.")
        return cleaned_data


class AnnullaTankForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo dell'annullamento",
        min_length=3,
        widget=forms.Textarea(attrs={"rows": 4}),
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
    lotto_definitivo = forms.CharField(
        max_length=50, label="Numero lotto definitivo",
        help_text="Conferma o modifica il numero provvisorio.",
    )
    quantita_ottenuta_kg = forms.DecimalField(
        max_digits=12,
        decimal_places=3,
        min_value=0.001,
        label="Quantità effettiva ottenuta (kg)",
        help_text="Peso netto disponibile per l'invasettamento.",
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
            "formato",
            "unita_formato",
            "scorta_minima",
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
            "quantita_per_confezione": "Unità per confezione di acquisto",
            "formato": "Formato del singolo articolo",
            "unita_formato": "Unità del formato",
            "scorta_minima": "Scorta minima",
            "tipo_packaging": "Tipo packaging",
            "pezzi_per_imballo": "Confezioni per imballo",
            "attivo": "Articolo attivo",
            "note": "Note",
        }

        help_texts = {
            "quantita_per_confezione": (
                "Quantità di unità contenute nella confezione di acquisto. "
                "Esempio: 10 vasetti oppure 25 kg per confezione."
            ),
            "formato": "Esempio: 250 con unità g per un vasetto da 250 g.",
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

    def clean(self):
        cleaned_data = super().clean()
        formato = cleaned_data.get("formato")
        unita_formato = cleaned_data.get("unita_formato")
        if formato is not None and formato <= 0:
            self.add_error("formato", "Il formato deve essere maggiore di zero.")
        if (formato is None) != (not unita_formato):
            raise forms.ValidationError(
                "Formato e unità del formato devono essere compilati insieme."
            )
        return cleaned_data


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
