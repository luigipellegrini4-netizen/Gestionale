import json

from django import forms
from django.contrib.auth import get_user_model

from magazzino.models import Articolo, Giacenza, Ubicazione

from .models import (
    AbilitazioneOperatore, CicloProduzione, DefinizioneControllo,
    DipendenzaPassaggio, FaseProduzione, LineaProduzione, NonConformita,
    OrdineProduzione, PassaggioLinea, RegolaControlloCiclo, StazioneLavoro, UnitaProduzione,
    ConsumoMateriale, LottoCommerciale, LottoLavorazione, RisorsaProduzione,
    TipoUnitaProduzione, TurnoLinea,
)


class LineaProduzioneForm(forms.ModelForm):
    class Meta:
        model = LineaProduzione
        fields = ("codice", "nome", "descrizione", "attiva")


class TurnoLineaForm(forms.ModelForm):
    class Meta:
        model = TurnoLinea
        fields = ("giorno_settimana", "ora_inizio", "ora_fine", "attivo")
        widgets = {
            "ora_inizio": forms.TimeInput(attrs={"type": "time"}),
            "ora_fine": forms.TimeInput(attrs={"type": "time"}),
        }


class ReportProduzioneForm(forms.Form):
    dal = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )
    al = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"}),
    )
    linea = forms.ModelChoiceField(
        queryset=LineaProduzione.objects.all(), required=False,
    )
    stato = forms.ChoiceField(
        choices=(("", "Tutti gli stati"),) + tuple(OrdineProduzione.Stato.choices),
        required=False,
    )

    def clean(self):
        dati = super().clean()
        if dati.get("dal") and dati.get("al") and dati["dal"] > dati["al"]:
            raise forms.ValidationError("La data iniziale non può superare quella finale.")
        return dati


class StazioneLavoroForm(forms.ModelForm):
    class Meta:
        model = StazioneLavoro
        fields = (
            "codice", "nome", "tipo", "richiede_operatore_abilitato",
            "richiede_risorsa", "attiva",
        )


class PassaggioLineaForm(forms.ModelForm):
    class Meta:
        model = PassaggioLinea
        fields = ("stazione", "ordine", "obbligatoria", "durata_standard_minuti")

    def __init__(self, *args, linea=None, **kwargs):
        super().__init__(*args, **kwargs)
        if linea is not None:
            usate = linea.passaggi.values_list("stazione_id", flat=True)
            self.fields["stazione"].queryset = StazioneLavoro.objects.filter(
                attiva=True,
            ).exclude(pk__in=usate)


class DipendenzaPassaggioForm(forms.ModelForm):
    class Meta:
        model = DipendenzaPassaggio
        fields = ("passaggio", "predecessore", "modalita", "quantita_minima_avvio")
        labels = {
            "passaggio": "Stazione successiva",
            "predecessore": "Stazione precedente",
            "modalita": "Modalità di collegamento",
            "quantita_minima_avvio": "Quantità minima per avvio",
        }

    def __init__(self, *args, linea=None, **kwargs):
        super().__init__(*args, **kwargs)
        if linea is not None:
            passaggi = linea.passaggi.select_related("stazione")
            self.fields["passaggio"].queryset = passaggi
            self.fields["predecessore"].queryset = passaggi

    def clean(self):
        dati = super().clean()
        if dati.get("passaggio") == dati.get("predecessore"):
            raise forms.ValidationError("Una stazione non può dipendere da sé stessa.")
        return dati


