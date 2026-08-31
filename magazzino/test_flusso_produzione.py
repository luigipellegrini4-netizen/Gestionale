from datetime import date, time
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from .forms import (
    BatchProduzioneForm, CarrelloProduzioneForm,
    ConfermaProduzioneForm, ControlloTankForm, ProduzioneForm,
)
from .models import Articolo, BatchProduzione, CarrelloProduzione, Giacenza, Lotto, MaterialeSospesoNonConformita, Movimento, NonConformitaLotto, PrelievoProduzione, Produzione, Ricetta, RigaRicetta, TankProduzione, Ubicazione
from .services import apri_non_conformita_batch, calcola_quantita_teorica_ricetta, genera_codice_lotto_per_produzione, genera_codice_lotto_produzione, genera_codice_lotto_ripresa, proponi_prelievi_articolo, registra_controlli_tank, riepilogo_materiali_ricetta, risolvi_non_conformita_batch, risolvi_nc_produzione_derivata


class FlussoProduzioneTreFasiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.articolo = Articolo.objects.create(
            codice="PF-FLUSSO", descrizione="Prodotto test flusso",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.ingrediente = Articolo.objects.create(
            codice="MP-FLUSSO", descrizione="Ingrediente test flusso",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        ricetta = Ricetta.objects.create(
            articolo=cls.articolo, nome="Ricetta flusso", versione="1", attiva=True,
        )
        RigaRicetta.objects.create(
            ricetta=ricetta, articolo=cls.ingrediente,
            quantita=Decimal("10"), ingrediente_prodotto=True,
        )

    def setUp(self):
        self.operatore = get_user_model().objects.create_user(
            username=f"operatore-{self._testMethodName}", password="test",
        )
        self.produzione = Produzione.objects.create(
            articolo=self.articolo, data_produzione=date(2026, 8, 28),
            lotto_provvisorio="260829", numero_batch_previsti=20,
        )

    def _crea_nc_derivata_con_materiale(self):
        ubicazione_origine = Ubicazione.objects.create(
            nome=f"MP origine {self._testMethodName}",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        Ubicazione.objects.create(
            nome=f"Produzione {self._testMethodName}",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        lotto = Lotto.objects.create(
            articolo=self.ingrediente,
            codice_lotto=f"LOT-{self._testMethodName}"[:50],
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("50"),
        )
        produzione = Produzione.objects.create(
            articolo=self.articolo,
            data_produzione=date(2026, 8, 29),
            lotto_provvisorio=f"TMP-{self._testMethodName}"[:50],
            numero_batch_previsti=5,
        )
        PrelievoProduzione.objects.create(
            produzione=produzione,
            lotto=lotto,
            ubicazione_origine=ubicazione_origine,
            quantita_prelevata=Decimal("50"),
            quantita_movimentata=Decimal("50"),
            quantita_scarto=Decimal("0"),
        )
        for numero in (1, 2):
            BatchProduzione.objects.create(
                produzione=produzione, numero=numero, esito_conformita="C",
            )
        batch = BatchProduzione.objects.create(
            produzione=produzione, numero=3, esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(batch, False, "Blocco", self.operatore)
        return nc, nc.produzioni_bloccate.get(), nc.materiali_sospesi.get(), batch

    def test_produzione_supporta_numero_elevato_di_batch(self):
        self.assertEqual(self.produzione.numero_batch_previsti, 20)
        self.assertEqual(self.produzione.fase, Produzione.Fase.PREPARAZIONE)
        self.assertEqual(
            calcola_quantita_teorica_ricetta(self.produzione), Decimal("200.000"),
        )

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

    def test_ph_tra_4_1_e_4_4_genera_allerta_senza_nc(self):
        for numero, ph in enumerate((Decimal("4.11"), Decimal("4.40")), start=1):
            tank = TankProduzione.objects.create(
                produzione=self.produzione, numero=numero, numero_batch=1,
            )
            registra_controlli_tank(tank, Decimal("42"), ph)
            tank.refresh_from_db()
            self.assertTrue(tank.ph_in_allerta)
            self.assertFalse(tank.non_conforme)
            self.assertFalse(tank.conforme)
            self.assertEqual(tank.esito_controlli, "ALLERTA")

    def test_ph_superiore_a_4_4_e_non_conforme(self):
        tank = TankProduzione.objects.create(
            produzione=self.produzione, numero=1, numero_batch=1,
        )
        registra_controlli_tank(tank, Decimal("42"), Decimal("4.41"))
        tank.refresh_from_db()
        self.assertTrue(tank.ph_non_conforme)
        self.assertTrue(tank.non_conforme)
        self.assertEqual(tank.esito_controlli, "NC")

    def test_form_controlli_accetta_valori_di_allerta_e_nc(self):
        casi = (
            ("42", "4.20"),
            ("42", "4.41"),
            ("39.99", "4.00"),
            ("45.01", "4.00"),
        )
        for brix, ph in casi:
            with self.subTest(brix=brix, ph=ph):
                form = ControlloTankForm(data={"gradi_brix": brix, "ph": ph})
                self.assertTrue(form.is_valid(), form.errors)

    def test_form_controlli_rifiuta_solo_valori_fisicamente_non_validi(self):
        for brix, ph in (("-0.01", "4.00"), ("42", "-0.01"), ("42", "14.01")):
            with self.subTest(brix=brix, ph=ph):
                form = ControlloTankForm(data={"gradi_brix": brix, "ph": ph})
                self.assertFalse(form.is_valid())

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

    def test_form_batch_nc_richiede_decisione_sul_proseguimento(self):
        form = BatchProduzioneForm(data={
            "ora_inizio": "10:00", "ora_fine": "10:20",
            "esito_conformita": "NC", "note": "Fuori parametro",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("produzione_puo_proseguire", form.errors)

    def test_form_batch_nc_accetta_orari_non_compilati(self):
        form = BatchProduzioneForm(data={
            "ora_inizio": "", "ora_fine": "",
            "esito_conformita": "NC",
            "produzione_puo_proseguire": "SI",
            "note": "NC rilevata prima dell'avvio",
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_batch_conforme_richiede_entrambi_gli_orari(self):
        form = BatchProduzioneForm(data={
            "ora_inizio": "", "ora_fine": "",
            "esito_conformita": "C", "note": "",
        })
        self.assertFalse(form.is_valid())
        self.assertIn("Ora di inizio", str(form.non_field_errors()))

    def test_batch_nc_viene_messo_in_quarantena_ed_escluso_dai_tank(self):
        batch = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(batch, True, "Tracciato NC", self.operatore)
        batch.refresh_from_db()
        self.produzione.refresh_from_db()
        self.assertEqual(batch.stato, BatchProduzione.Stato.QUARANTENA)
        self.assertIsNone(batch.tank_id)
        self.assertEqual(nc.lotto_temporaneo, "260829")
        self.assertEqual(self.produzione.stato_roboqubo, Produzione.StatoRoboqubo.CON_NC)
        self.assertFalse(self.produzione.invasettamento_congelato)
        nuova = nc.produzioni_bloccate.get()
        self.assertEqual(nuova.numero_batch_previsti, 1)
        self.assertEqual(nuova.quantita_teorica_kg, Decimal("10.000"))
        self.assertTrue(nuova.lotto_provvisorio.startswith("1TEMP"))
        self.assertEqual(batch.produzione_id, nuova.pk)
        self.assertEqual(self.produzione.numero_batch_previsti, 19)
        self.assertEqual(self.produzione.quantita_teorica_kg, Decimal("190.000"))
        self.assertEqual(
            self.produzione.quantita_teorica_kg,
            calcola_quantita_teorica_ricetta(self.produzione),
        )

    def test_rq_reintegra_batch_e_sblocca_la_produzione(self):
        batch = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(batch, True, "Tracciato NC", self.operatore)
        risolvi_nc_produzione_derivata(nc, "REINTEGRA", {}, self.operatore)
        batch.refresh_from_db()
        self.produzione.refresh_from_db()
        nc.refresh_from_db()
        self.assertEqual(batch.stato, BatchProduzione.Stato.REINTEGRATO)
        self.assertEqual(batch.esito_conformita, "NC")
        self.assertEqual(nc.stato, NonConformitaLotto.Stato.CHIUSA)
        self.assertFalse(self.produzione.invasettamento_congelato)

    def test_rq_scarta_batch_senza_mantenere_gli_orari(self):
        batch = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(batch, True, "Tracciato NC", self.operatore)
        risolvi_nc_produzione_derivata(nc, "SCARTA", {}, self.operatore)
        batch.refresh_from_db()
        self.assertEqual(batch.stato, BatchProduzione.Stato.SCARTATO)
        self.assertIsNone(batch.ora_inizio)
        self.assertIsNone(batch.ora_fine)

    def test_nc_che_blocca_crea_una_nuova_produzione_con_i_batch_residui(self):
        Ubicazione.objects.create(
            nome="Magazzino produzione test",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="C",
        )
        batch_nc = BatchProduzione.objects.create(
            produzione=self.produzione, numero=2, ora_inizio=time(8, 30),
            ora_fine=time(8, 50), esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(
            batch_nc, False, "Blocco produzione", self.operatore,
        )
        nuova = nc.produzioni_bloccate.get()
        self.produzione.refresh_from_db()
        batch_nc.refresh_from_db()
        self.assertEqual(self.produzione.fase, Produzione.Fase.ROBOQUBO)
        self.assertEqual(
            self.produzione.stato_roboqubo,
            Produzione.StatoRoboqubo.CON_NC,
        )
        self.assertEqual(self.produzione.numero_batch_previsti, 1)
        self.assertEqual(nuova.numero_batch_previsti, 19)
        self.assertEqual(nuova.quantita_teorica_kg, Decimal("190.000"))
        self.assertEqual(self.produzione.quantita_teorica_kg, Decimal("10.000"))
        self.assertTrue(nuova.lotto_provvisorio.startswith("1TEMP"))
        self.assertEqual(nuova.bloccata_da_nc, nc)
        self.assertEqual(batch_nc.produzione, nuova)
        self.assertEqual(batch_nc.numero, 1)
        self.assertEqual(nuova.batch.count(), 19)
        self.assertEqual(nuova.batch.count(), nuova.numero_batch_previsti)
        self.assertEqual(
            riepilogo_materiali_ricetta(self.produzione)[0]["quantita_totale"],
            Decimal("10.000000"),
        )
        self.assertEqual(
            riepilogo_materiali_ricetta(nuova)[0]["quantita_totale"],
            Decimal("190.000000"),
        )
        self.assertEqual(
            nuova.quantita_teorica_kg,
            calcola_quantita_teorica_ricetta(nuova),
        )
        self.assertEqual(
            nuova.batch.filter(stato=BatchProduzione.Stato.SOSPESO).count(), 18,
        )

    def test_rq_reintegra_batch_e_sblocca_i_batch_pianificati(self):
        Ubicazione.objects.create(
            nome="Magazzino produzione sblocco",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        batch_nc = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, ora_inizio=time(8),
            ora_fine=time(8, 20), esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(
            batch_nc, False, "Blocco produzione", self.operatore,
        )
        nuova = nc.produzioni_bloccate.get()
        risolvi_nc_produzione_derivata(nc, "REINTEGRA", {}, self.operatore)
        nuova.refresh_from_db()
        batch_nc.refresh_from_db()
        self.assertEqual(nuova.bloccata_da_nc_id, nc.pk)
        self.assertEqual(nuova.fase, Produzione.Fase.ROBOQUBO)
        self.assertEqual(batch_nc.stato, BatchProduzione.Stato.REINTEGRATO)
        self.assertEqual(batch_nc.esito_conformita, "NC")
        self.assertEqual(
            nuova.batch.filter(stato=BatchProduzione.Stato.DA_LAVORARE).count(), 19,
        )

    def test_scarto_batch_nc_riduce_anche_il_riepilogo_materiali(self):
        Ubicazione.objects.create(
            nome="Magazzino produzione scarto riepilogo",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        batch_nc = BatchProduzione.objects.create(
            produzione=self.produzione, numero=1, esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(
            batch_nc, False, "Blocco produzione", self.operatore,
        )
        nuova = nc.produzioni_bloccate.get()

        risolvi_nc_produzione_derivata(nc, "SCARTA", {}, self.operatore)

        nuova.refresh_from_db()
        self.assertEqual(nuova.numero_batch_previsti, 19)
        self.assertEqual(
            riepilogo_materiali_ricetta(nuova)[0]["quantita_totale"],
            Decimal("190.000000"),
        )

    def test_materiali_nc_entrano_e_rientrano_dal_magazzino_produzione(self):
        ubicazione_origine = Ubicazione.objects.create(
            nome="Magazzino MP origine NC",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        ubicazione_produzione = Ubicazione.objects.create(
            nome="Magazzino produzione movimenti NC",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        lotto = Lotto.objects.create(
            articolo=self.ingrediente, codice_lotto="MP-NC-MOV",
            tipo=Lotto.Tipo.ACQUISTO, quantita_iniziale=Decimal("50"),
        )
        produzione = Produzione.objects.create(
            articolo=self.articolo, data_produzione=date(2026, 8, 29),
            lotto_provvisorio="TEMP260829", numero_batch_previsti=5,
        )
        PrelievoProduzione.objects.create(
            produzione=produzione, lotto=lotto,
            ubicazione_origine=ubicazione_origine,
            quantita_prelevata=Decimal("50"), quantita_movimentata=Decimal("50"),
            quantita_scarto=Decimal("0"),
        )
        BatchProduzione.objects.create(
            produzione=produzione, numero=1, esito_conformita="C",
        )
        BatchProduzione.objects.create(
            produzione=produzione, numero=2, esito_conformita="C",
        )
        batch_nc = BatchProduzione.objects.create(
            produzione=produzione, numero=3, esito_conformita="NC",
        )

        nc = apri_non_conformita_batch(batch_nc, False, "Blocco", self.operatore)
        derivata = nc.produzioni_bloccate.get()
        materiale = nc.materiali_sospesi.get()
        self.assertEqual(materiale.lotto_originale, lotto)
        self.assertEqual(materiale.non_conformita, nc)
        self.assertIsNotNone(materiale.lotto_recuperato)
        self.assertEqual(materiale.quantita, Decimal("20.000000"))
        self.assertEqual(
            Giacenza.objects.get(
                lotto=materiale.lotto_recuperato,
                ubicazione=ubicazione_produzione,
            ).quantita,
            Decimal("20.000000"),
        )
        self.assertTrue(Movimento.objects.filter(
            lotto=materiale.lotto_recuperato,
            tipo=Movimento.Tipo.QUARANTENA,
            quantita=Decimal("20.000000"),
            ubicazione_destinazione=ubicazione_produzione,
        ).exists())

        proposta = proponi_prelievi_articolo(self.ingrediente, Decimal("1"))
        self.assertFalse(proposta["completa"])

        risolvi_nc_produzione_derivata(
            nc, "REINTEGRA",
            {materiale.pk: {"esito": MaterialeSospesoNonConformita.Esito.RIUTILIZZA, "note": ""}},
            self.operatore,
        )
        self.assertEqual(
            Giacenza.objects.get(lotto=materiale.lotto_recuperato).quantita,
            Decimal("0"),
        )
        self.assertEqual(
            derivata.prelievi.filter(lotto=materiale.lotto_recuperato).aggregate(
                totale=Sum("quantita_prelevata"),
            )["totale"],
            Decimal("20.000000"),
        )
        self.assertTrue(Movimento.objects.filter(
            lotto=materiale.lotto_recuperato,
            tipo=Movimento.Tipo.REINTEGRO,
            quantita=Decimal("20.000000"),
            ubicazione_origine=ubicazione_produzione,
        ).exists())

    def test_matrice_batch_scartato_materiali_reintegrati_prosegue_senza_batch(self):
        nc, derivata, materiale, batch = self._crea_nc_derivata_con_materiale()
        risolvi_nc_produzione_derivata(
            nc, "SCARTA",
            {materiale.pk: {"esito": MaterialeSospesoNonConformita.Esito.RIUTILIZZA}},
            self.operatore,
        )

        derivata.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(derivata.stato, Produzione.Stato.BOZZA)
        self.assertEqual(derivata.numero_batch_previsti, 2)
        self.assertEqual(batch.stato, BatchProduzione.Stato.SCARTATO)
        self.assertEqual(
            derivata.batch.filter(stato=BatchProduzione.Stato.DA_LAVORARE).count(), 2,
        )

    def test_matrice_batch_reintegrato_materiale_scartato_annulla_batch_futuri(self):
        nc, derivata, materiale, batch = self._crea_nc_derivata_con_materiale()
        risolvi_nc_produzione_derivata(
            nc, "REINTEGRA",
            {materiale.pk: {"esito": MaterialeSospesoNonConformita.Esito.SCARTA}},
            self.operatore,
        )

        derivata.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(derivata.stato, Produzione.Stato.BOZZA)
        self.assertEqual(derivata.numero_batch_previsti, 1)
        self.assertEqual(derivata.quantita_batch_reintegrato_kg, Decimal("10"))
        self.assertEqual(batch.stato, BatchProduzione.Stato.REINTEGRATO)
        self.assertEqual(batch.esito_conformita, "NC")
        self.assertEqual(
            derivata.batch.filter(stato=BatchProduzione.Stato.ANNULLATO).count(), 2,
        )

    def test_matrice_batch_e_materiale_scartati_abortisce_produzione(self):
        nc, derivata, materiale, batch = self._crea_nc_derivata_con_materiale()
        risolvi_nc_produzione_derivata(
            nc, "SCARTA",
            {materiale.pk: {"esito": MaterialeSospesoNonConformita.Esito.SCARTA}},
            self.operatore,
        )

        derivata.refresh_from_db()
        batch.refresh_from_db()
        self.assertEqual(derivata.stato, Produzione.Stato.ABORTITA)
        self.assertEqual(derivata.fase, Produzione.Fase.COMPLETATA)
        self.assertEqual(batch.stato, BatchProduzione.Stato.SCARTATO)

    def test_roboqubo_si_chiude_con_un_batch_reintegrato_e_uno_annullato(self):
        ubicazione_origine = Ubicazione.objects.create(
            nome="MP origine chiusura 2 batch",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        Ubicazione.objects.create(
            nome="Produzione chiusura 2 batch",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODUZIONE,
        )
        lotto = Lotto.objects.create(
            articolo=self.ingrediente, codice_lotto="LOT-CHIUSURA-2-BATCH",
            tipo=Lotto.Tipo.ACQUISTO, quantita_iniziale=Decimal("20"),
        )
        produzione = Produzione.objects.create(
            articolo=self.articolo, data_produzione=date(2026, 8, 30),
            lotto_provvisorio="TEMP-CHIUSURA-2", numero_batch_previsti=2,
        )
        PrelievoProduzione.objects.create(
            produzione=produzione, lotto=lotto,
            ubicazione_origine=ubicazione_origine,
            quantita_prelevata=Decimal("20"), quantita_movimentata=Decimal("20"),
            quantita_scarto=Decimal("0"),
        )
        batch_nc = BatchProduzione.objects.create(
            produzione=produzione, numero=1, esito_conformita="NC",
        )
        nc = apri_non_conformita_batch(batch_nc, False, "Blocco", self.operatore)
        derivata = nc.produzioni_bloccate.get()
        materiale = nc.materiali_sospesi.get()
        risolvi_nc_produzione_derivata(
            nc, "REINTEGRA",
            {materiale.pk: {"esito": MaterialeSospesoNonConformita.Esito.SCARTA}},
            self.operatore,
        )
        batch_nc.refresh_from_db()
        tank = TankProduzione.objects.create(
            produzione=derivata, numero=1, numero_batch=1,
            gradi_brix=Decimal("42"), ph=Decimal("4.0"),
            data_ora_controlli=timezone.now(),
        )
        batch_nc.tank = tank
        batch_nc.save(update_fields=["tank"])
        self.operatore.user_permissions.add(
            Permission.objects.get(codename="operare_roboqubo"),
        )
        self.client.force_login(self.operatore)

        response = self.client.post(
            reverse("gestione_produzione", kwargs={"pk": derivata.pk}),
            {"azione": "chiudi_roboqubo"},
        )

        self.assertEqual(response.status_code, 302)
        derivata.refresh_from_db()
        self.assertEqual(derivata.fase, Produzione.Fase.INVASETTAMENTO)
        self.assertEqual(derivata.stato_roboqubo, Produzione.StatoRoboqubo.CONCLUSA)

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

    def test_lotto_della_ripresa_usa_progressivo_numerico(self):
        data_conferma = date(2026, 8, 29)
        Lotto.objects.create(
            articolo=self.articolo, codice_lotto="260829",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=1,
        )
        self.assertEqual(
            genera_codice_lotto_ripresa(self.articolo, data_conferma),
            "1260829",
        )

    def test_lotto_derivato_rimuove_temp_e_mantiene_il_progressivo(self):
        self.produzione.lotto_provvisorio = "1TEMP260829"
        self.produzione.save(update_fields=["lotto_provvisorio"])
        self.assertEqual(
            genera_codice_lotto_per_produzione(self.produzione, date(2026, 9, 2)),
            "1260829",
        )
        Lotto.objects.create(
            articolo=self.articolo, codice_lotto="1260829",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=1,
        )
        self.assertEqual(
            genera_codice_lotto_per_produzione(self.produzione, date(2026, 9, 2)),
            "2260829",
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
