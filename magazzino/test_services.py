from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import (
    Articolo,
    Confezionamento,
    Giacenza,
    Inscatolamento,
    Lotto,
    Movimento,
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
    conferma_produzione,
    elimina_produzione_bozza,
    elimina_produzione_semilavorato_bozza,
    registra_carico,
    registra_confezionamento,
    registra_consumo,
    registra_inscatolamento,
    registra_prelievi_produzione,
    registra_scarto_prelievo_produzione,
    registra_trasferimento,
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
            categoria=Articolo.Categoria.PRODOTTO_NUDO,
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
            categoria=Articolo.Categoria.PRODOTTO_NUDO,
            unita_misura=Articolo.UnitaMisura.KG,
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
        ricetta = Ricetta.objects.create(
            articolo=cls.prodotto,
            nome="Ricetta test",
        )
        RigaRicetta.objects.create(
            ricetta=ricetta,
            articolo=cls.ingrediente,
            quantita=Decimal("5"),
        )

    def test_produzione_non_puo_essere_confermata_due_volte(self):
        produzione = avvia_produzione(self.prodotto)
        prelievi = registra_prelievi_produzione(
            produzione=produzione,
            articolo=self.ingrediente,
            quantita_richiesta=Decimal("5"),
        )
        for prelievo in prelievi:
            registra_scarto_prelievo_produzione(
                prelievo=prelievo,
                quantita_scarto=Decimal("0"),
            )

        produzione_confermata = conferma_produzione(
            produzione=produzione,
            quantita_prodotta=Decimal("4"),
            ubicazione_destinazione=self.ubicazione_prodotto,
        )

        with self.assertRaisesMessage(ValueError, "non è in bozza"):
            conferma_produzione(
                produzione=produzione,
                quantita_prodotta=Decimal("4"),
                ubicazione_destinazione=self.ubicazione_prodotto,
            )

        self.assertEqual(
            Lotto.objects.filter(articolo=self.prodotto).count(),
            1,
        )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "dettaglio_lotto",
                args=[produzione_confermata.lotto_id],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["tracciabilita_monte"][0]["quantita_scarto"],
            Decimal("0"),
        )


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
        cls.prodotto_nudo = Articolo.objects.create(
            codice="NUDO-PACK",
            descrizione="Prodotto nudo packaging",
            categoria=Articolo.Categoria.PRODOTTO_NUDO,
            unita_misura=Articolo.UnitaMisura.PZ,
            prodotto_finito_collegato=cls.prodotto_finito,
        )
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
            quantita_iniziale=Decimal("10"),
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
            quantita=Decimal("10"),
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
            Giacenza.objects.get(lotto=self.lotto_nudo).quantita,
            Decimal("4"),
        )
        self.assertEqual(
            Giacenza.objects.get(lotto=self.lotto_etichetta).quantita,
            Decimal("14"),
        )
        self.assertEqual(
            Giacenza.objects.get(lotto=confezionamento.lotto_finito).quantita,
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

        with self.assertRaisesMessage(ValueError, "Quantità sfusa insufficiente"):
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
