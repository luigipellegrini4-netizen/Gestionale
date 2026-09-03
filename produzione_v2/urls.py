from django.urls import path

from . import views

app_name = "produzione_v2"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("postazioni/", views.postazioni, name="postazioni"),
    path("postazioni/<str:ruolo>/", views.postazione_operatore, name="postazione_operatore"),
    path(
        "postazioni/b/ordini/<int:ordine_pk>/", views.lavorazione_roboqbo,
        name="lavorazione_roboqbo",
    ),
    path("mie-attivita/", views.mie_attivita, name="mie_attivita"),
    path("report/", views.report_produzione, name="report_produzione"),
    path("report.csv", views.esporta_report_produzione, name="esporta_report_produzione"),
    path(
        "preset/roboqbo-invasettamento/",
        views.applica_preset_roboqbo_invasettamento,
        name="applica_preset_roboqbo_invasettamento",
    ),
    path("linee/nuova/", views.nuova_linea, name="nuova_linea"),
    path("linee/<int:pk>/", views.dettaglio_linea, name="dettaglio_linea"),
    path("stazioni/nuova/", views.nuova_stazione, name="nuova_stazione"),
    path("stazioni/<int:pk>/", views.dettaglio_stazione, name="dettaglio_stazione"),
    path("cicli/nuovo/", views.nuovo_ciclo, name="nuovo_ciclo"),
    path("cicli/<int:pk>/", views.dettaglio_ciclo, name="dettaglio_ciclo"),
    path("ordini/nuovo/", views.nuovo_ordine, name="nuovo_ordine"),
    path("tracciabilita/", views.ricerca_tracciabilita, name="ricerca_tracciabilita"),
    path("ordini/<int:pk>/", views.dettaglio_ordine, name="dettaglio_ordine"),
    path(
        "ordini/<int:pk>/tracciabilita/", views.tracciabilita_ordine,
        name="tracciabilita_ordine",
    ),
    path(
        "ordini/<int:pk>/tracciabilita.csv", views.esporta_tracciabilita_ordine,
        name="esporta_tracciabilita_ordine",
    ),
]
