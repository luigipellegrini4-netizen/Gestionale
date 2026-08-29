from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Articolo,
    CarrelloProduzione,
    Confezionamento,
    Giacenza,
    Inscatolamento,
    Lotto,
    Movimento,
    NonConformitaLotto,
    PrelievoProduzione,
    PrelievoProduzioneSemilavorato,
    Produzione,
    ProduzioneSemilavorato,
    Ricetta,
    RigaRicetta,
    Ubicazione,
)
from .services import (
    avvia_produzione,
    apri_tank_produzione,
    conferma_produzione,
    elimina_produzione_bozza,
    elimina_produzione_semilavorato_bozza,
    registra_carico,
    registra_carico_lotto,
    registra_confezionamento,
    registra_consumo,
    registra_inscatolamento,
    registra_ingredienti_tank,
    registra_prelievi_produzione,
    registra_scarto_prelievo_produzione,
    registra_scarti_tank,
    registra_controlli_tank,
    registra_pastorizzazione,
    registra_verifica_vuoto,
    registra_trasferimento,
    proponi_prelievi_articolo,
    modifica_tank_produzione,
    modifica_risultato_produzione,
    annulla_tank_produzione,
    apri_non_conformita_lotto,
    gestisci_non_conformita_lotto,
)


class OperazioniMagazzinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operatore = get_user_model().objects.create_user(
            username="operatore-magazzino",
            password="password-di-test",
        )
        cls.articolo = Articolo.objects.create(
            codice="MP-TEST",
            descrizione="Materia prima test",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.origine = Ubicazione.objects.create(
            nome="Origine test",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.destinazione = Ubicazione.objects.create(
            nome="Destinazione test",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.articolo,
            codice_lotto="LOT-TEST",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
            peso_unita_acquisto=Decimal("2"),
        )

    def setUp(self):
        self.giacenza = Giacenza.objects.create(
            lotto=self.lotto,
            ubicazione=self.origine,
            quantita=Decimal("10"),
        )

    def test_carico_incrementa_giacenza_e_crea_movimento(self):
        movimento = registra_carico(
            lotto=self.lotto,
            quantita=Decimal("2.5"),
            ubicazione=self.origine,
            operatore=self.operatore,
        )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("12.5"))
        self.assertEqual(movimento.tipo, Movimento.Tipo.CARICO)
        self.assertEqual(movimento.quantita, Decimal("2.5"))
        self.assertEqual(movimento.eseguito_da, self.operatore)

    def test_non_conformita_parziale_quarantena_e_reintegro(self):
        non_conformita = apri_non_conformita_lotto(
            lotto=self.lotto,
            giacenza=self.giacenza,
            numero_uda=3,
            motivo="Confezioni danneggiate",
            operatore=self.operatore,
        )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("4"))
        self.assertEqual(non_conformita.quantita_quarantena, Decimal("6"))
        self.assertTrue(
            Movimento.objects.filter(
                lotto=self.lotto,
                tipo=Movimento.Tipo.QUARANTENA,
                quantita=Decimal("6"),
            ).exists()
        )

        gestisci_non_conformita_lotto(
            non_conformita=non_conformita,
            numero_uda_scartate=1,
            numero_uda_reintegrate=2,
            decisione="Due UDA conformi, una da eliminare",
            responsabile=self.operatore,
        )

        self.giacenza.refresh_from_db()
        non_conformita.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("8"))
        self.assertEqual(non_conformita.stato, NonConformitaLotto.Stato.CHIUSA)
        self.assertEqual(non_conformita.numero_uda_scartate, 1)
        self.assertEqual(non_conformita.numero_uda_reintegrate, 2)
        self.assertTrue(
            Movimento.objects.filter(
                lotto=self.lotto,
                tipo=Movimento.Tipo.REINTEGRO,
                quantita=Decimal("4"),
            ).exists()
        )
        self.assertTrue(
            Movimento.objects.filter(
                lotto=self.lotto,
                tipo=Movimento.Tipo.SCARTO_NC,
                quantita=Decimal("2"),
            ).exists()
        )

    def test_non_conformita_rifiuta_decisione_con_totale_uda_errato(self):
        non_conformita = apri_non_conformita_lotto(
            lotto=self.lotto,
            giacenza=self.giacenza,
            numero_uda=2,
            motivo="Verifica",
            operatore=self.operatore,
        )

        with self.assertRaisesMessage(ValueError, "deve coincidere"):
            gestisci_non_conformita_lotto(
                non_conformita=non_conformita,
                numero_uda_scartate=0,
                numero_uda_reintegrate=1,
                decisione="Decisione incompleta",
                responsabile=self.operatore,
            )

    def test_carico_lotto_crea_posizione_scaffale_e_piano(self):
        lotto, movimento = registra_carico_lotto(
            articolo=self.articolo,
            codice_lotto="LOT-SCAFFALE",
            fornitore=None,
            quantita=Decimal("10"),
            ubicazione=self.origine,
            numero_colli=1,
            unita_acquisto_per_collo=4,
            peso_unita_acquisto=Decimal("2.5"),
            ddt="DDT-TEST-001",
            scaffale="S1",
            piano="P2",
        )

        giacenza = Giacenza.objects.get(lotto=lotto)
        self.assertEqual(giacenza.ubicazione, self.origine)
        self.assertEqual(giacenza.scaffale, "S1")
        self.assertEqual(giacenza.piano, "P2")
        self.assertEqual(movimento.scaffale_destinazione, "S1")
        self.assertEqual(movimento.piano_destinazione, "P2")
        self.assertEqual(lotto.numero_colli, 1)
        self.assertEqual(lotto.unita_acquisto_per_collo, 4)
        self.assertEqual(lotto.numero_unita_acquisto_totali, 4)
        self.assertEqual(lotto.peso_unita_acquisto, Decimal("2.5"))
        self.assertEqual(lotto.ddt, "DDT-TEST-001")

    def test_carico_non_tracciato_genera_riferimento_interno(self):
        articolo = Articolo.objects.create(
            codice="CONS-NO-LOTTO", descrizione="Guanti monouso",
            categoria=Articolo.Categoria.CONSUMABILI,
            unita_misura=Articolo.UnitaMisura.PZ,
            tracciabilita_lotto=False,
        )
        lotto, _ = registra_carico_lotto(
            articolo=articolo,
            codice_lotto="",
            fornitore=None,
            quantita=Decimal("10"),
            ubicazione=self.origine,
            numero_colli=1,
            unita_acquisto_per_collo=10,
            peso_unita_acquisto=Decimal("1"),
            ddt="DDT-NO-LOTTO",
            data_arrivo=date(2026, 8, 29),
        )
        self.assertEqual(lotto.codice_lotto, "NT-260829-001")
        self.assertEqual(lotto.codice_visualizzato, "Non tracciato")

    def test_carichi_stesso_articolo_possono_avere_strutture_diverse(self):
        lotto_a, _ = registra_carico_lotto(
            articolo=self.articolo,
            codice_lotto="FRAGOLE-A",
            fornitore=None,
            quantita=Decimal("10"),
            ubicazione=self.origine,
            numero_colli=1,
            unita_acquisto_per_collo=4,
            peso_unita_acquisto=Decimal("2.5"),
            ddt="DDT-A",
        )
        lotto_b, _ = registra_carico_lotto(
            articolo=self.articolo,
            codice_lotto="FRAGOLE-B",
            fornitore=None,
            quantita=Decimal("20"),
            ubicazione=self.origine,
            numero_colli=1,
            unita_acquisto_per_collo=2,
            peso_unita_acquisto=Decimal("10"),
            fattura="FATT-B",
        )

        self.assertEqual(lotto_a.unita_acquisto_per_collo, 4)
        self.assertEqual(lotto_a.peso_unita_acquisto, Decimal("2.5"))
        self.assertEqual(lotto_b.unita_acquisto_per_collo, 2)
        self.assertEqual(lotto_b.peso_unita_acquisto, Decimal("10"))

    def test_carico_calcola_e_salva_il_dato_mancante(self):
        lotto, _ = registra_carico_lotto(
            articolo=self.articolo,
            codice_lotto="LOT-PESO-CALCOLATO",
            fornitore=None,
            quantita=Decimal("30"),
            ubicazione=self.origine,
            numero_colli=3,
            unita_acquisto_per_collo=2,
            peso_unita_acquisto=None,
            ddt="DDT-CALCOLO",
        )

        lotto.refresh_from_db()
        self.assertEqual(lotto.peso_unita_acquisto, Decimal("5"))

    def test_prelievo_automatico_usa_fefo_e_fifo_a_parita_di_scadenza(self):
        oggi = date.today()
        dati_lotti = [
            ("LOT-SCAD-NUOVO", oggi - timedelta(days=1), oggi + timedelta(days=5)),
            ("LOT-SENZA-SCAD", oggi - timedelta(days=10), None),
            ("LOT-SCAD-VECCHIO", oggi - timedelta(days=2), oggi + timedelta(days=5)),
        ]
        for codice, arrivo, scadenza in dati_lotti:
            lotto = Lotto.objects.create(
                articolo=self.articolo,
                codice_lotto=codice,
                tipo=Lotto.Tipo.ACQUISTO,
                data_arrivo=arrivo,
                data_scadenza=scadenza,
                quantita_iniziale=Decimal("1"),
            )
            Giacenza.objects.create(
                lotto=lotto,
                ubicazione=self.origine,
                quantita=Decimal("1"),
            )

        proposta = proponi_prelievi_articolo(self.articolo, Decimal("3"))

        self.assertEqual(
            [riga["lotto"].codice_lotto for riga in proposta["righe"]],
            ["LOT-SCAD-VECCHIO", "LOT-SCAD-NUOVO", "LOT-SENZA-SCAD"],
        )

    def test_trasferimento_aggiorna_entrambe_le_ubicazioni(self):
        movimento = registra_trasferimento(
            lotto=self.lotto,
            quantita=Decimal("4"),
            ubicazione_origine=self.origine,
            ubicazione_destinazione=self.destinazione,
        )

        self.giacenza.refresh_from_db()
        destinazione = Giacenza.objects.get(
            lotto=self.lotto,
            ubicazione=self.destinazione,
        )
        self.assertEqual(self.giacenza.quantita, Decimal("6"))
        self.assertEqual(destinazione.quantita, Decimal("4"))
        self.assertEqual(movimento.tipo, Movimento.Tipo.TRASFERIMENTO)

    def test_trasferimento_insufficiente_non_modifica_il_magazzino(self):
        with self.assertRaisesMessage(ValueError, "Quantità insufficiente"):
            registra_trasferimento(
                lotto=self.lotto,
                quantita=Decimal("11"),
                ubicazione_origine=self.origine,
                ubicazione_destinazione=self.destinazione,
            )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("10"))
        self.assertFalse(
            Giacenza.objects.filter(
                lotto=self.lotto,
                ubicazione=self.destinazione,
            ).exists()
        )
        self.assertFalse(Movimento.objects.exists())

    def test_consumo_decrementa_giacenza_e_crea_movimento(self):
        movimento = registra_consumo(
            lotto=self.lotto,
            quantita=Decimal("3"),
            ubicazione_origine=self.origine,
        )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("7"))
        self.assertEqual(movimento.tipo, Movimento.Tipo.CONSUMO)

    def test_consumo_insufficiente_non_modifica_la_giacenza(self):
        with self.assertRaisesMessage(ValueError, "Quantità insufficiente"):
            registra_consumo(
                lotto=self.lotto,
                quantita=Decimal("11"),
                ubicazione_origine=self.origine,
            )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("10"))
        self.assertFalse(Movimento.objects.exists())


class VincoliQuantitaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.articolo = Articolo.objects.create(
            codice="VINCOLO-TEST",
            descrizione="Articolo vincoli",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Ubicazione vincoli",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )

    def test_database_rifiuta_lotto_con_quantita_non_positiva(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lotto.objects.create(
                articolo=self.articolo,
                codice_lotto="LOT-ZERO",
                tipo=Lotto.Tipo.ACQUISTO,
                quantita_iniziale=Decimal("0"),
            )

    def test_database_rifiuta_giacenza_negativa(self):
        lotto = Lotto.objects.create(
            articolo=self.articolo,
            codice_lotto="LOT-NEG",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("1"),
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Giacenza.objects.create(
                lotto=lotto,
                ubicazione=self.ubicazione,
                quantita=Decimal("-1"),
            )


class EliminazioneProduzioniBozzaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operatore = get_user_model().objects.create_user(
            username="annullamento-produzione",
            password="password-di-test",
        )
        cls.ingrediente = Articolo.objects.create(
            codice="ING-ANN",
            descrizione="Ingrediente annullamento",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.prodotto = Articolo.objects.create(
            codice="NUDO-ANN",
            descrizione="Prodotto nudo annullamento",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.semilavorato = Articolo.objects.create(
            codice="SEMI-ANN",
            descrizione="Semilavorato annullamento",
            categoria=Articolo.Categoria.SEMILAVORATO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Origine annullamento",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.ingrediente,
            codice_lotto="LOT-ANN",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("20"),
        )

    def setUp(self):
        self.giacenza = Giacenza.objects.create(
            lotto=self.lotto,
            ubicazione=self.ubicazione,
            quantita=Decimal("15"),
        )

    def test_eliminazione_bozza_ripristina_i_prelievi(self):
        produzione = Produzione.objects.create(
            articolo=self.prodotto,
            data_produzione=date.today(),
        )
        PrelievoProduzione.objects.create(
            produzione=produzione,
            lotto=self.lotto,
            ubicazione_origine=self.ubicazione,
            quantita_prelevata=Decimal("5"),
        )

        elimina_produzione_bozza(produzione, operatore=self.operatore)

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("20"))
        self.assertFalse(Produzione.objects.filter(pk=produzione.pk).exists())
        rettifica = Movimento.objects.get(tipo=Movimento.Tipo.RETTIFICA)
        self.assertEqual(rettifica.quantita, Decimal("5"))
        self.assertEqual(rettifica.eseguito_da, self.operatore)

    def test_eliminazione_bozza_semilavorato_ripristina_i_prelievi(self):
        produzione = ProduzioneSemilavorato.objects.create(
            articolo=self.semilavorato,
            data_produzione=date.today(),
        )
        PrelievoProduzioneSemilavorato.objects.create(
            produzione=produzione,
            lotto=self.lotto,
            ubicazione_origine=self.ubicazione,
            quantita_prelevata=Decimal("5"),
        )

        elimina_produzione_semilavorato_bozza(
            produzione,
            operatore=self.operatore,
        )

        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("20"))
        self.assertFalse(
            ProduzioneSemilavorato.objects.filter(pk=produzione.pk).exists()
        )
        self.assertTrue(
            Movimento.objects.filter(
                tipo=Movimento.Tipo.RETTIFICA,
                quantita=Decimal("5"),
            ).exists()
        )

    def test_produzione_confermata_non_puo_essere_eliminata(self):
        produzione = Produzione.objects.create(
            articolo=self.prodotto,
            data_produzione=date.today(),
            stato=Produzione.Stato.CONFERMATA,
        )

        with self.assertRaisesMessage(ValueError, "solo una produzione in bozza"):
            elimina_produzione_bozza(produzione)

        self.assertTrue(Produzione.objects.filter(pk=produzione.pk).exists())


class ConfermaProduzioneTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tracciabilita-test",
            password="password-di-test",
        )
        cls.ingrediente = Articolo.objects.create(
            codice="ING-TEST",
            descrizione="Ingrediente test",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.prodotto = Articolo.objects.create(
            codice="NUDO-TEST",
            descrizione="Prodotto nudo test",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.vasetto = Articolo.objects.create(
            codice="VASO-TEST",
            descrizione="Vasetto test",
            categoria=Articolo.Categoria.MOCA,
            unita_misura=Articolo.UnitaMisura.PZ,
            formato=Decimal("250"),
            unita_formato=Articolo.UnitaFormato.G,
        )
        cls.tappo = Articolo.objects.create(
            codice="TAPPO-TEST",
            descrizione="Tappo test",
            categoria=Articolo.Categoria.MOCA,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.ubicazione_ingrediente = Ubicazione.objects.create(
            nome="Materie prime produzione",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.ubicazione_prodotto = Ubicazione.objects.create(
            nome="Packaging produzione",
            tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING,
        )
        cls.lotto_ingrediente = Lotto.objects.create(
            articolo=cls.ingrediente,
            codice_lotto="ING-LOT",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("20"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_ingrediente,
            ubicazione=cls.ubicazione_ingrediente,
            quantita=Decimal("20"),
        )
        for articolo in (cls.vasetto, cls.tappo):
            lotto = Lotto.objects.create(
                articolo=articolo,
                codice_lotto=f"{articolo.codice}-LOT",
                tipo=Lotto.Tipo.ACQUISTO,
                quantita_iniziale=Decimal("10"),
            )
            Giacenza.objects.create(
                lotto=lotto,
                ubicazione=cls.ubicazione_ingrediente,
                quantita=Decimal("10"),
            )
        ricetta = Ricetta.objects.create(
            articolo=cls.prodotto,
            nome="Ricetta test",
        )
        RigaRicetta.objects.create(
            ricetta=ricetta,
            articolo=cls.ingrediente,
            quantita=Decimal("5"),
        )
        for articolo in (cls.vasetto, cls.tappo):
            RigaRicetta.objects.create(
                ricetta=ricetta,
                articolo=articolo,
                quantita=Decimal("1"),
                ingrediente_prodotto=False,
            )

    def test_produzione_non_puo_essere_confermata_due_volte(self):
        produzione = avvia_produzione(self.prodotto)
        tank = apri_tank_produzione(produzione, numero_batch=1)
        prelievi = registra_prelievi_produzione(
            produzione=produzione,
            articolo=self.ingrediente,
            quantita_richiesta=Decimal("5"),
            tank=tank,
        )
        for prelievo in prelievi:
            registra_scarto_prelievo_produzione(
                prelievo=prelievo,
                quantita_scarto=Decimal("0"),
            )
        tank = registra_controlli_tank(tank, gradi_brix="65", ph="3.20")
        self.assertIsNotNone(tank.data_ora_controlli)
        produzione.moca_igienizzati = True
        produzione.stato_roboqubo = Produzione.StatoRoboqubo.CONCLUSA
        produzione.save(update_fields=["moca_igienizzati", "stato_roboqubo"])
        CarrelloProduzione.objects.create(
            produzione=produzione,
            numero=1,
            esito_pastorizzazione="C",
            esito_shock_vuoto="C",
            shock_vuoto_registrato_il=timezone.now(),
            chiuso_il=timezone.now(),
        )

        produzione_confermata = conferma_produzione(
            produzione=produzione,
            quantita_prodotta=Decimal("4"),
            quantita_ottenuta_kg=Decimal("1"),
            ubicazione_destinazione=self.ubicazione_prodotto,
            pastorizzazione_completata=True,
            vuoto_controllato=True,
        )

        with self.assertRaisesMessage(ValueError, "non è in bozza"):
            conferma_produzione(
                produzione=produzione,
                quantita_prodotta=Decimal("4"),
                ubicazione_destinazione=self.ubicazione_prodotto,
                pastorizzazione_completata=True,
                vuoto_controllato=True,
            )

        self.assertEqual(
            Lotto.objects.filter(articolo=self.prodotto).count(),
            1,
        )
        self.assertEqual(
            produzione_confermata.lotto.fase,
            Lotto.Fase.INVASETTATO,
        )
        self.assertEqual(produzione_confermata.quantita_ottenuta_kg, Decimal("1"))
        self.assertEqual(produzione_confermata.quantita_teorica_kg, Decimal("5"))
        self.assertEqual(
            produzione_confermata.stato_invasettamento,
            Produzione.StatoInvasettamento.CONCLUSO,
        )
        self.assertEqual(produzione_confermata.resa_percentuale, Decimal("20"))
        self.assertIsNotNone(produzione_confermata.data_ora_pastorizzazione)
        self.assertIsNotNone(produzione_confermata.data_ora_verifica_vuoto)
        self.assertEqual(
            Giacenza.objects.get(lotto__articolo=self.vasetto).quantita,
            Decimal("6"),
        )
        self.assertEqual(
            Giacenza.objects.get(lotto__articolo=self.tappo).quantita,
            Decimal("6"),
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "dettaglio_lotto",
                args=[produzione_confermata.lotto_id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dati e controlli di produzione")
        self.assertContains(response, "Controlli dei tank")
        self.assertContains(response, "65,00")
        self.assertContains(response, "3,20")
        self.assertContains(response, "Pastorizzazione")
        self.assertContains(response, "Verifica del vuoto")
        self.assertEqual(
            response.context["tracciabilita_monte"][0]["quantita_scarto"],
            Decimal("0"),
        )

        modifica_risultato_produzione(
            produzione_confermata,
            lotto_definitivo="LOTTO-CORRETTO",
            quantita_prodotta=5,
            peso_netto_vasetto_g=250,
            pezzi_difettosi_finali=2,
            capsule_difettose_finali=1,
            note="Correzione test",
            operatore=self.user,
        )
        produzione_confermata.refresh_from_db()
        produzione_confermata.lotto.refresh_from_db()
        self.assertEqual(produzione_confermata.lotto.codice_lotto, "LOTTO-CORRETTO")
        self.assertEqual(produzione_confermata.quantita_prodotta, Decimal("5"))
        self.assertEqual(produzione_confermata.quantita_ottenuta_kg, Decimal("1.75"))
        self.assertEqual(produzione_confermata.resa_percentuale, Decimal("35"))
        self.assertEqual(
            Giacenza.objects.get(lotto=produzione_confermata.lotto).quantita,
            Decimal("5"),
        )

    def test_prelievo_arrotonda_a_uda_intere_e_deposita_avanzo_in_produzione(self):
        Giacenza.objects.filter(lotto=self.lotto_ingrediente).update(quantita=0)
        ubicazione_produzione = Ubicazione.objects.create(
            nome="Magazzino produzione test",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        lotto = Lotto.objects.create(
            articolo=self.ingrediente,
            codice_lotto="ING-UDA-25",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("100"),
            peso_unita_acquisto=Decimal("25"),
        )
        giacenza = Giacenza.objects.create(
            lotto=lotto,
            ubicazione=self.ubicazione_ingrediente,
            quantita=Decimal("100"),
        )
        produzione = avvia_produzione(self.prodotto)

        prelievi = registra_prelievi_produzione(
            produzione=produzione,
            articolo=self.ingrediente,
            quantita_richiesta=Decimal("70"),
        )

        prelievo = next(p for p in prelievi if p.lotto_id == lotto.pk)
        giacenza.refresh_from_db()
        self.assertEqual(prelievo.quantita_prelevata, Decimal("70"))
        self.assertEqual(prelievo.quantita_movimentata, Decimal("75"))
        self.assertEqual(prelievo.quantita_resa_produzione, Decimal("5"))
        self.assertEqual(giacenza.quantita, Decimal("25"))
        self.assertEqual(
            Giacenza.objects.get(
                lotto=lotto, ubicazione=ubicazione_produzione,
            ).quantita,
            Decimal("5"),
        )

    def test_non_apre_un_secondo_tank_prima_dei_controlli(self):
        produzione = avvia_produzione(self.prodotto)
        tank = apri_tank_produzione(produzione, numero_batch=8)

        self.assertEqual(tank.numero, 1)
        self.assertEqual(tank.numero_batch, 8)
        with self.assertRaisesMessage(ValueError, "tank aperto"):
            apri_tank_produzione(produzione, numero_batch=1)

    def test_modifica_e_annullamento_tank_restano_nello_storico(self):
        produzione = avvia_produzione(self.prodotto)
        tank = apri_tank_produzione(produzione, numero_batch=5)

        tank = modifica_tank_produzione(tank, numero_batch=7)
        self.assertEqual(tank.numero_batch, 7)

        tank = annulla_tank_produzione(
            tank,
            motivo="Non conformità organolettica",
            operatore=self.user,
        )
        self.assertTrue(tank.annullato)
        self.assertEqual(tank.motivo_annullamento, "Non conformità organolettica")
        self.assertIsNotNone(tank.data_ora_annullamento)
        self.assertEqual(tank.annullato_da, self.user)

        nuovo_tank = apri_tank_produzione(produzione, numero_batch=5)
        self.assertEqual(nuovo_tank.numero, 2)

    def test_registra_separatamente_orari_pastorizzazione_e_sottovuoto(self):
        produzione = avvia_produzione(self.prodotto)

        produzione = registra_pastorizzazione(produzione)
        self.assertTrue(produzione.pastorizzazione_completata)
        self.assertIsNotNone(produzione.data_ora_pastorizzazione)
        self.assertFalse(produzione.vuoto_controllato)

        produzione = registra_verifica_vuoto(produzione)
        self.assertTrue(produzione.vuoto_controllato)
        self.assertIsNotNone(produzione.data_ora_verifica_vuoto)

    def test_registra_tutti_gli_ingredienti_del_tank(self):
        produzione = avvia_produzione(self.prodotto)
        tank = apri_tank_produzione(produzione, numero_batch=2)

        prelievi = registra_ingredienti_tank(
            produzione=produzione,
            tank=tank,
            quantita_per_articolo={self.ingrediente.pk: Decimal("10")},
            note_per_articolo={self.ingrediente.pk: "Correzione operatore"},
        )

        self.assertTrue(prelievi)
        self.assertEqual(tank.prelievi.count(), len(prelievi))
        self.assertTrue(all(p.note == "Correzione operatore" for p in prelievi))

        registrati = registra_scarti_tank(
            produzione,
            tank,
            {prelievo.pk: Decimal("0") for prelievo in prelievi},
            {prelievo.pk: "Nessuno scarto" for prelievo in prelievi},
        )
        self.assertEqual(len(registrati), len(prelievi))
        self.assertFalse(tank.prelievi.filter(quantita_scarto__isnull=True).exists())


class ConfezionamentoInscatolamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operatore = get_user_model().objects.create_user(
            username="operatore-packaging",
            password="password-di-test",
        )
        cls.prodotto_finito = Articolo.objects.create(
            codice="FINITO-PACK",
            descrizione="Prodotto finito packaging",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.prodotto_nudo = cls.prodotto_finito
        cls.etichetta = Articolo.objects.create(
            codice="ETI-PACK",
            descrizione="Etichetta packaging",
            categoria=Articolo.Categoria.PACKAGING,
            unita_misura=Articolo.UnitaMisura.PZ,
            tipo_packaging=Articolo.TipoPackaging.ETICHETTA,
        )
        cls.scatola = Articolo.objects.create(
            codice="SCA-PACK",
            descrizione="Scatola packaging",
            categoria=Articolo.Categoria.PACKAGING,
            unita_misura=Articolo.UnitaMisura.PZ,
            tipo_packaging=Articolo.TipoPackaging.SCATOLA,
            pezzi_per_imballo=6,
        )
        cls.ubicazione_packaging = Ubicazione.objects.create(
            nome="Packaging test completo",
            tipo_magazzino=Ubicazione.TipoMagazzino.PACKAGING,
        )
        cls.ubicazione_finiti = Ubicazione.objects.create(
            nome="Finiti test completo",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.lotto_nudo = Lotto.objects.create(
            articolo=cls.prodotto_nudo,
            codice_lotto="PACK-LOT",
            tipo=Lotto.Tipo.PRODUZIONE,
            fase=Lotto.Fase.INVASETTATO,
            quantita_iniziale=Decimal("6"),
        )
        cls.lotto_etichetta = Lotto.objects.create(
            articolo=cls.etichetta,
            codice_lotto="ETI-LOT",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("20"),
        )
        cls.lotto_scatola = Lotto.objects.create(
            articolo=cls.scatola,
            codice_lotto="SCA-LOT",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
        )

    def setUp(self):
        Giacenza.objects.create(
            lotto=self.lotto_nudo,
            ubicazione=self.ubicazione_packaging,
            quantita=Decimal("6"),
        )
        Giacenza.objects.create(
            lotto=self.lotto_etichetta,
            ubicazione=self.ubicazione_packaging,
            quantita=Decimal("20"),
        )
        Giacenza.objects.create(
            lotto=self.lotto_scatola,
            ubicazione=self.ubicazione_packaging,
            quantita=Decimal("10"),
        )

    def confeziona_sei_pezzi(self):
        return registra_confezionamento(
            lotto_origine=self.lotto_nudo,
            articolo_finito=self.prodotto_finito,
            quantita_confezionata=Decimal("6"),
            consumi={self.lotto_etichetta: Decimal("6")},
            ubicazione_origine=self.ubicazione_packaging,
            ubicazione_destinazione=self.ubicazione_finiti,
            operatore=self.operatore,
        )

    def test_confezionamento_aggiorna_tutte_le_giacenze(self):
        confezionamento = self.confeziona_sei_pezzi()

        self.assertIsInstance(confezionamento, Confezionamento)
        self.assertEqual(
            Giacenza.objects.get(
                lotto=self.lotto_nudo,
                ubicazione=self.ubicazione_packaging,
            ).quantita,
            Decimal("0"),
        )
        self.assertEqual(
            Giacenza.objects.get(lotto=self.lotto_etichetta).quantita,
            Decimal("14"),
        )
        self.assertEqual(
            Giacenza.objects.get(
                lotto=confezionamento.lotto_finito,
                ubicazione=self.ubicazione_finiti,
            ).quantita,
            Decimal("6"),
        )
        self.assertEqual(Movimento.objects.count(), 3)
        self.assertFalse(
            Movimento.objects.exclude(eseguito_da=self.operatore).exists()
        )

    def test_inscatolamento_non_puo_usare_due_volte_lo_stesso_sfuso(self):
        confezionamento = self.confeziona_sei_pezzi()
        inscatolamento = registra_inscatolamento(
            lotto_prodotto=confezionamento.lotto_finito,
            lotto_imballo=self.lotto_scatola,
            quantita_prodotti=Decimal("6"),
            ubicazione_prodotto=self.ubicazione_finiti,
            ubicazione_imballo=self.ubicazione_packaging,
            operatore=self.operatore,
        )

        self.assertIsInstance(inscatolamento, Inscatolamento)
        self.assertEqual(inscatolamento.quantita_imballi, Decimal("1"))
        self.assertEqual(
            Giacenza.objects.get(lotto=self.lotto_scatola).quantita,
            Decimal("9"),
        )

        with self.assertRaisesMessage(ValueError, "deve essere etichettato"):
            registra_inscatolamento(
                lotto_prodotto=confezionamento.lotto_finito,
                lotto_imballo=self.lotto_scatola,
                quantita_prodotti=Decimal("6"),
                ubicazione_prodotto=self.ubicazione_finiti,
                ubicazione_imballo=self.ubicazione_packaging,
                operatore=self.operatore,
            )

        self.assertEqual(Inscatolamento.objects.count(), 1)
        self.assertEqual(
            Giacenza.objects.get(lotto=self.lotto_scatola).quantita,
            Decimal("9"),
        )
