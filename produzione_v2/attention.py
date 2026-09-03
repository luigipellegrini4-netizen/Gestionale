from django.utils import timezone

from .models import FaseProduzione, NonConformita, RilevazioneControllo


class CentroAttenzioneProduzione:
    def dati(self):
        stati_attivi = (
            FaseProduzione.Stato.DA_AVVIARE,
            FaseProduzione.Stato.IN_CORSO,
            FaseProduzione.Stato.IN_ATTESA,
            FaseProduzione.Stato.BLOCCATA,
        )
        return {
            "nc_aperte": NonConformita.objects.exclude(
                stato=NonConformita.Stato.CHIUSA,
            ).select_related(
                "ordine", "fase__passaggio__stazione", "unita", "consumo__lotto",
            ).order_by("aperta_il")[:30],
            "fasi_in_ritardo": FaseProduzione.objects.filter(
                stato__in=stati_attivi,
                pianificata_fine__lt=timezone.now(),
            ).select_related(
                "ordine", "passaggio__stazione",
            ).order_by("pianificata_fine")[:30],
            "controlli_critici": RilevazioneControllo.objects.filter(
                esito__in=(
                    RilevazioneControllo.Esito.ALLERTA,
                    RilevazioneControllo.Esito.NON_CONFORME,
                ),
            ).select_related(
                "fase__ordine", "fase__passaggio__stazione", "definizione",
            ).order_by("-rilevato_il")[:30],
        }