class DefinizioneControlloForm(forms.ModelForm):
    regole_json = forms.CharField(
        required=False,
        label="Regole",
        help_text=(
            'JSON, es.: {"conforme_max":"4.1", '
            '"allerta_min_escluso":"4.1", "allerta_max":"4.4"}'
        ),
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = DefinizioneControllo
        fields = (
            "codice", "nome", "tipo_dato", "obbligatorio",
            "unita_misura", "ordine",
        )

    def clean_regole_json(self):
        testo = self.cleaned_data["regole_json"].strip()
        if not testo:
            return {}
        try:
            regole = json.loads(testo)
        except json.JSONDecodeError as errore:
            raise forms.ValidationError("Le regole devono essere un oggetto JSON valido.") from errore
        if not isinstance(regole, dict):
            raise forms.ValidationError("Le regole devono essere un oggetto JSON.")
        return regole

    def save(self, commit=True):
        controllo = super().save(commit=False)
        controllo.regole = self.cleaned_data["regole_json"]
        if commit:
            controllo.save()
        return controllo


class OrdineProduzioneForm(forms.ModelForm):
    ciclo = forms.ModelChoiceField(
        queryset=CicloProduzione.objects.none(), label="Prodotto, linea e ciclo",
    )

    class Meta:
        model = OrdineProduzione
        fields = (
            "codice", "ciclo", "quantita_pianificata",
            "priorita", "pianificato_per", "note",
        )
        widgets = {"pianificato_per": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ciclo"].queryset = CicloProduzione.objects.select_related(
            "prodotto", "linea", "ricetta",
        ).filter(
            attivo=True, linea__attiva=True, prodotto__attivo=True,
        )

    def clean(self):
        dati = super().clean()
        ciclo = dati.get("ciclo")
        if ciclo:
            self.instance.linea = ciclo.linea
            self.instance.prodotto = ciclo.prodotto
        return dati

    def save(self, commit=True):
        ordine = super().save(commit=False)
        ordine.ciclo = self.cleaned_data["ciclo"]
        ordine.linea = ordine.ciclo.linea
        ordine.prodotto = ordine.ciclo.prodotto
        if commit:
            ordine.save()
        return ordine


class CicloProduzioneForm(forms.ModelForm):
    class Meta:
        model = CicloProduzione
        fields = (
            "prodotto", "linea", "ricetta", "versione",
            "quantita_riferimento", "resa_minima_percentuale",
            "resa_massima_percentuale", "attivo", "note",
        )

    def clean(self):
        dati = super().clean()
        prodotto = dati.get("prodotto")
        ricetta = dati.get("ricetta")
        if prodotto and ricetta and ricetta.articolo_id != prodotto.pk:
            self.add_error("ricetta", "La ricetta non appartiene al prodotto selezionato.")
        return dati


class RegolaControlloCicloForm(forms.ModelForm):
    regole_json = forms.CharField(
        label="Limiti specifici del prodotto",
        help_text=(
            'JSON, es.: {"conforme_min":"60", "conforme_max":"65", '
            '"allerta_min_escluso":"65", "allerta_max":"67"}'
        ),
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = RegolaControlloCiclo
        fields = ("definizione", "attiva")

    def __init__(self, *args, ciclo=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ciclo is not None:
            stazioni = ciclo.linea.passaggi.values_list("stazione_id", flat=True)
            gia_presenti = ciclo.regole_controllo.values_list("definizione_id", flat=True)
            self.fields["definizione"].queryset = DefinizioneControllo.objects.filter(
                stazione_id__in=stazioni,
            ).exclude(pk__in=gia_presenti)

    def clean_regole_json(self):
        try:
            regole = json.loads(self.cleaned_data["regole_json"])
        except json.JSONDecodeError as errore:
            raise forms.ValidationError("I limiti devono essere un oggetto JSON valido.") from errore
        if not isinstance(regole, dict) or not regole:
            raise forms.ValidationError("Indica almeno una regola.")
        return regole

    def save(self, commit=True):
        regola = super().save(commit=False)
        regola.regole = self.cleaned_data["regole_json"]
        if commit:
            regola.save()
        return regola


class TipoUnitaProduzioneForm(forms.ModelForm):
    class Meta:
        model = TipoUnitaProduzione
        fields = ("codice", "nome", "unita_misura", "richiede_quantita", "attivo")


class UnitaProduzioneForm(forms.Form):
    tipo = forms.ModelChoiceField(queryset=TipoUnitaProduzione.objects.none())
    codice = forms.CharField(max_length=50)
    quantita = forms.DecimalField(
        required=False, min_value=0, max_digits=14, decimal_places=3,
    )
    origine = forms.ModelChoiceField(
        queryset=UnitaProduzione.objects.none(), required=False,
        help_text="Facoltativa: unità della fase precedente da cui deriva.",
    )
    quantita_origine = forms.DecimalField(
        required=False, min_value=0.001, max_digits=14, decimal_places=3,
        label="Quantità prelevata dall'origine",
        help_text="Obbligatoria per un prelievo parziale; se vuota usa tutto il residuo.",
    )

    def __init__(self, *args, fase=None, **kwargs):
        super().__init__(*args, **kwargs)
        if fase is not None:
            self.fields["tipo"].queryset = fase.stazione.tipi_unita.filter(attivo=True)
            self.fields["origine"].queryset = fase.ordine.unita.exclude(fase=fase).filter(
                stato__in=(UnitaProduzione.Stato.CONFORME, UnitaProduzione.Stato.REINTEGRATA),
            )


class AllocazioneOrigineForm(forms.Form):
    destinazione = forms.ModelChoiceField(queryset=UnitaProduzione.objects.none())
    origine = forms.ModelChoiceField(queryset=UnitaProduzione.objects.none())
    quantita = forms.DecimalField(min_value=0.001, max_digits=14, decimal_places=3)

    def __init__(self, *args, ordine=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ordine is not None:
            self.fields["destinazione"].queryset = ordine.unita.select_related("fase").order_by(
                "fase__sequenza", "codice",
            )
            self.fields["origine"].queryset = ordine.unita.select_related("fase").filter(
                stato__in=(UnitaProduzione.Stato.CONFORME, UnitaProduzione.Stato.REINTEGRATA),
            ).order_by("fase__sequenza", "codice")


class LottoLavorazioneForm(forms.Form):
    codice = forms.CharField(max_length=50, label="Codice lotto temporaneo B")
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))


class BatchRoboQboForm(forms.Form):
    codice = forms.CharField(max_length=50, label="Codice batch")
    quantita = forms.DecimalField(
        min_value=0.001, max_digits=14, decimal_places=3, label="Quantità prodotta (kg)",
    )


class TankRoboQboForm(forms.Form):
    codice = forms.CharField(max_length=50, label="Codice tank")


class RiversamentoTankForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=UnitaProduzione.objects.none())
    tank = forms.ModelChoiceField(queryset=UnitaProduzione.objects.none())
    quantita = forms.DecimalField(
        min_value=0.001, max_digits=14, decimal_places=3, label="Quantità riversata (kg)",
    )

    def __init__(self, *args, fase=None, **kwargs):
        super().__init__(*args, **kwargs)
        if fase is not None:
            self.fields["batch"].queryset = fase.unita.filter(
                tipo="BATCH",
                stato__in=(UnitaProduzione.Stato.CONFORME, UnitaProduzione.Stato.REINTEGRATA),
            ).order_by("codice")
            self.fields["tank"].queryset = fase.unita.filter(tipo="TANK").exclude(
                stato__in=(UnitaProduzione.Stato.SCARTATA, UnitaProduzione.Stato.ANNULLATA),
            ).order_by("codice")


class ChiusuraLottoCommercialeForm(forms.Form):
    lotti_lavorazione = forms.ModelMultipleChoiceField(
        queryset=LottoLavorazione.objects.none(), label="Lotti temporanei di origine",
    )
    codice = forms.CharField(required=False, max_length=50, label="Lotto definitivo C")
    vasetti_conformi = forms.IntegerField(min_value=0)
    vasetti_scartati = forms.IntegerField(min_value=0)
    capsule_scartate = forms.IntegerField(min_value=0)
    motivazione_eccezione = forms.CharField(
        required=False, label="Motivazione unione eccezionale",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, ordine=None, codice_proposto=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ordine is not None:
            self.fields["lotti_lavorazione"].queryset = ordine.lotti_lavorazione.filter(
                stato=LottoLavorazione.Stato.CHIUSO,
            )
        self.fields["codice"].initial = codice_proposto


class ConsuntivoEtichettaturaForm(forms.Form):
    lotto_commerciale = forms.ModelChoiceField(
        queryset=LottoCommerciale.objects.none(), label="Lotto definitivo",
    )
    vasetti_conformi = forms.IntegerField(min_value=0)
    vasetti_scartati = forms.IntegerField(min_value=0)
    etichette_scartate = forms.IntegerField(min_value=0)

    def __init__(self, *args, ordine=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lotto_commerciale"].queryset = (
            ordine.lotti_commerciali.filter(consuntivo_etichettatura__isnull=True)
            if ordine is not None else LottoCommerciale.objects.none()
        )


class OutputProduzioneForm(forms.Form):
    articolo = forms.ModelChoiceField(queryset=Articolo.objects.none())
    codice_lotto = forms.CharField(max_length=50)
    quantita = forms.DecimalField(min_value=0.000001, max_digits=14, decimal_places=6)
    unita = forms.ModelChoiceField(
        queryset=UnitaProduzione.objects.none(), required=False,
        label="Unità di origine",
    )
    ubicazione = forms.ModelChoiceField(queryset=Ubicazione.objects.none())
    scaffale = forms.CharField(max_length=30, required=False)
    piano = forms.CharField(max_length=30, required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, fase=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["articolo"].queryset = Articolo.objects.filter(attivo=True)
        self.fields["ubicazione"].queryset = Ubicazione.objects.filter(attiva=True)
        if fase is not None:
            self.fields["articolo"].initial = fase.ordine.prodotto
            self.fields["unita"].queryset = fase.unita.filter(
                stato__in=(
                    UnitaProduzione.Stato.CONFORME,
                    UnitaProduzione.Stato.ALLERTA,
                    UnitaProduzione.Stato.REINTEGRATA,
                ),
            )


class AbilitazioneOperatoreForm(forms.ModelForm):
    class Meta:
        model = AbilitazioneOperatore
        fields = (
            "operatore", "ruolo", "valida_dal", "valida_fino_al", "attiva", "note",
        )
        widgets = {
            "valida_dal": forms.DateInput(attrs={"type": "date"}),
            "valida_fino_al": forms.DateInput(attrs={"type": "date"}),
        }


class AssegnazioneOperatoreForm(forms.Form):
    operatore = forms.ModelChoiceField(queryset=get_user_model().objects.none())

    def __init__(self, *args, fase=None, **kwargs):
        super().__init__(*args, **kwargs)
        utenti = get_user_model().objects.filter(is_active=True)
        if fase is not None:
            gia_assegnati = fase.assegnazioni.filter(
                terminato_il__isnull=True,
            ).values_list("operatore_id", flat=True)
            utenti = utenti.exclude(pk__in=gia_assegnati)
            if fase.stazione.richiede_operatore_abilitato:
                utenti = utenti.filter(
                    abilitazioni_produzione_v2__stazione=fase.stazione,
                    abilitazioni_produzione_v2__attiva=True,
                ).distinct()
        self.fields["operatore"].queryset = utenti.order_by("username")


class RisorsaProduzioneForm(forms.ModelForm):
    class Meta:
        model = RisorsaProduzione
        fields = ("codice", "nome", "tipo", "capacita", "unita_misura", "attiva", "note")


class ImpegnoRisorsaForm(forms.Form):
    risorsa = forms.ModelChoiceField(queryset=RisorsaProduzione.objects.none())

    def __init__(self, *args, fase=None, **kwargs):
        super().__init__(*args, **kwargs)
        if fase is not None:
            gia_impegnate = fase.impegni_risorse.filter(
                rilasciata_il__isnull=True,
            ).values_list("risorsa_id", flat=True)
            self.fields["risorsa"].queryset = fase.stazione.risorse.filter(
                attiva=True,
            ).exclude(pk__in=gia_impegnate)


class GiacenzaChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, giacenza):
        posizione = " / ".join(filter(None, (
            giacenza.ubicazione.nome,
            f"Scaffale {giacenza.scaffale}" if giacenza.scaffale else "",
            f"Piano {giacenza.piano}" if giacenza.piano else "",
        )))
        return (
            f"{giacenza.lotto.articolo.codice} - {giacenza.lotto.articolo.nome_per_produzione} · "
            f"lotto {giacenza.lotto.codice_lotto} · {giacenza.quantita} · {posizione}"
        )


class PrenotazioneMaterialeForm(forms.Form):
    giacenza = GiacenzaChoiceField(queryset=Giacenza.objects.none(), label="Lotto e posizione")
    quantita = forms.DecimalField(min_value=0.000001, max_digits=14, decimal_places=6)

    def __init__(self, *args, articoli=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = Giacenza.objects.select_related(
            "lotto__articolo", "ubicazione",
        ).filter(quantita__gt=0, ubicazione__attiva=True)
        if articoli:
            queryset = queryset.filter(lotto__articolo_id__in=articoli)
        else:
            queryset = queryset.filter(lotto__articolo__categoria__in=(
                Articolo.Categoria.MATERIA_PRIMA, Articolo.Categoria.SEMILAVORATO,
            ))
        self.fields["giacenza"].queryset = queryset.order_by(
            "lotto__articolo__codice", "lotto__codice_lotto",
            "ubicazione__nome", "scaffale", "piano",
        )


class AperturaNonConformitaForm(forms.Form):
    fase = forms.ModelChoiceField(
        queryset=FaseProduzione.objects.none(), required=False, label="Fase coinvolta",
    )
    unita = forms.ModelChoiceField(
        queryset=UnitaProduzione.objects.none(), required=False, label="Unità coinvolta",
    )
    consumo = forms.ModelChoiceField(
        queryset=ConsumoMateriale.objects.none(), required=False, label="Materiale coinvolto",
    )
    motivo = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, ordine=None, **kwargs):
        super().__init__(*args, **kwargs)
        if ordine is not None:
            self.fields["fase"].queryset = ordine.fasi.select_related("passaggio__stazione")
            self.fields["unita"].queryset = ordine.unita.select_related("fase")
            self.fields["consumo"].queryset = ordine.materiali.select_related("articolo", "lotto")


class ChiusuraNonConformitaForm(forms.Form):
    esito = forms.ChoiceField(choices=NonConformita.Esito.choices)
    azione = forms.CharField(
        label="Azione adottata", widget=forms.Textarea(attrs={"rows": 3}),
    )
