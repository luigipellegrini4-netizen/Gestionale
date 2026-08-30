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
    Produzione,
    BatchProduzione,
    CarrelloProduzione,
    NonConformitaLotto,
    MaterialeSospesoNonConformita,
)

from datetime import date, timedelta

from decimal import Decimal, ROUND_HALF_UP

class CaricoLottoForm(forms.Form):

    ricerca_articolo = forms.CharField(
        required=False,
        label="Cerca articolo",
        widget=forms.TextInput(attrs={"placeholder": "Codice o descrizione"}),
    )

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
        required=False,
        help_text="Obbligatorio solo per gli articoli con tracciabilità per lotto.",
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

    capacita_imballo = forms.IntegerField(
        min_value=1,
        required=False,
        label="Capacità del singolo imballo",
        help_text="Solo per scatole e cofanetti: numero di prodotti contenuti.",
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


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ricerca = (self.data.get("ricerca_articolo") or "").strip()
        if ricerca:
            self.fields["articolo"].queryset = self.fields["articolo"].queryset.filter(
                Q(codice__icontains=ricerca) | Q(descrizione__icontains=ricerca)
            )

    def clean(self):
        cleaned_data = super().clean()
        errori = []
        fattura = (cleaned_data.get("fattura") or "").strip()
        ddt = (cleaned_data.get("ddt") or "").strip()
        articolo = cleaned_data.get("articolo")
        codice_lotto = (cleaned_data.get("codice_lotto") or "").strip()
        cleaned_data["codice_lotto"] = codice_lotto
        if articolo is not None and articolo.tracciabilita_lotto and not codice_lotto:
            self.add_error("codice_lotto", "Il codice lotto è obbligatorio per questo articolo.")
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
        capacita_imballo = cleaned_data.get("capacita_imballo")
        if (
            articolo is not None
            and articolo.tipo_packaging in {
                Articolo.TipoPackaging.SCATOLA,
                Articolo.TipoPackaging.COFANETTO,
            }
            and capacita_imballo is None
        ):
            self.add_error(
                "capacita_imballo",
                "Indicare quanti prodotti contiene la singola scatola o il cofanetto.",
            )
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

    ricerca_articolo = forms.CharField(
        required=False,
        label="Cerca articolo",
        widget=forms.TextInput(attrs={"placeholder": "Codice o descrizione"}),
    )

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
        ricerca = (self.data.get("ricerca_articolo") or "").strip()
        if ricerca:
            self.fields["articolo"].queryset = self.fields["articolo"].queryset.filter(
                Q(codice__icontains=ricerca) | Q(descrizione__icontains=ricerca)
            )
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

    ricerca_lotto = forms.CharField(
        required=False,
        label="Cerca lotto",
        widget=forms.TextInput(
            attrs={"placeholder": "Codice lotto, codice o descrizione articolo"},
        ),
    )

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


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ricerca = (self.data.get("ricerca_lotto") or "").strip()
        if ricerca:
            self.fields["lotto"].queryset = self.fields["lotto"].queryset.filter(
                Q(codice_lotto__icontains=ricerca)
                | Q(articolo__codice__icontains=ricerca)
                | Q(articolo__descrizione__icontains=ricerca)
            )


class GiacenzaRettificaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, giacenza):
        posizione = giacenza.ubicazione.nome
        if giacenza.scaffale:
            posizione += f" · Scaffale {giacenza.scaffale}"
        if giacenza.piano:
            posizione += f" · Piano {giacenza.piano}"
        return (
            f"{giacenza.lotto.articolo.codice} · lotto "
            f"{giacenza.lotto.codice_visualizzato} · {posizione} · "
            f"teorico {giacenza.quantita} {giacenza.lotto.articolo.unita_misura}"
        )


