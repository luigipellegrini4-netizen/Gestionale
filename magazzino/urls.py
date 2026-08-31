from django.urls import path

from . import views


urlpatterns = [
    path(
        "non-conformita/nuova/",
        views.apri_non_conformita_generale,
        name="apri_non_conformita_generale",
    ),
    path(
        "non-conformita/ricerca-lotti/",
        views.ricerca_lotti_non_conformita,
        name="ricerca_lotti_non_conformita",
    ),
    path(
        "non-conformita/posizioni-lotto/",
        views.posizioni_lotto_non_conformita,
        name="posizioni_lotto_non_conformita",
    ),
    path(
        "non-conformita/",
        views.registro_non_conformita,
        name="registro_non_conformita",
    ),
    path(
        "non-conformita/<int:pk>/",
        views.dettaglio_non_conformita,
        name="dettaglio_non_conformita",
    ),
    path(
        "amministrazione/registro-operazioni/<int:pk>/",
        views.dettaglio_registro_operazione,
        name="dettaglio_registro_operazione",
    ),
    path(
        "amministrazione/azzera-database/",
        views.azzera_database_magazzino,
        name="azzera_database_magazzino",
    ),
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
        "trasferimento/disponibilita/",
        views.disponibilita_trasferimento,
        name="disponibilita_trasferimento",
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
        "rettifica-inventario/",
        views.rettifica_inventario,
        name="rettifica_inventario",
    ),
    path(
        "rettifica-inventario/disponibilita/",
        views.disponibilita_rettifica,
        name="disponibilita_rettifica",
    ),

    path(
        "movimenti/",
        views.elenco_movimenti,
        name="elenco_movimenti",
    ),
    path(
        "lotti/ricerca/",
        views.ricerca_lotti,
        name="ricerca_lotti",
    ),

    path(
        "lotti/<int:pk>/",
        views.dettaglio_lotto,
        name="dettaglio_lotto",
    ),
    path(
        "lotti/<int:pk>/non-conformita/nuova/",
        views.apri_non_conformita,
        name="apri_non_conformita",
    ),
    path(
        "non-conformita/<int:pk>/gestisci/",
        views.gestisci_non_conformita,
        name="gestisci_non_conformita",
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
        "produzione/gestione/",
        views.elenco_gestione_produzioni,
        name="elenco_gestione_produzioni",
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
        "produzione/<int:pk>/gestione/",
        views.dettaglio_gestione_produzione,
        name="dettaglio_gestione_produzione",
    ),
    path(
        "produzione/<int:pk>/invasettamento/",
        views.invasettamento_produzione,
        name="invasettamento_produzione",
    ),
    path(
        "produzione/<int:pk>/modifica/",
        views.modifica_produzione,
        name="modifica_produzione",
    ),
    path(
        "produzione/batch/<int:pk>/modifica/",
        views.modifica_batch_produzione,
        name="modifica_batch_produzione",
    ),
    path(
        "produzione/carrello/<int:pk>/modifica/",
        views.modifica_carrello_produzione,
        name="modifica_carrello_produzione",
    ),
    path(
        "produzione/<int:pk>/invasettamento/modifica/",
        views.modifica_invasettamento_produzione,
        name="modifica_invasettamento_produzione",
    ),
    path(
        "produzione/<int:pk>/risultato/modifica/",
        views.modifica_risultato_produzione_view,
        name="modifica_risultato_produzione",
    ),
    path(
        "produzione/invasettamento/",
        views.elenco_invasettamenti,
        name="elenco_invasettamenti",
    ),
    path(
        "produzione/<int:pk>/elimina/",
        views.elimina_produzione,
        name="elimina_produzione",
    ),
    path(
        "produzione/tank/<int:pk>/modifica/",
        views.modifica_tank,
        name="modifica_tank",
    ),
    path(
        "produzione/tank/<int:pk>/annulla/",
        views.annulla_tank,
        name="annulla_tank",
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
        "produzione-semilavorati/<int:pk>/elimina/",
        views.elimina_produzione_semilavorato,
        name="elimina_produzione_semilavorato",
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
    path("fornitori/", views.elenco_fornitori, name="elenco_fornitori"),
    path("fornitori/nuovo/", views.nuovo_fornitore, name="nuovo_fornitore"),
    path(
        "fornitori/<int:pk>/modifica/",
        views.modifica_fornitore,
        name="modifica_fornitore",
    ),
    path("ubicazioni/", views.elenco_ubicazioni, name="elenco_ubicazioni"),
    path("ubicazioni/nuova/", views.nuova_ubicazione, name="nuova_ubicazione"),
    path(
        "ubicazioni/<int:pk>/modifica/",
        views.modifica_ubicazione,
        name="modifica_ubicazione",
    ),
    path("importazioni/", views.importazione_csv, name="importazione_csv"),
    path(
        "importazioni/template/<str:tipo>/",
        views.template_csv,
        name="template_csv",
    ),
    path("backup/", views.gestione_backup, name="gestione_backup"),
    path("backup/esporta/", views.esporta_backup, name="esporta_backup"),
    path("registro-operazioni/", views.registro_operazioni, name="registro_operazioni"),
]
