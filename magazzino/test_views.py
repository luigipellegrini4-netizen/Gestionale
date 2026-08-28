from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import (
    Articolo,
    Giacenza,
    Inscatolamento,
    Lotto,
    Movimento,
    NonConformitaLotto,
    Produzione,
    Ricetta,
    Ubicazione,
)


class SituazioneMagazzinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="situazione-test",
            password="password-di-test",
        )
        cls.prodotto = Articolo.objects.create(
            codice="PF-TEST",
            descrizione="Prodotto finito test",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
            quantita_per_confezione=Decimal("10"),
        )
        cls.imballo = Articolo.objects.create(
            codice="SCATOLA-TEST",
            descrizione="Scatola test",
            categoria=Articolo.Categoria.PACKAGING,
            unita_misura=Articolo.UnitaMisura.PZ,
            tipo_packaging=Articolo.TipoPackaging.SCATOLA,
            pezzi_per_imballo=6,
        )
        cls.ubicazione_a = Ubicazione.objects.create(
            nome="Prodotti finiti A",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.ubicazione_b = Ubicazione.objects.create(
            nome="Prodotti finiti B",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.lotto_prodotto = Lotto.objects.create(
            articolo=cls.prodotto,
            codice_lotto="PF-LOT",
            tipo=Lotto.Tipo.PRODUZIONE,
            quantita_iniziale=Decimal("10"),
        )
        cls.lotto_imballo = Lotto.objects.create(
            articolo=cls.imballo,
            codice_lotto="IMB-LOT",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
            fattura="FATT-LOT-01",
            ddt="DDT-LOT-01",
            numero_colli=2,
            unita_acquisto_per_collo=5,
            peso_unita_acquisto=Decimal("1.25"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_prodotto,
            ubicazione=cls.ubicazione_a,
            quantita=Decimal("7"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_prodotto,
            ubicazione=cls.ubicazione_b,
            quantita=Decimal("3"),
        )
        Inscatolamento.objects.create(
            lotto_prodotto=cls.lotto_prodotto,
            lotto_imballo=cls.lotto_imballo,
            quantita_prodotti=Decimal("6"),
            quantita_imballi=Decimal("1"),
            pezzi_per_imballo=6,
            data_inscatolamento=date.today(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_totali_sono_calcolati_correttamente(self):
        response = self.client.get(reverse("situazione_magazzino"))

        self.assertEqual(response.status_code, 200)
        prodotto = next(
            articolo
            for articolo in response.context["articoli"]
            if articolo.pk == self.prodotto.pk
        )
        self.assertEqual(prodotto.giacenza_totale, Decimal("10"))

    def test_operatore_vede_il_pulsante_scarico_materiale(self):
        permesso = Permission.objects.get(codename="operare_magazzino")
        self.user.user_permissions.add(permesso)
        self.client.force_login(self.user)

        response = self.client.get(reverse("situazione_magazzino"))

        self.assertContains(response, reverse("consumo"))
        self.assertContains(response, "Scarico materiale")

    def test_registro_generale_non_conformita_senza_lotto(self):
        self.user.user_permissions.add(
            Permission.objects.get(codename="operare_magazzino")
        )
        self.client.force_login(self.user)
        apertura = self.client.post(
            reverse("apri_non_conformita_generale"),
            {
                "ambito": NonConformitaLotto.Ambito.COMMERCIALE,
                "tipo_nc": NonConformitaLotto.Tipo.RECLAMO_CLIENTE,
                "lotto": "",
                "motivo": "Segnalazione commerciale di prova",
                "note_apertura": "Contatto immediato con il cliente",
            },
        )
        self.assertRedirects(apertura, reverse("registro_non_conformita"))
        nc = NonConformitaLotto.objects.get(
            motivo="Segnalazione commerciale di prova"
        )
        self.assertIsNone(nc.lotto)
        self.assertEqual(nc.stato, NonConformitaLotto.Stato.APERTA)

        registro = self.client.get(
            reverse("registro_non_conformita"), {"q": str(nc.pk)}
        )
        self.assertContains(registro, f"NC-{nc.pk}")
        self.assertContains(registro, "Reclamo del Cliente")

        self.user.user_permissions.add(
            Permission.objects.get(codename="gestire_non_conformita")
        )
        self.client.force_login(self.user)
        lavorazione = self.client.post(
            reverse("gestisci_non_conformita", args=[nc.pk]),
            {
                "analisi_cause": "Analisi iniziale",
                "azione_risoluzione": "Contattare il cliente",
                "azione": "salva",
            },
        )
        self.assertRedirects(lavorazione, reverse("registro_non_conformita"))
        nc.refresh_from_db()
        self.assertEqual(nc.stato, NonConformitaLotto.Stato.IN_LAVORAZIONE)

    def test_apertura_generale_ricerca_lotto_e_mette_uda_in_quarantena(self):
        giacenza = Giacenza.objects.create(
            lotto=self.lotto_imballo,
            ubicazione=self.ubicazione_a,
            quantita=Decimal("10"),
        )
        self.user.user_permissions.add(
            Permission.objects.get(codename="operare_magazzino")
        )
        self.client.force_login(self.user)

        ricerca = self.client.get(
            reverse("ricerca_lotti_non_conformita"), {"q": "IMB-LOT"}
        )
        self.assertEqual(ricerca.status_code, 200)
        self.assertEqual(
            ricerca.json()["risultati"][0]["id"], self.lotto_imballo.pk
        )

        apertura = self.client.post(
            reverse("apri_non_conformita_generale"),
            {
                "ambito": NonConformitaLotto.Ambito.PRODUZIONE,
                "tipo_nc": NonConformitaLotto.Tipo.VERSO_FORNITORE,
                "lotto": self.lotto_imballo.pk,
                "giacenza": giacenza.pk,
                "numero_uda": 2,
                "motivo": "Materiale non idoneo",
                "note_apertura": "Isolamento immediato",
            },
        )

        self.assertRedirects(apertura, reverse("registro_non_conformita"))
        giacenza.refresh_from_db()
        nc = NonConformitaLotto.objects.get(motivo="Materiale non idoneo")
        self.assertEqual(nc.numero_uda_quarantena, 2)
        self.assertEqual(nc.quantita_quarantena, Decimal("2.5"))
        self.assertEqual(giacenza.quantita, Decimal("7.5"))

    def test_articoli_sono_ordinati_e_separati_per_categoria(self):

        response = self.client.get(reverse("situazione_magazzino"))

        articoli = list(response.context["articoli"])
        self.assertEqual([a.pk for a in articoli], [self.imballo.pk, self.prodotto.pk])

        self.assertEqual(
            [gruppo["nome"] for gruppo in response.context["gruppi_articoli"]],
            ["Packaging", "Prodotto finito"],
        )
        self.assertContains(response, 'class="category-group-header"', count=2)

    def test_articolo_rimanda_alla_scheda_e_ai_suoi_lotti(self):
        situazione = self.client.get(reverse("situazione_magazzino"))

        self.assertContains(
            situazione,
            reverse("dettaglio_articolo", args=[self.prodotto.pk]),
        )
        self.assertNotContains(situazione, "Dettaglio giacenze per lotto")

        dettaglio_articolo = self.client.get(
            reverse("dettaglio_articolo", args=[self.prodotto.pk])
        )
        self.assertContains(
            dettaglio_articolo,
            reverse("dettaglio_lotto", args=[self.lotto_prodotto.pk]),
        )

    def test_dettaglio_articolo_mostra_quantita_per_confezione(self):
        response = self.client.get(
            reverse("dettaglio_articolo", args=[self.prodotto.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unità per confezione di acquisto")
        self.assertContains(response, "10")

    def test_dettaglio_lotto_mostra_documenti_e_struttura_acquisto(self):
        response = self.client.get(
            reverse("dettaglio_lotto", args=[self.lotto_imballo.pk])
        )

        self.assertContains(response, "FATT-LOT-01")
        self.assertContains(response, "DDT-LOT-01")
        self.assertContains(response, "Numero colli")
        self.assertContains(response, "Numero di unità di acquisto per collo")
        self.assertContains(response, "Unità di acquisto totali")
        self.assertContains(response, "Peso della singola unità di acquisto")

    def test_apertura_e_gestione_non_conformita_da_dettaglio_lotto(self):
        giacenza = Giacenza.objects.create(
            lotto=self.lotto_imballo,
            ubicazione=self.ubicazione_a,
            quantita=Decimal("10"),
        )
        permesso_operatore = Permission.objects.get(codename="operare_magazzino")
        self.user.user_permissions.add(permesso_operatore)
        self.client.force_login(self.user)

        apertura = self.client.post(
            reverse("apri_non_conformita", args=[self.lotto_imballo.pk]),
            {
                "giacenza": giacenza.pk,
                "numero_uda": 2,
                "ambito": NonConformitaLotto.Ambito.PRODUZIONE,
                "tipo_nc": NonConformitaLotto.Tipo.INTERNO,
                "motivo": "Imballi danneggiati",
                "note": "Controllare il trasporto",
            },
        )

        self.assertRedirects(
            apertura,
            reverse("dettaglio_lotto", args=[self.lotto_imballo.pk]),
        )
        non_conformita = NonConformitaLotto.objects.get(lotto=self.lotto_imballo)
        giacenza.refresh_from_db()
        self.assertEqual(giacenza.quantita, Decimal("7.5"))

        senza_permesso = self.client.get(
            reverse("gestisci_non_conformita", args=[non_conformita.pk])
        )
        self.assertEqual(senza_permesso.status_code, 403)

        permesso_qualita = Permission.objects.get(
            codename="gestire_non_conformita"
        )
        self.user.user_permissions.add(permesso_qualita)
        self.client.force_login(self.user)
        gestione = self.client.post(
            reverse("gestisci_non_conformita", args=[non_conformita.pk]),
            {
                "numero_uda_scartate": 1,
                "numero_uda_reintegrate": 1,
                "decisione": "Una UDA recuperata e una scartata",
                "analisi_cause": "Danno durante la movimentazione",
                "azione_risoluzione": "Revisione della movimentazione",
                "responsabile_azione": "Responsabile magazzino",
                "data_inizio_gestione": "2026-08-28",
                "azione_immediata": "on",
                "scadenza_prevista": "",
                "esito_efficacia": NonConformitaLotto.EsitoEfficacia.EFFICACE,
                "verifica_efficacia": "Controllo completato",
                "data_verifica": "2026-08-28",
                "azione": "chiudi",
            },
        )

        self.assertRedirects(
            gestione,
            reverse("registro_non_conformita"),
        )
        giacenza.refresh_from_db()
        non_conformita.refresh_from_db()
        self.assertEqual(giacenza.quantita, Decimal("8.75"))
        self.assertEqual(non_conformita.stato, NonConformitaLotto.Stato.CHIUSA)

        dettaglio = self.client.get(
            reverse("dettaglio_lotto", args=[self.lotto_imballo.pk])
        )
        self.assertContains(dettaglio, f"NC-{non_conformita.pk}")
        self.assertContains(dettaglio, "Una UDA recuperata e una scartata")

    def test_dettaglio_articolo_mostra_formato(self):
        vasetto = Articolo.objects.create(
            codice="VASO-250",
            descrizione="Vasetto 250 g",
            categoria=Articolo.Categoria.MOCA,
            unita_misura=Articolo.UnitaMisura.PZ,
            formato=Decimal("250"),
            unita_formato=Articolo.UnitaFormato.G,
        )

        response = self.client.get(reverse("dettaglio_articolo", args=[vasetto.pk]))

        self.assertContains(response, "Formato del singolo articolo")
        self.assertContains(response, "250")
        self.assertContains(response, "g")

    def test_tabella_lotti_mostra_la_giacenza_attuale(self):
        response = self.client.get(
            reverse("dettaglio_articolo", args=[self.prodotto.pk])
        )

        lotto = next(
            lotto
            for lotto in response.context["lotti"]
            if lotto.pk == self.lotto_prodotto.pk
        )
        self.assertEqual(lotto.giacenza_attuale, Decimal("10"))
        self.assertContains(response, "Giacenza attuale")

    def test_numero_query_non_cresce_per_articolo_o_lotto(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("situazione_magazzino"))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 12)

    def test_movimenti_sono_paginati_a_cinquanta(self):
        Movimento.objects.bulk_create(
            [
                Movimento(
                    tipo=Movimento.Tipo.CARICO,
                    lotto=self.lotto_prodotto,
                    quantita=Decimal("1"),
                    ubicazione_destinazione=self.ubicazione_a,
                )
                for _ in range(51)
            ]
        )

        prima_pagina = self.client.get(reverse("elenco_movimenti"))
        seconda_pagina = self.client.get(
            reverse("elenco_movimenti"),
            {"page": 2},
        )

        self.assertEqual(len(prima_pagina.context["movimenti"]), 50)
        self.assertEqual(len(seconda_pagina.context["movimenti"]), 1)
        self.assertContains(prima_pagina, "Pagina 1 di 2")


class TrasferimentoGuidatoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="trasferimento-test",
            password="password-di-test",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="operare_magazzino")
        )
        cls.articolo = Articolo.objects.create(
            codice="MP-TRASF",
            descrizione="Materia prima da trasferire",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.altro_articolo = Articolo.objects.create(
            codice="MP-ALTRO",
            descrizione="Altro articolo",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.origine = Ubicazione.objects.create(
            nome="Origine trasferimento",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
            scaffale="A",
            piano="1",
        )
        cls.destinazione = Ubicazione.objects.create(
            nome="Destinazione trasferimento",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.articolo,
            codice_lotto="LOT-TRASF",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
        )
        cls.lotto_altro = Lotto.objects.create(
            articolo=cls.altro_articolo,
            codice_lotto="LOT-ALTRO",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("5"),
        )
        cls.giacenza = Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.origine,
            quantita=Decimal("8"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_altro,
            ubicazione=cls.origine,
            quantita=Decimal("5"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.destinazione,
            quantita=Decimal("0"),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_disponibilita_mostra_solo_lotti_positivi_dell_articolo(self):
        response = self.client.get(
            reverse("disponibilita_trasferimento"),
            {"articolo": self.articolo.pk},
        )

        self.assertEqual(response.status_code, 200)
        righe = response.json()["disponibilita"]
        self.assertEqual(len(righe), 1)
        self.assertEqual(righe[0]["id"], self.giacenza.pk)
        self.assertEqual(righe[0]["lotto"], "LOT-TRASF")
        self.assertIn("Scaffale A", righe[0]["posizione"])
        self.assertEqual(righe[0]["quantita"], "8.000000")

    def test_trasferimento_usa_lotto_e_origine_della_giacenza(self):
        response = self.client.post(
            reverse("trasferimento"),
            {
                "articolo": self.articolo.pk,
                "giacenza": self.giacenza.pk,
                "ubicazione_destinazione": self.destinazione.pk,
                "quantita": "3",
                "note": "Test guidato",
            },
        )

        self.assertRedirects(response, reverse("trasferimento"))
        self.giacenza.refresh_from_db()
        destinazione = Giacenza.objects.get(
            lotto=self.lotto,
            ubicazione=self.destinazione,
        )
        self.assertEqual(self.giacenza.quantita, Decimal("5"))
        self.assertEqual(destinazione.quantita, Decimal("3"))
        movimento = Movimento.objects.latest("pk")
        self.assertEqual(movimento.ubicazione_origine, self.origine)
        self.assertEqual(movimento.ubicazione_destinazione, self.destinazione)

    def test_quantita_superiore_alla_disponibilita_viene_rifiutata(self):
        response = self.client.post(
            reverse("trasferimento"),
            {
                "articolo": self.articolo.pk,
                "giacenza": self.giacenza.pk,
                "ubicazione_destinazione": self.destinazione.pk,
                "quantita": "9",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "quantita",
            "Disponibilità insufficiente: massimo 8.000000.",
        )
        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("8"))


class RicercaLottiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ricerca-lotti-test",
            password="password-di-test",
        )
        cls.articolo = Articolo.objects.create(
            codice="CONF-ALB",
            descrizione="Confettura albicocca",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.altro_articolo = Articolo.objects.create(
            codice="CONF-FRAG",
            descrizione="Confettura fragola",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.ubicazione_a = Ubicazione.objects.create(
            nome="Ricerca A",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.ubicazione_b = Ubicazione.objects.create(
            nome="Ricerca B",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.articolo,
            codice_lotto="ALB-2026-001",
            tipo=Lotto.Tipo.PRODUZIONE,
            quantita_iniziale=Decimal("20"),
        )
        cls.lotto_altro = Lotto.objects.create(
            articolo=cls.altro_articolo,
            codice_lotto="FRAG-2026-001",
            tipo=Lotto.Tipo.PRODUZIONE,
            quantita_iniziale=Decimal("10"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.ubicazione_a,
            quantita=Decimal("7"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.ubicazione_b,
            quantita=Decimal("5"),
        )
        Movimento.objects.create(
            tipo=Movimento.Tipo.CARICO,
            lotto=cls.lotto,
            quantita=Decimal("20"),
            ubicazione_destinazione=cls.ubicazione_a,
        )
        Movimento.objects.create(
            tipo=Movimento.Tipo.TRASFERIMENTO,
            lotto=cls.lotto,
            quantita=Decimal("5"),
            ubicazione_origine=cls.ubicazione_a,
            ubicazione_destinazione=cls.ubicazione_b,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_ricerca_per_codice_lotto(self):
        response = self.client.get(
            reverse("ricerca_lotti"),
            {"q": "ALB-2026"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["lotti"].paginator.count, 1)
        risultato = response.context["lotti"][0]
        self.assertEqual(risultato.pk, self.lotto.pk)
        self.assertEqual(risultato.giacenza_totale, Decimal("12"))
        self.assertIsNotNone(risultato.ultimo_movimento)

    def test_ricerca_per_descrizione_articolo(self):
        response = self.client.get(
            reverse("ricerca_lotti"),
            {"q": "albicocca"},
        )

        self.assertContains(response, "ALB-2026-001")
        self.assertNotContains(response, "FRAG-2026-001")
        self.assertContains(
            response,
            reverse("dettaglio_lotto", args=[self.lotto.pk]),
        )


class ElencoRicetteSeparateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ricette-separate-test",
            password="password-di-test",
        )
        prodotto = Articolo.objects.create(
            codice="PROD-RIC",
            descrizione="Prodotto ricetta",
            nome_produzione="Prodotto operativo",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        semilavorato = Articolo.objects.create(
            codice="SEMI-RIC",
            descrizione="Semilavorato ricetta",
            categoria=Articolo.Categoria.SEMILAVORATO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ricetta_prodotto = Ricetta.objects.create(
            articolo=prodotto,
            nome="Ricetta prodotto test",
        )
        cls.ricetta_semilavorato = Ricetta.objects.create(
            articolo=semilavorato,
            nome="Ricetta semilavorato test",
        )

    def test_ricette_sono_divise_per_tipo(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("elenco_ricette"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ricette dei prodotti")
        self.assertContains(response, "Ricette dei semilavorati")
        self.assertEqual(
            list(response.context["ricette_prodotti"]),
            [self.ricetta_prodotto],
        )
        self.assertEqual(
            list(response.context["ricette_semilavorati"]),
            [self.ricetta_semilavorato],
        )

    def test_elenco_ricette_non_filtra_per_fase_del_lotto(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("elenco_ricette"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.ricetta_prodotto.nome)


class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="dashboard-test",
            password="password-di-test",
        )
        cls.articolo = Articolo.objects.create(
            codice="SCORTA-DASH",
            descrizione="Articolo sotto scorta",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
            scorta_minima=Decimal("10"),
        )
        cls.prodotto = Articolo.objects.create(
            codice="PROD-DASH",
            descrizione="Prodotto dashboard",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Dashboard magazzino",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.articolo,
            codice_lotto="LOT-DASH",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("5"),
            data_scadenza=date.today() + timedelta(days=10),
        )
        Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.ubicazione,
            quantita=Decimal("5"),
        )
        Movimento.objects.create(
            tipo=Movimento.Tipo.CARICO,
            lotto=cls.lotto,
            quantita=Decimal("5"),
            ubicazione_destinazione=cls.ubicazione,
        )
        Produzione.objects.create(
            articolo=cls.prodotto,
            data_produzione=date.today(),
        )

    def test_home_mostra_indicatori_operativi(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["numero_sotto_scorta"], 1)
        self.assertEqual(response.context["numero_lotti_scadenza"], 1)
        self.assertEqual(response.context["numero_produzioni_bozza"], 1)
        self.assertEqual(response.context["movimenti_oggi"], 1)
        self.assertContains(response, "LOT-DASH")
        self.assertContains(response, "SCORTA-DASH")