class RettificaInventarioForm(forms.Form):
    ricerca_lotto = forms.CharField(
        required=False,
        label="Cerca lotto",
        widget=forms.TextInput(
            attrs={"placeholder": "Codice lotto, codice o descrizione articolo"},
        ),
    )
    giacenza = GiacenzaRettificaChoiceField(
        queryset=Giacenza.objects.select_related(
            "lotto__articolo", "ubicazione",
        ).order_by("lotto__articolo__codice", "lotto__codice_lotto", "ubicazione__nome"),
        label="Lotto e posizione da rettificare",
    )
    quantita_reale = forms.DecimalField(
        max_digits=12,
        decimal_places=6,
        min_value=Decimal("0"),
        label="Quantità reale rilevata",
    )
    motivo = forms.CharField(max_length=200, label="Motivo della rettifica")
    note = forms.CharField(
        required=False,
        label="Note",
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ricerca = (self.data.get("ricerca_lotto") or "").strip()
        if ricerca:
            self.fields["giacenza"].queryset = self.fields["giacenza"].queryset.filter(
                Q(lotto__codice_lotto__icontains=ricerca)
                | Q(lotto__articolo__codice__icontains=ricerca)
                | Q(lotto__articolo__descrizione__icontains=ricerca)
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
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
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
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )
    quantita_scartata = forms.DecimalField(
        min_value=Decimal("0"), max_digits=12, decimal_places=6,
        required=False,
        label="Quantità da scartare",
    )
    quantita_reintegrata = forms.DecimalField(
        min_value=Decimal("0"), max_digits=12, decimal_places=6,
        required=False,
        label="Quantità da reintegrare",
    )
    decisione = forms.CharField(
        required=False,
        label="Motivazione della decisione sulla quarantena",
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
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
    )

    def __init__(self, *args, non_conformita, **kwargs):
        super().__init__(*args, **kwargs)
        self.non_conformita = non_conformita
        unita_nc = non_conformita.unita_quarantena or (
            "UDA" if non_conformita.numero_uda_quarantena else
            non_conformita.lotto.articolo.unita_misura if non_conformita.lotto_id else ""
        )
        self.fields["quantita_scartata"].label = f"Quantità da scartare ({unita_nc})"
        self.fields["quantita_reintegrata"].label = f"Quantità da reintegrare ({unita_nc})"
        if not self.is_bound:
            oggi = date.today()
            for nome_data in ("data_inizio_gestione", "data_verifica"):
                if not self.initial.get(nome_data):
                    self.initial[nome_data] = oggi
        self.chiavi_materiali = {}
        self.righe_materiali = []
        self.campo_esito_batch = None
        self.mostra_scadenza_materiali = not non_conformita.produzioni_bloccate.exists()
        if non_conformita.batch_id:
            self.fields["esito_batch"] = forms.ChoiceField(
                required=False,
                label=f"Decisione sul batch {non_conformita.batch.numero}",
                choices=(("", "Seleziona"), ("SCARTA", "Scarta il batch"), ("REINTEGRA", "Reintegra il batch")),
            )
            materiali = list(non_conformita.materiali_sospesi.select_related(
                "prelievo__lotto__articolo"
            ))
            primi_per_miscela = {}
            for materiale in materiali:
                if materiale.descrizione_miscela:
                    primi_per_miscela.setdefault(materiale.descrizione_miscela, materiale.pk)
            campi_aggiunti = set()
            for materiale in materiali:
                suffisso = str(
                    primi_per_miscela.get(materiale.descrizione_miscela, materiale.pk)
                    if materiale.descrizione_miscela else materiale.pk
                )
                self.chiavi_materiali[materiale.pk] = suffisso
                if suffisso in campi_aggiunti:
                    continue
                campi_aggiunti.add(suffisso)
                articolo = materiale.prelievo.lotto.articolo
                etichetta_materiale = materiale.descrizione_miscela or f"{articolo.codice} — {articolo.descrizione}"
                quantita_etichetta = materiale.quantita
                if materiale.descrizione_miscela:
                    quantita_etichetta = sum(
                        (m.quantita for m in materiali if m.descrizione_miscela == materiale.descrizione_miscela),
                        Decimal("0"),
                    )
                self.fields[f"materiale_esito_{suffisso}"] = forms.ChoiceField(
                    required=False,
                    label=f"{etichetta_materiale} ({quantita_etichetta} {articolo.unita_misura})",
                    choices=(
                        ("", "Seleziona"),
                        (MaterialeSospesoNonConformita.Esito.RIUTILIZZA, "Reintegro"),
                        (MaterialeSospesoNonConformita.Esito.SCARTA, "Scarto"),
                    ),
                    initial=materiale.esito,
                )
                if self.mostra_scadenza_materiali:
                    self.fields[f"materiale_scadenza_{suffisso}"] = forms.DateField(
                        required=False,
                        label=f"Nuova scadenza {articolo.codice}",
                        initial=date.today() + timedelta(days=7),
                        widget=forms.DateInput(attrs={"type": "date"}),
                    )
                self.fields[f"materiale_note_{suffisso}"] = forms.CharField(
                    required=False,
                    label=f"Note {articolo.codice}",
                    initial=materiale.note,
                )
                self.righe_materiali.append({
                    "ingrediente": etichetta_materiale,
                    "quantita": quantita_etichetta,
                    "unita_misura": articolo.unita_misura,
                    "decisione": self[f"materiale_esito_{suffisso}"],
                    "scadenza": (
                        self[f"materiale_scadenza_{suffisso}"]
                        if self.mostra_scadenza_materiali else None
                    ),
                    "note": self[f"materiale_note_{suffisso}"],
                })
            self.campo_esito_batch = self["esito_batch"]
        nomi_generali = (
            "analisi_cause", "azione_risoluzione", "responsabile_azione",
            "data_inizio_gestione", "azione_immediata", "scadenza_prevista",
            "decisione", "esito_efficacia", "verifica_efficacia", "data_verifica",
        )
        self.campi_generali = [self[nome] for nome in nomi_generali]

    def clean(self):
        cleaned_data = super().clean()
        scartate = cleaned_data.get("quantita_scartata")
        reintegrate = cleaned_data.get("quantita_reintegrata")
        if (
            self.data.get("azione") == "chiudi"
            and self.non_conformita.quantita_quarantena
        ):
            if scartate is None or reintegrate is None:
                raise forms.ValidationError(
                    "Indicare la quantità da scartare e quella da reintegrare."
                )
            totale = (
                Decimal(self.non_conformita.numero_uda_quarantena)
                if (self.non_conformita.unita_quarantena or "UDA") == "UDA"
                else self.non_conformita.quantita_quarantena
            )
            if scartate + reintegrate != totale:
                raise forms.ValidationError(
                    "La somma delle quantità scartata e reintegrata deve "
                    f"coincidere con la quantità in quarantena ({totale})."
                )
            if (self.non_conformita.unita_quarantena or "UDA") == "UDA":
                if scartate != scartate.to_integral_value() or reintegrate != reintegrate.to_integral_value():
                    raise forms.ValidationError("Le quantità espresse in UDA devono essere numeri interi.")
        if self.data.get("azione") == "chiudi":
            if self.non_conformita.batch_id and not cleaned_data.get("esito_batch"):
                self.add_error("esito_batch", "Indicare la decisione sul batch non conforme.")
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
        label="Posizione da mettere in quarantena (facoltativa)",
        empty_label="Nessuna posizione selezionata",
    )
    unita_quarantena = forms.ChoiceField(
        required=False,
        choices=(("", "Seleziona"), ("UDA", "UDA"), ("KG", "kg")),
        label="Unità della quarantena",
    )
    quantita_quarantena_input = forms.DecimalField(
        min_value=Decimal("0.000001"), decimal_places=6, max_digits=12,
        required=False,
        label="Quantità da mettere in quarantena",
    )

    class Meta:
        model = NonConformitaLotto
        fields = [
            "ambito", "tipo_nc", "ricerca_lotto", "lotto", "giacenza",
            "unita_quarantena", "quantita_quarantena_input", "motivo", "note_apertura",
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
        unita = cleaned_data.get("unita_quarantena")
        quantita_input = cleaned_data.get("quantita_quarantena_input")
        if lotto and (unita or quantita_input):
            if giacenza is None or not unita or quantita_input is None:
                raise forms.ValidationError(
                    "Per la quarantena occorre indicare posizione, unità e quantità. "
                    "In alternativa lasciare vuoti unità e quantità; la posizione "
                    "può essere registrata da sola."
                )
            if unita == "UDA" and lotto.quantita_singola_uda is None:
                self.add_error(
                    "lotto",
                    "Il lotto non ha la quantità della singola UDA registrata.",
                )
            elif unita == "UDA" and quantita_input != quantita_input.to_integral_value():
                self.add_error(
                    "quantita_quarantena_input",
                    "Il numero di UDA deve essere un numero intero.",
                )
            elif unita == "KG" and lotto.articolo.unita_misura != Articolo.UnitaMisura.KG:
                self.add_error(
                    "unita_quarantena",
                    "I kg possono essere usati solo per un articolo gestito in kilogrammi.",
                )
            else:
                quantita = (
                    quantita_input * lotto.quantita_singola_uda
                    if unita == "UDA" else quantita_input
                )
                if quantita > giacenza.quantita:
                    self.add_error(
                        "quantita_quarantena_input",
                        "La quantità supera la giacenza disponibile nella posizione.",
                    )
        elif not lotto and (giacenza or unita or quantita_input):
            raise forms.ValidationError(
                "Se è indicata una quantità in quarantena è necessario selezionare il lotto."
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

    ricetta_base = forms.ModelChoiceField(
        queryset=Ricetta.objects.select_related("articolo").order_by(
            "articolo__descrizione", "-id",
        ),
        required=False,
        label="Usa una ricetta come base",
        empty_label="Nessuna: crea una ricetta vuota",
        help_text="Gli ingredienti e i materiali saranno copiati e potranno essere modificati senza cambiare la ricetta originale.",
    )

    class Meta:
        model = Ricetta

        fields = [
            "tipo_prodotto",
            "articolo",
            "ricetta_base",
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
            self.fields.pop("ricetta_base", None)
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
        min_value=40,
        max_value=45,
        max_digits=5,
        decimal_places=2,
        label="Gradi Brix (da 40 a 45, estremi inclusi)",
    )
    ph = forms.DecimalField(
        min_value=0,
        max_value=4.1,
        max_digits=4,
        decimal_places=2,
        label="pH (massimo 4,1 incluso)",
    )


class BatchProduzioneForm(forms.Form):
    ora_inizio = forms.TimeField(
        required=False, label="Ora inizio",
        help_text="Facoltativa soltanto se il batch è non conforme.",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    ora_fine = forms.TimeField(
        required=False, label="Ora fine",
        help_text="Facoltativa soltanto se il batch è non conforme.",
        widget=forms.TimeInput(attrs={"type": "time"}),
    )
    esito_conformita = forms.ChoiceField(
        label="Tracciato di conformità 82 °C × 60 secondi",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
    note = forms.CharField(required=False, label="Note", widget=forms.Textarea(attrs={"rows": 2}))
    produzione_puo_proseguire = forms.ChoiceField(
        required=False,
        label="La produzione può proseguire con i batch successivi?",
        choices=(("", "Seleziona"), ("SI", "Sì"), ("NO", "No, sospendi la fase RoboQbo")),
        help_text="Obbligatorio quando il tracciato del batch è non conforme.",
    )

    def clean(self):
        dati = super().clean()
        esito = dati.get("esito_conformita")
        inizio = dati.get("ora_inizio")
        fine = dati.get("ora_fine")
        if esito != "NC" and (inizio is None or fine is None):
            raise forms.ValidationError(
                "Ora di inizio e ora di fine sono obbligatorie per un batch conforme o non applicabile."
            )
        if esito == "NC" and ((inizio is None) != (fine is None)):
            raise forms.ValidationError(
                "Per un batch non conforme indica entrambi gli orari oppure lasciali entrambi vuoti."
            )
        if inizio and fine and fine < inizio:
            raise forms.ValidationError("L'ora di fine non può precedere l'ora di inizio.")
        if dati.get("esito_conformita") == "NC" and not dati.get("produzione_puo_proseguire"):
            self.add_error(
                "produzione_puo_proseguire",
                "Indicare se la produzione può proseguire.",
            )
        if dati.get("esito_conformita") != "NC":
            dati.pop("produzione_puo_proseguire", None)
        return dati


class CarrelloProduzioneForm(forms.Form):
    esito_pastorizzazione = forms.ChoiceField(
        label="2ª pastorizzazione: 71 °C × 4 minuti",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
    note_pastorizzazione = forms.CharField(required=False, label="Note pastorizzazione", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, produzione=None, **kwargs):
        super().__init__(*args, **kwargs)

class ChiusuraCarrelloForm(forms.Form):
    esito_shock_vuoto = forms.ChoiceField(
        label="Shock termico e presenza vuoto",
        choices=(("C", "C - Conforme"), ("NC", "NC - Non conforme"), ("NA", "NA - Non applicabile")),
        widget=forms.RadioSelect(attrs={"class": "control-options"}),
    )
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
        help_text="Proposto automaticamente dalla data odierna; puoi modificarlo.",
    )
    lotto_proposto_originale = forms.CharField(required=False, widget=forms.HiddenInput)
    quantita_prodotta = forms.IntegerField(
        min_value=1,
        label="Numero di vasetti prodotti buoni",
    )
    peso_netto_vasetto_g = forms.DecimalField(
        max_digits=10,
        decimal_places=3,
        min_value=0.001,
        label="Peso netto del singolo vasetto (g)",
        help_text="MIRA calcola: vasetti buoni × peso netto ÷ 1.000.",
    )
    pezzi_difettosi_finali = forms.IntegerField(
        min_value=0, initial=0, label="Numero di vasetti da scartare",
    )
    capsule_difettose_finali = forms.IntegerField(
        min_value=0, initial=0, label="N° capsule difettose complessive",
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

    def clean(self):
        dati = super().clean()
        vasetti = dati.get("quantita_prodotta")
        scarti = dati.get("pezzi_difettosi_finali")
        peso = dati.get("peso_netto_vasetto_g")
        if vasetti is not None and scarti is not None and peso is not None:
            dati["quantita_ottenuta_kg"] = (
                Decimal(vasetti + scarti) * peso / Decimal("1000")
            )
        return dati


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
            "scorta_minima",
            "tipo_packaging",
            "attivo",
            "tracciabilita_lotto",
            "note",
        ]

        labels = {
            "codice": "Codice",
            "descrizione": "Descrizione",
            "nome_produzione": "Nome prodotto in ricette e produzione",
            "categoria": "Categoria",
            "unita_misura": "Unità di misura",
            "scorta_minima": "Scorta minima",
            "tipo_packaging": "Tipo packaging",
            "attivo": "Articolo attivo",
            "tracciabilita_lotto": "Tracciabilità per lotto",
            "note": "Note",
        }

        help_texts = {
        }

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
            "attiva",
        ]
        labels = {
            "nome": "Nome",
            "tipo_magazzino": "Tipo magazzino",
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


class ModificaProduzioneForm(forms.ModelForm):
    class Meta:
        model = Produzione
        fields = ["data_produzione", "numero_batch_previsti", "lotto_provvisorio", "note"]
        labels = {
            "data_produzione": "Data di inizio produzione",
            "numero_batch_previsti": "Numero batch previsti",
            "lotto_provvisorio": "Lotto provvisorio",
            "note": "Note preparazione",
        }
        widgets = {
            "data_produzione": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }


class ModificaBatchProduzioneForm(forms.ModelForm):
    class Meta:
        model = BatchProduzione
        fields = [
            "ora_inizio", "ora_fine", "temperatura_conformita",
            "durata_conformita_secondi", "esito_conformita", "note",
        ]
        widgets = {
            "ora_inizio": forms.TimeInput(attrs={"type": "time"}),
            "ora_fine": forms.TimeInput(attrs={"type": "time"}),
            "esito_conformita": forms.RadioSelect(attrs={"class": "control-options"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        dati = super().clean()
        if dati.get("ora_inizio") and dati.get("ora_fine") and dati["ora_fine"] < dati["ora_inizio"]:
            raise forms.ValidationError("L'ora di fine non può precedere l'ora di inizio.")
        return dati


class ModificaCarrelloProduzioneForm(forms.ModelForm):
    pastorizzazione_registrata_il = forms.DateTimeField(
        label="Data e ora seconda pastorizzazione",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )
    shock_vuoto_registrato_il = forms.DateTimeField(
        required=False,
        label="Data e ora shock termico / vuoto",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = CarrelloProduzione
        fields = [
            "temperatura_pastorizzazione", "durata_pastorizzazione_minuti",
            "esito_pastorizzazione", "note_pastorizzazione",
            "esito_shock_vuoto", "note_shock_vuoto",
        ]
        widgets = {
            "esito_pastorizzazione": forms.RadioSelect(attrs={"class": "control-options"}),
            "esito_shock_vuoto": forms.RadioSelect(attrs={"class": "control-options"}),
            "note_pastorizzazione": forms.Textarea(attrs={"rows": 2}),
            "note_shock_vuoto": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pastorizzazione_registrata_il"].initial = self.instance.pastorizzazione_registrata_il
        self.fields["shock_vuoto_registrato_il"].initial = self.instance.shock_vuoto_registrato_il

    def save(self, commit=True):
        carrello = super().save(commit=False)
        carrello.pastorizzazione_registrata_il = self.cleaned_data["pastorizzazione_registrata_il"]
        carrello.shock_vuoto_registrato_il = self.cleaned_data["shock_vuoto_registrato_il"]
        carrello.chiuso_il = carrello.shock_vuoto_registrato_il
        if commit:
            carrello.save()
        return carrello


class ModificaInvasettamentoProduzioneForm(forms.ModelForm):
    moca_igienizzati_il = forms.DateTimeField(
        required=False,
        label="Data e ora pulizia / igienizzazione MOCA",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
    )

    class Meta:
        model = Produzione
        fields = [
            "moca_igienizzati", "pezzi_difettosi_finali",
            "capsule_difettose_finali",
        ]
        labels = {
            "moca_igienizzati": "Vasetti e capsule puliti e igienizzati",
            "pezzi_difettosi_finali": "N° vasetti difettosi complessivi",
            "capsule_difettose_finali": "N° capsule difettose complessive",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["moca_igienizzati_il"].initial = self.instance.moca_igienizzati_il

    def clean(self):
        dati = super().clean()
        if dati.get("moca_igienizzati") and not dati.get("moca_igienizzati_il"):
            raise forms.ValidationError("Indica data e ora dell'igienizzazione MOCA.")
        return dati

    def save(self, commit=True):
        produzione = super().save(commit=False)
        produzione.moca_igienizzati_il = self.cleaned_data["moca_igienizzati_il"]
        if commit:
            produzione.save()
        return produzione


class ModificaRisultatoProduzioneForm(forms.Form):
    lotto_definitivo = forms.CharField(max_length=50, label="Numero lotto definitivo")
    quantita_prodotta = forms.IntegerField(
        min_value=1, label="Numero di vasetti prodotti buoni",
    )
    peso_netto_vasetto_g = forms.DecimalField(
        max_digits=10, decimal_places=3, min_value=Decimal("0.001"),
        label="Peso netto del singolo vasetto (g)",
    )
    pezzi_difettosi_finali = forms.IntegerField(
        min_value=0, label="Numero di vasetti da scartare",
    )
    capsule_difettose_finali = forms.IntegerField(
        min_value=0, label="N° capsule difettose complessive",
    )
    note = forms.CharField(
        required=False, label="Note", widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, produzione=None, **kwargs):
        self.produzione = produzione
        if (
            produzione is not None
            and (not args or args[0] is None)
            and "initial" not in kwargs
        ):
            kwargs["initial"] = {
                "lotto_definitivo": produzione.lotto.codice_lotto if produzione.lotto else "",
                "quantita_prodotta": produzione.quantita_prodotta,
                "peso_netto_vasetto_g": produzione.peso_netto_vasetto_g,
                "pezzi_difettosi_finali": produzione.pezzi_difettosi_finali,
                "capsule_difettose_finali": produzione.capsule_difettose_finali,
                "note": produzione.note,
            }
        super().__init__(*args, **kwargs)

    def clean(self):
        dati = super().clean()
        vasetti = dati.get("quantita_prodotta")
        scarti = dati.get("pezzi_difettosi_finali")
        peso = dati.get("peso_netto_vasetto_g")
        if vasetti is not None and scarti is not None and peso is not None:
            dati["quantita_ottenuta_kg"] = Decimal(vasetti + scarti) * peso / Decimal("1000")
        return dati


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
