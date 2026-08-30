from django.contrib import admin
from .models import (
    Articolo, Ubicazione, Fornitore, Lotto, Giacenza, Movimento,
    NonConformitaLotto,
)


@admin.register(NonConformitaLotto)
class NonConformitaLottoAdmin(admin.ModelAdmin):
    list_display = (
        "id", "ambito", "tipo_nc", "lotto", "stato", "numero_uda_quarantena",
        "data_apertura", "aperta_da", "data_chiusura", "gestita_da",
    )
    list_filter = ("stato", "ambito", "tipo_nc", "data_apertura", "data_chiusura")
    search_fields = (
        "lotto__codice_lotto", "lotto__articolo__codice",
        "lotto__articolo__descrizione", "motivo", "decisione",
    )
    readonly_fields = ("data_apertura", "data_chiusura")


@admin.register(Articolo)
class ArticoloAdmin(admin.ModelAdmin):
    list_display = (
        "codice",
        "descrizione",
        "categoria",
        "unita_misura",
        "scorta_minima",
        "attivo",
    )
    list_filter = (
        "categoria",
        "unita_misura",
        "attivo",
    )
    search_fields = (
        "codice",
        "descrizione",
    )
    ordering = ("codice",)


@admin.register(Ubicazione)
class UbicazioneAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "tipo_magazzino",
        "attiva",
    )
    list_filter = (
        "tipo_magazzino",
        "attiva",
    )
    search_fields = (
        "nome",
    )
    ordering = ("nome",)


@admin.register(Fornitore)
class FornitoreAdmin(admin.ModelAdmin):
    list_display = (
        "codice",
        "ragione_sociale",
        "partita_iva",
        "telefono",
        "email",
        "attivo",
    )
    list_filter = (
        "attivo",
    )
    search_fields = (
        "codice",
        "ragione_sociale",
        "partita_iva",
        "telefono",
        "email",
    )
    ordering = (
        "ragione_sociale",
    )


@admin.register(Lotto)
class LottoAdmin(admin.ModelAdmin):
    list_display = (
        "codice_lotto",
        "articolo",
        "tipo",
        "fase",
        "fornitore",
        "data_arrivo",
        "data_produzione",
        "data_scadenza",
        "quantita_iniziale",
        "numero_colli",
        "unita_acquisto_per_collo",
        "peso_unita_acquisto",
        "fattura",
        "ddt",
    )
    list_filter = (
        "tipo",
        "fase",
        "articolo",
        "fornitore",
    )
    search_fields = (
        "codice_lotto",
        "fornitore__codice",
        "fornitore__ragione_sociale",
        "articolo__codice",
        "articolo__descrizione",
        "fattura",
        "ddt",
    )
    ordering = (
        "articolo",
        "codice_lotto",
    )


@admin.register(Giacenza)
class GiacenzaAdmin(admin.ModelAdmin):
    list_display = (
        "lotto",
        "ubicazione",
        "scaffale",
        "piano",
        "quantita",
    )
    list_filter = (
        "ubicazione",
    )
    search_fields = (
        "lotto__codice_lotto",
        "lotto__articolo__codice",
        "lotto__articolo__descrizione",
        "ubicazione__nome",
    )
    ordering = (
        "lotto",
        "ubicazione",
    )


@admin.register(Movimento)
class MovimentoAdmin(admin.ModelAdmin):
    list_display = (
        "data_ora",
        "tipo",
        "lotto",
        "quantita",
        "ubicazione_origine",
        "ubicazione_destinazione",
        "eseguito_da",
        "causale",
    )
    list_filter = (
        "tipo",
        "data_ora",
        "ubicazione_origine",
        "ubicazione_destinazione",
        "eseguito_da",
    )
    search_fields = (
        "lotto__codice_lotto",
        "lotto__articolo__codice",
        "lotto__articolo__descrizione",
        "eseguito_da__username",
        "eseguito_da__first_name",
        "eseguito_da__last_name",
        "causale",
        "note",
    )
    ordering = (
        "-data_ora",
    )
