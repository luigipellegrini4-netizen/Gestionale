from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from magazzino.models import Giacenza

from .models import ConsumoMateriale, FaseProduzione


@dataclass(frozen=True)
class PropostaPrelievo:
    fabbisogno: object
    giacenza: Giacenza
    quantita: Decimal


class PianificatoreMaterialiFEFO:
    def __init__(self, fase):
        self.fase = fase

    def calcola(self, blocca=False):
        proposte = []
        mancanti = []
        fabbisogni = self.fase.ordine.fabbisogni.filter(
            Q(fase=self.fase) | Q(fase__isnull=True),
        ).select_related("articolo")
        for fabbisogno in fabbisogni:
            residuo = fabbisogno.quantita_residua
            giacenze = Giacenza.objects.filter(
                lotto__articolo=fabbisogno.articolo,
                quantita__gt=0,
                ubicazione__attiva=True,
            ).filter(
                Q(lotto__data_scadenza__isnull=True)
                | Q(lotto__data_scadenza__gte=timezone.localdate())
            ).select_related("lotto__articolo", "ubicazione").order_by(
                F("lotto__data_scadenza").asc(nulls_last=True),
                "lotto__data_arrivo", "lotto__id", "ubicazione__nome", "id",
            )
            if blocca:
                giacenze = giacenze.select_for_update()
            for giacenza in giacenze:
                impegnata = giacenza.impegni_produzione_v2.filter(
                    stato=ConsumoMateriale.Stato.PRENOTATO,
                ).aggregate(totale=models.Sum("quantita"))["totale"] or Decimal("0")
                disponibile = giacenza.quantita - impegnata
                if disponibile <= 0:
                    continue
                quantita = min(residuo, disponibile)
                proposte.append(PropostaPrelievo(fabbisogno, giacenza, quantita))
                residuo -= quantita
                if residuo <= 0:
                    break
            if residuo > 0:
                mancanti.append((fabbisogno, residuo))
        return proposte, mancanti

    @transaction.atomic
    def prenota(self, operatore):
        from .services import prenota_materiale

        fase = FaseProduzione.objects.select_for_update().get(pk=self.fase.pk)
        if fase.stato != FaseProduzione.Stato.IN_CORSO:
            raise ValidationError("La prenotazione FEFO richiede una fase in corso.")
        self.fase = fase
        proposte, mancanti = self.calcola(blocca=True)
        if mancanti:
            dettaglio = ", ".join(
                f"{fabbisogno.articolo.codice}: {quantita} {fabbisogno.unita_misura}"
                for fabbisogno, quantita in mancanti
            )
            raise ValidationError(f"Disponibilità insufficiente per: {dettaglio}.")
        return [
            prenota_materiale(self.fase, proposta.giacenza, proposta.quantita, operatore)
            for proposta in proposte
        ]
