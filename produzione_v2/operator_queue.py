from django.utils import timezone

from .models import AbilitazioneOperatore, AssegnazioneOperatore, FaseProduzione


class CodaLavoroOperatore:
    def __init__(self, operatore):
        self.operatore = operatore

    def dati(self):
        assegnazioni = AssegnazioneOperatore.objects.filter(
            operatore=self.operatore, terminato_il__isnull=True,
        ).select_related(
            "fase__ordine__prodotto", "fase__passaggio__stazione",
        ).order_by("-fase__ordine__priorita", "fase__pianificata_inizio")
        candidate = FaseProduzione.objects.filter(
            ordine__stato="IN_CORSO", stato=FaseProduzione.Stato.DA_AVVIARE,
        ).select_related(
            "ordine__prodotto", "passaggio__stazione",
        ).prefetch_related("passaggio__dipendenze").order_by(
            "-ordine__priorita", "pianificata_inizio", "ordine__codice", "sequenza",
        )[:100]
        disponibili = [
            fase for fase in candidate
            if fase.eseguibile and self._abilitato(fase)
        ]
        return {
            "assegnazioni_attive": assegnazioni,
            "fasi_disponibili": disponibili,
            "adesso": timezone.now(),
        }

    def _abilitato(self, fase):
        if not fase.stazione.richiede_operatore_abilitato:
            return True
        oggi = timezone.localdate()
        return AbilitazioneOperatore.objects.filter(
            operatore=self.operatore, stazione=fase.stazione,
            attiva=True, valida_dal__lte=oggi,
        ).filter(
            valida_fino_al__isnull=True,
        ).exists() or AbilitazioneOperatore.objects.filter(
            operatore=self.operatore, stazione=fase.stazione,
            attiva=True, valida_dal__lte=oggi, valida_fino_al__gte=oggi,
        ).exists()
