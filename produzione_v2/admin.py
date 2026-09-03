from django.contrib import admin

from .models import (
    AbilitazioneOperatore, AllocazioneOrigineUnita, AppartenenzaUnitaLotto,
    CicloProduzione, ConsuntivoEtichettatura, DefinizioneControllo,
    FaseProduzione, LineaProduzione, RegolaControlloCiclo, RisorsaProduzione,
    LottoCommerciale, LottoLavorazione, OrdineProduzione, OrigineLottoCommerciale,
    OutputProduzione, PassaggioLinea, StazioneLavoro, TurnoLinea,
)


class PassaggioInline(admin.TabularInline):
    model = PassaggioLinea
    extra = 0


class TurnoLineaInline(admin.TabularInline):
    model = TurnoLinea
    extra = 0


@admin.register(LineaProduzione)
class LineaProduzioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "nome", "attiva")
    inlines = (PassaggioInline, TurnoLineaInline)


class ControlloInline(admin.TabularInline):
    model = DefinizioneControllo
    extra = 0


@admin.register(StazioneLavoro)
class StazioneLavoroAdmin(admin.ModelAdmin):
    list_display = ("codice", "nome", "tipo", "attiva")
    inlines = (ControlloInline,)


@admin.register(OrdineProduzione)
class OrdineProduzioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "linea", "prodotto", "stato", "pianificato_per")
    list_filter = ("stato", "linea")
    search_fields = ("codice", "prodotto__codice", "prodotto__descrizione")


class RegolaControlloCicloInline(admin.TabularInline):
    model = RegolaControlloCiclo
    extra = 0


@admin.register(CicloProduzione)
class CicloProduzioneAdmin(admin.ModelAdmin):
    list_display = ("prodotto", "linea", "versione", "quantita_riferimento", "attivo")
    list_filter = ("attivo", "linea")
    inlines = (RegolaControlloCicloInline,)


@admin.register(FaseProduzione)
class FaseProduzioneAdmin(admin.ModelAdmin):
    list_display = ("ordine", "sequenza", "stazione", "stato")
    list_filter = ("stato", "passaggio__stazione")


@admin.register(OutputProduzione)
class OutputProduzioneAdmin(admin.ModelAdmin):
    list_display = ("ordine", "articolo", "codice_lotto", "quantita", "stato")
    list_filter = ("stato", "articolo")


@admin.register(AbilitazioneOperatore)
class AbilitazioneOperatoreAdmin(admin.ModelAdmin):
    list_display = ("operatore", "stazione", "ruolo", "valida_dal", "valida_fino_al", "attiva")
    list_filter = ("attiva", "stazione")


@admin.register(RisorsaProduzione)
class RisorsaProduzioneAdmin(admin.ModelAdmin):
    list_display = ("codice", "nome", "stazione", "tipo", "capacita", "attiva")
    list_filter = ("attiva", "tipo", "stazione")


admin.site.register(AllocazioneOrigineUnita)
admin.site.register(LottoLavorazione)
admin.site.register(AppartenenzaUnitaLotto)
admin.site.register(LottoCommerciale)
admin.site.register(OrigineLottoCommerciale)
admin.site.register(ConsuntivoEtichettatura)
