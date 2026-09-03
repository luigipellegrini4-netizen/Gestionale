from decimal import Decimal

from django.db.models import Count

from .models import OrdineProduzione


class ReportProduzione:
    def __init__(self, filtri):
        self.filtri = filtri

    def ordini(self):
        queryset = OrdineProduzione.objects.select_related(
            "prodotto", "linea", "ciclo",
        ).prefetch_related("output", "fasi", "eventi").annotate(
            numero_nc=Count("non_conformita", distinct=True),
        )
        if self.filtri.get("dal"):
            queryset = queryset.filter(pianificato_per__gte=self.filtri["dal"])
        if self.filtri.get("al"):
            queryset = queryset.filter(pianificato_per__lte=self.filtri["al"])
        if self.filtri.get("linea"):
            queryset = queryset.filter(linea=self.filtri["linea"])
        if self.filtri.get("stato"):
            queryset = queryset.filter(stato=self.filtri["stato"])
        return list(queryset.order_by("pianificato_per", "linea__codice", "codice")[:500])

    @staticmethod
    def indicatori(ordini):
        rese = [ordine.resa_percentuale for ordine in ordini if ordine.quantita_prodotta > 0]
        return {
            "totale": len(ordini),
            "completati": sum(
                ordine.stato == OrdineProduzione.Stato.COMPLETATO for ordine in ordini
            ),
            "abortiti": sum(
                ordine.stato == OrdineProduzione.Stato.ABORTITO for ordine in ordini
            ),
            "nc": sum(ordine.numero_nc for ordine in ordini),
            "resa_media": (
                (sum(rese, Decimal("0")) / len(rese)).quantize(Decimal("0.01"))
                if rese else None
            ),
        }
