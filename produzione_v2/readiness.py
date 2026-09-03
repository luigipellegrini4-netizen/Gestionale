from dataclasses import dataclass

from django.db.models import Q
from django.utils import timezone

from .material_planning import PianificatoreMaterialiFEFO
from .models import AbilitazioneOperatore


@dataclass(frozen=True)
class ProblemaProntezza:
    codice: str
    descrizione: str


class ValutatoreProntezzaOrdine:
    def __init__(self, ordine):
        self.ordine = ordine

    def valuta(self):
        problemi = []
        if not self.ordine.linea.attiva:
            problemi.append(ProblemaProntezza("LINEA", "La linea produttiva non è attiva."))
        if self.ordine.ciclo_id and not self.ordine.ciclo.attivo:
            problemi.append(ProblemaProntezza("CICLO", "Il ciclo produttivo non è attivo."))
        oggi = timezone.localdate()
        for passaggio in self.ordine.linea.passaggi.select_related("stazione"):
            stazione = passaggio.stazione
            if stazione.richiede_risorsa and not stazione.risorse.filter(attiva=True).exists():
                problemi.append(ProblemaProntezza(
                    "RISORSA", f"{stazione.nome}: nessuna risorsa attiva disponibile.",
                ))
            if stazione.richiede_operatore_abilitato:
                abilitati = AbilitazioneOperatore.objects.filter(
                    stazione=stazione, attiva=True, valida_dal__lte=oggi,
                ).filter(Q(valida_fino_al__isnull=True) | Q(valida_fino_al__gte=oggi))
                if not abilitati.exists():
                    problemi.append(ProblemaProntezza(
                        "OPERATORE", f"{stazione.nome}: nessun operatore con abilitazione valida.",
                    ))
        for fase in self.ordine.fasi.all():
            _, mancanti = PianificatoreMaterialiFEFO(fase).calcola()
            for fabbisogno, quantita in mancanti:
                problemi.append(ProblemaProntezza(
                    "MATERIALE",
                    f"{fabbisogno.articolo.codice}: mancano {quantita} {fabbisogno.unita_misura}.",
                ))
        return problemi
