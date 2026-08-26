from django.urls import path

from . import views


urlpatterns = [
    path(
        "", 
        views.home,
        name="home",
    ),

    path(
        "carichi/nuovo/",
        views.nuovo_carico,
        name="nuovo_carico",
    ),

    path(
        "trasferimento/",
        views.trasferimento,
        name="trasferimento",
    ),

    path(
        "situazione/",
        views.situazione_magazzino,
        name="situazione_magazzino",
    ),

    path(
        "consumo/",
        views.consumo,
        name="consumo",
    ),

    path(
        "movimenti/",
        views.elenco_movimenti,
        name="elenco_movimenti",
    ),

    path(
        "lotti/<int:pk>/",
        views.dettaglio_lotto,
        name="dettaglio_lotto",
    ),

    path(
        "ricette/",
        views.elenco_ricette,
        name="elenco_ricette",
    ),

    path(
        "ricette/<int:pk>/",
        views.dettaglio_ricetta,
        name="dettaglio_ricetta",
    ),

    path(
        "ricette/<int:pk>/modifica/",
        views.modifica_ricetta,
        name="modifica_ricetta",
    ),

    path(
        "ricette/<int:pk>/aggiungi-riga/",
        views.aggiungi_riga_ricetta,
        name="aggiungi_riga_ricetta",
    ),

    path(
        "ricette/righe/<int:pk>/modifica/",
        views.modifica_riga_ricetta,
        name="modifica_riga_ricetta",
    ),

    path(
        "ricette/righe/<int:pk>/elimina/",
        views.elimina_riga_ricetta,
        name="elimina_riga_ricetta",
    ),

    path(
        "ricette/nuova/",
        views.nuova_ricetta,
        name="nuova_ricetta",
    ),

    path(
        "produzione/",
        views.elenco_produzioni,
        {
            "tipo": "produzione",
        },
        name="elenco_produzioni",
    ),

    path(
        "produzione/nuova/",
        views.nuova_produzione,
        name="nuova_produzione",
    ),

    path(
        "produzione/<int:pk>/",
        views.gestione_produzione,
        name="gestione_produzione",
    ),

    path(
        "produzione-semilavorati/nuova/",
        views.nuova_produzione_semilavorato,
        name="nuova_produzione_semilavorato",
    ),

    path(
        "produzione-semilavorati/",
        views.elenco_produzioni,
        {
            "tipo": "semilavorato",
        },
        name="elenco_produzioni_semilavorato",
    ),

    path(
        "produzione-semilavorati/<int:pk>/",
        views.gestione_produzione_semilavorato,
        name="gestione_produzione_semilavorato",
    ),

    path(
        "confezionamento/nuovo/",
        views.nuovo_confezionamento,
        name="nuovo_confezionamento",
    ),

    path(
        "inscatolamento/nuovo/",
        views.nuovo_inscatolamento,
        name="nuovo_inscatolamento",
    ),

    path(
        "articoli/",
        views.elenco_articoli,
        name="elenco_articoli",
    ),

    path(
        "articoli/nuovo/",
        views.nuovo_articolo,
        name="nuovo_articolo",
    ),

    path(
        "articoli/<int:pk>/",
        views.dettaglio_articolo,
        name="dettaglio_articolo",
    ),
    
    path(
        "articoli/<int:pk>/modifica/",
        views.modifica_articolo,
        name="modifica_articolo",
    ),
]