from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from .forms import (
    BatchProduzioneForm, CarrelloProduzioneForm,
    ConfermaProduzioneForm, ProduzioneForm,
)
from .models import Articolo, BatchProduzione, CarrelloProduzione, Lotto, Produzione, TankProduzione
from .services import genera_codice_lotto_produzione, registra_controlli_tank


class FlussoProduzioneTreFasiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.articolo = Articolo.objects.create(
            codice="PF-FLUSSO", descrizione="Prodotto test flusso",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )

    def setUp(self):
        self.produzione = Produzione.objects.create(
            articolo=self.articolo, data_produzione=date(2026, 8, 28),
            lotto_provvisorio="260829", numero_batch_previsti=20,
        )

    def test_produzione_supporta_numero_elevato_di_batch(self):
        self.assertEqual(self.produzione.numero_batch_previsti, 20)
        self.assertEqual(self.produzione.fase, Produzione.Fase.PREPARAZIONE)

    def test_form_nuova_produzione_include_batch_ma_non_chiede_lotto_provvisorio(self):
        form = ProduzioneForm(data={
            "articolo": self.articolo.pk,
            "data_produzione": "2026-08-28",
            "numero_batch_previsti": 20,
            "lotto_provvisorio": "260829",
            "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["numero_batch_previsti"], 20)
        self.assertNotIn("lotto_provvisorio", form.fields)

    def test_batch_conserva_parametri_ed_esito(self):
        batch = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="C", note="Regolare",
        )
        self.assertEqual(batch.temperatura_conformita, 82)
        self.assertEqual(batch.durata_conformita_secondi, 60)

    def test_tank_collega_batch_e_calcola_conformita(self):
        tank = TankProduzione.objects.create(produzione=self.produzione, numero=1, numero_batch=1)
        BatchProduzione.objects.create(
            produzione=self.produzione, tank=tank, numero=1,
            ora_inizio=time(8), ora_fine=time(8, 20), esito_conformita="C",
        )
        registra_controlli_tank(tank, Decimal("42"), Decimal("4.0"))
        tank.refresh_from_db()
        self.assertTrue(tank.conforme)
        self.assertIsNotNone(tank.chiuso_il)

    def test_tank_fuori_parametro_rimane_registrato_non_conforme(self):
        tank = TankProduzione.objects.create(produzione=self.produzione, numero=1, numero_batch=1)
        registra_controlli_tank(tank, Decimal("46"), Decimal("4.2"))
        tank.refresh_from_db()
        self.assertFalse(tank.conforme)

    def test_limiti_brix_e_ph_includono_gli_estremi(self):
        tank = TankProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_batch=1,
        )
        registra_controlli_tank(tank, Decimal("40"), Decimal("4.1"))
        tank.refresh_from_db()
        self.assertTrue(tank.conforme)

    def test_carrello_conserva_parametri_seconda_pastorizzazione(self):
        carrello = CarrelloProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_pezzi=500,
            esito_pastorizzazione="C",
        )
        self.assertEqual(carrello.temperatura_pastorizzazione, 71)
        self.assertEqual(carrello.durata_pastorizzazione_minuti, 4)

    def test_form_batch_blocca_orario_invertito(self):
        form = BatchProduzioneForm(data={
            "ora_inizio": "10:00", "ora_fine": "09:00",
            "esito_conformita": "C", "note": "",
        })
        self.assertFalse(form.is_valid())

    def test_form_carrello_accetta_esiti_nc_e_na(self):
        tank = TankProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_batch=1,
        )
        registra_controlli_tank(tank, Decimal("42"), Decimal("4.0"))
        form = CarrelloProduzioneForm(data={
            "numero_pezzi": 500, "esito_pastorizzazione": "NC",
            "note_pastorizzazione": "Verifica qualità",
        }, produzione=self.produzione)
        self.assertTrue(form.is_valid())

    def test_conferma_calcola_peso_ottenuto_da_vasetti_buoni(self):
        form = ConfermaProduzioneForm(data={
            "lotto_definitivo": "260829",
            "quantita_prodotta": 500,
            "peso_netto_vasetto_g": "250",
            "pezzi_difettosi_finali": 0,
            "capsule_difettose_finali": 0,
            "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["quantita_ottenuta_kg"], Decimal("125"))

    def test_conferma_include_anche_i_vasetti_da_scartare_nel_peso(self):
        form = ConfermaProduzioneForm(data={
            "lotto_definitivo": "260829", "quantita_prodotta": 490,
            "pezzi_difettosi_finali": 10, "capsule_difettose_finali": 2,
            "peso_netto_vasetto_g": "250", "note": "",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["quantita_ottenuta_kg"], Decimal("125"))

    def test_lotto_del_giorno_usa_prefissi_progressivi_per_lo_stesso_prodotto(self):
        data_conferma = date(2026, 8, 29)
        Lotto.objects.create(
            articolo=self.articolo, codice_lotto="260829",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=1,
        )
        self.assertEqual(
            genera_codice_lotto_produzione(self.articolo, data_conferma),
            "A260829",
        )
        Lotto.objects.create(
            articolo=self.articolo, codice_lotto="A260829",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=1,
        )
        self.assertEqual(
            genera_codice_lotto_produzione(self.articolo, data_conferma),
            "B260829",
        )

    def test_carrello_non_e_collegato_al_tank(self):
        tank = TankProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_batch=1,
        )
        registra_controlli_tank(tank, Decimal("42"), Decimal("4.0"))
        carrello = CarrelloProduzione.objects.create(
            produzione=self.produzione, numero=1,
            numero_pezzi=500, esito_pastorizzazione="C",
        )
        self.assertFalse(hasattr(carrello, "tank"))
        self.assertNotIn("tank", CarrelloProduzioneForm().fields)

    def test_produzione_bozza_con_batch_e_carrello_puo_essere_eliminata(self):
        tank = TankProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_batch=1,
        )
        BatchProduzione.objects.create(
            produzione=self.produzione, tank=tank, numero=1,
            ora_inizio=time(8), ora_fine=time(8, 20), esito_conformita="C",
        )
        CarrelloProduzione.objects.create(
            produzione=self.produzione, numero=1,
            numero_pezzi=500, esito_pastorizzazione="C",
        )

        self.produzione.delete()

        self.assertFalse(Produzione.objects.filter(pk=self.produzione.pk).exists())
        self.assertFalse(BatchProduzione.objects.exists())
        self.assertFalse(CarrelloProduzione.objects.exists())
