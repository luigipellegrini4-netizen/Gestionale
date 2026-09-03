from magazzino.models import Lotto

from .models import ConsumoMateriale, OrdineProduzione, OutputProduzione


class CatenaTracciabilita:
    """Ricostruisce la genealogia dei lotti attraversando più ordini V2."""

    def __init__(self, termine, profondita_massima=20):
        self.termine = (termine or "").strip()
        self.profondita_massima = profondita_massima

    def calcola(self):
        lotti_iniziali = set(Lotto.objects.filter(
            codice_lotto__icontains=self.termine,
        ).values_list("pk", flat=True)) if self.termine else set()
        valle_lotti, valle_ordini = self._a_valle(lotti_iniziali)
        monte_lotti, monte_ordini = self._a_monte(lotti_iniziali)
        tutti_lotti = lotti_iniziali | valle_lotti | monte_lotti
        tutti_ordini = valle_ordini | monte_ordini
        return {
            "lotti_iniziali": Lotto.objects.filter(pk__in=lotti_iniziali).select_related("articolo"),
            "lotti_a_valle": Lotto.objects.filter(pk__in=valle_lotti).select_related("articolo"),
            "lotti_a_monte": Lotto.objects.filter(pk__in=monte_lotti).select_related("articolo"),
            "ordini_coinvolti": OrdineProduzione.objects.filter(
                pk__in=tutti_ordini,
            ).select_related("prodotto", "linea"),
            "numero_lotti": len(tutti_lotti),
            "numero_ordini": len(tutti_ordini),
        }

    def _a_valle(self, iniziali):
        visitati_lotti = set(iniziali)
        visitati_ordini = set()
        frontiera = set(iniziali)
        for _ in range(self.profondita_massima):
            if not frontiera:
                break
            ordini = set(ConsumoMateriale.objects.filter(
                lotto_id__in=frontiera,
            ).values_list("ordine_id", flat=True)) - visitati_ordini
            if not ordini:
                break
            visitati_ordini.update(ordini)
            nuovi_lotti = set(OutputProduzione.objects.filter(
                ordine_id__in=ordini, lotto_id__isnull=False,
            ).values_list("lotto_id", flat=True)) - visitati_lotti
            visitati_lotti.update(nuovi_lotti)
            frontiera = nuovi_lotti
        return visitati_lotti - iniziali, visitati_ordini

    def _a_monte(self, iniziali):
        visitati_lotti = set(iniziali)
        visitati_ordini = set()
        frontiera = set(iniziali)
        for _ in range(self.profondita_massima):
            if not frontiera:
                break
            ordini = set(OutputProduzione.objects.filter(
                lotto_id__in=frontiera,
            ).values_list("ordine_id", flat=True)) - visitati_ordini
            if not ordini:
                break
            visitati_ordini.update(ordini)
            nuovi_lotti = set(ConsumoMateriale.objects.filter(
                ordine_id__in=ordini, lotto_id__isnull=False,
            ).values_list("lotto_id", flat=True)) - visitati_lotti
            visitati_lotti.update(nuovi_lotti)
            frontiera = nuovi_lotti
        return visitati_lotti - iniziali, visitati_ordini
