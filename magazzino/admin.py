from django.contrib import admin
from .models import Articolo, Ubicazione, Fornitore, Lotto, Giacenza, Movimento


@admin.register(Articolo)
class ArticoloAdmin(admin.ModelAdmin):
    list_display = (
        "codice",
        "descrizione",
        "categoria",
        "unita_misura",
        "scorta_minima",
        "criterio_rotazione",
        "attivo",
    )
    list_filter = (
        "categoria",
        "unita_misura",
        "criterio_rotazione",
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
        "scaffale",
        "piano",
        "attiva",
    )
    list_filter = (
        "tipo_magazzino",
        "attiva",
    )
    search_fields = (
        "nome",
        "scaffale",
        "piano",
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
        "fornitore",
        "data_arrivo",
        "data_produzione",
        "data_scadenza",
        "quantita_iniziale",
    )
    list_filter = (
        "tipo",
        "articolo",
        "fornitore",
    )
    search_fields = (
        "codice_lotto",
        "fornitore__codice",
        "fornitore__ragione_sociale",
        "articolo__codice",
        "articolo__descrizione",
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
