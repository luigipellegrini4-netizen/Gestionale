from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from magazzino.models import (
    Articolo, Giacenza, Lotto, Movimento, Ricetta, RigaRicetta, Ubicazione,
)

from .models import (
    AbilitazioneOperatore, AllocazioneOrigineUnita, CicloProduzione,
    ConsuntivoEtichettatura, ConsumoMateriale,
    DefinizioneControllo, DipendenzaPassaggio, EventoProduzione, FabbisognoMateriale,
    FaseProduzione, LineaProduzione, LottoCommerciale,
    NonConformita, OrdineProduzione, OutputProduzione, PassaggioLinea, RilevazioneControllo,
    RegolaControlloCiclo, RisorsaProduzione, StazioneLavoro, TipoUnitaProduzione,
    TurnoLinea, UnitaProduzione,
)
from .services import (
    aggiungi_dipendenza, aggiungi_origine_unita, apri_lotto_lavorazione,
    apri_non_conformita, assegna_esito_unita,
    assegna_operatore, avvia_fase,
    avvia_ordine, avvia_unita, chiudi_non_conformita, crea_unita,
    chiudi_lotto_commerciale, chiudi_lotto_lavorazione, completa_fase, completa_ordine,
    consuma_materiale, consuma_materiali_prenotati, prepara_ordine,
    prenota_materiale, registra_controllo,
    impegna_risorsa, registra_consuntivo_etichettatura, registra_output,
    reintegra_materiale, rilascia_risorsa,
    annulla_ordine, riprendi_fase, riprendi_ordine, salta_fase, sospendi_ordine,
)
from .material_planning import PianificatoreMaterialiFEFO
from .readiness import ValutatoreProntezzaOrdine
from .presets import PresetRoboQboInvasettamento


class MotoreProduzioneV2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operatore = get_user_model().objects.create_user(username="operatore-v2")
        cls.operatore.user_permissions.add(*Permission.objects.filter(
            codename__in=(
                "configurare_produzione_v2",
                "pianificare_produzione_v2",
                "operare_produzione_v2",
                "gestire_qualita_v2",
            ),
        ))
        cls.prodotto = Articolo.objects.create(
            codice="PF-V2", descrizione="Prodotto V2",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.linea = LineaProduzione.objects.create(codice="L1", nome="Linea uno")
        cls.roboqbo = StazioneLavoro.objects.create(
            codice="RQ", nome="RoboQbo", tipo=StazioneLavoro.Tipo.TRASFORMAZIONE,
        )
        cls.invasettamento = StazioneLavoro.objects.create(
            codice="INV", nome="Invasettamento",
            tipo=StazioneLavoro.Tipo.CONFEZIONAMENTO,
        )
        PassaggioLinea.objects.create(
            linea=cls.linea, stazione=cls.roboqbo, ordine=1,
        )
        PassaggioLinea.objects.create(
            linea=cls.linea, stazione=cls.invasettamento, ordine=2,
        )
        cls.ph = DefinizioneControllo.objects.create(
            stazione=cls.roboqbo, codice="PH", nome="pH",
            tipo_dato=DefinizioneControllo.TipoDato.DECIMALE,
            regole={
                "minimo_fisico": "0", "massimo_fisico": "14",
                "conforme_max": "4.1", "allerta_min_escluso": "4.1",
                "allerta_max": "4.4",
            },
        )
        cls.tipo_batch = TipoUnitaProduzione.objects.create(
            stazione=cls.roboqbo, codice="BATCH", nome="Batch", unita_misura="KG",
        )
        cls.tipo_carrello = TipoUnitaProduzione.objects.create(
            stazione=cls.invasettamento, codice="CARRELLO", nome="Carrello",
            unita_misura="PZ",
        )
        cls.materiale = Articolo.objects.create(
            codice="MP-V2", descrizione="Materia prima V2",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Magazzino V2", tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.materiale, codice_lotto="LOT-V2", tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("20"),
        )
        cls.giacenza = Giacenza.objects.create(
            lotto=cls.lotto, ubicazione=cls.ubicazione, quantita=Decimal("20"),
            scaffale="A", piano="1",
        )

    def crea_ordine(self, codice="OP-1", ciclo=None):
        return OrdineProduzione.objects.create(
            codice=codice, linea=self.linea, prodotto=self.prodotto,
            quantita_pianificata=Decimal("100"), pianificato_per=date(2026, 9, 1),
            creato_da=self.operatore, ciclo=ciclo,
        )

    def crea_ciclo(self):
        ricetta = Ricetta.objects.create(
            articolo=self.prodotto, nome="Ricetta V2", versione="V2", attiva=True,
        )
        riga = RigaRicetta.objects.create(
            ricetta=ricetta, articolo=self.materiale, quantita=Decimal("2"),
        )
        ciclo = CicloProduzione.objects.create(
            prodotto=self.prodotto, linea=self.linea, ricetta=ricetta,
            versione="V2", quantita_riferimento=Decimal("10"),
        )
        return ciclo, riga

    def crea_scenario_matrice_nc(self, codice):
        ordine = prepara_ordine(self.crea_ordine(codice), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        batch = UnitaProduzione.objects.create(
            ordine=ordine, fase=fase, tipo="BATCH", codice=f"{codice}-B1",
            stato=UnitaProduzione.Stato.IN_LAVORAZIONE,
        )
        futuro = UnitaProduzione.objects.create(
            ordine=ordine, fase=fase, tipo="BATCH", codice=f"{codice}-B2",
            stato=UnitaProduzione.Stato.CREATA,
        )
        consumo = prenota_materiale(fase, self.giacenza, "3", self.operatore)
        consumo = consuma_materiale(consumo, self.operatore)
        nc_batch = apri_non_conformita(
            ordine, "Verifica batch", self.operatore, fase=fase, unita=batch,
        )
        nc_materiale = apri_non_conformita(
            ordine, "Verifica ingrediente", self.operatore, fase=fase, consumo=consumo,
        )
        return ordine, fase, batch, futuro, consumo, nc_batch, nc_materiale

    def setUp(self):
        self.client.force_login(self.operatore)

    def test_preparazione_genera_le_fasi_dalla_linea(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.PRONTO)
        self.assertEqual(
            list(ordine.fasi.values_list("sequenza", flat=True)), [1, 2],
        )
        self.assertEqual(ordine.eventi.get().tipo, "ORDINE_PREPARATO")

    def test_non_si_puo_avviare_una_fase_saltando_la_precedente(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        seconda = ordine.fasi.get(sequenza=2)
        with self.assertRaisesMessage(ValidationError, "fasi precedenti"):
            avvia_fase(seconda, self.operatore)

    def test_dipendenza_a_flusso_avvia_su_output_parziale_e_contabilizza_il_residuo(self):
        primo = self.linea.passaggi.get(ordine=1)
        secondo = self.linea.passaggi.get(ordine=2)
        aggiungi_dipendenza(
            secondo, primo, DipendenzaPassaggio.Modalita.FLUSSO,
            quantita_minima_avvio=Decimal("2"),
        )
        ordine = prepara_ordine(self.crea_ordine("OP-FLUSSO"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase_rq = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        fase_inv = ordine.fasi.get(sequenza=2)
        self.assertFalse(fase_inv.eseguibile)

        batch = crea_unita(
            fase_rq, self.tipo_batch, "BATCH-FLUSSO", "5", self.operatore,
        )
        avvia_unita(batch, self.operatore)
        assegna_esito_unita(batch, UnitaProduzione.Stato.CONFORME, self.operatore)
        self.assertTrue(fase_inv.eseguibile)
        fase_inv = avvia_fase(fase_inv, self.operatore)

        crea_unita(
            fase_inv, self.tipo_carrello, "INV-FLUSSO-1", "3", self.operatore,
            origine=batch, quantita_origine="3",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.quantita_trasferita, Decimal("3"))
        self.assertEqual(batch.quantita_disponibile, Decimal("2"))
        with self.assertRaisesMessage(ValidationError, "supera il prodotto disponibile"):
            crea_unita(
                fase_inv, self.tipo_carrello, "INV-FLUSSO-2", "3", self.operatore,
                origine=batch, quantita_origine="3",
            )

    def test_unita_destinazione_puo_prelevare_da_piu_batch(self):
        primo = self.linea.passaggi.get(ordine=1)
        secondo = self.linea.passaggi.get(ordine=2)
        aggiungi_dipendenza(secondo, primo, DipendenzaPassaggio.Modalita.FLUSSO)
        ordine = prepara_ordine(self.crea_ordine("OP-MULTI-ORIGINE"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase_rq = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        batch = []
        for indice in (1, 2):
            unita = crea_unita(
                fase_rq, self.tipo_batch, f"BATCH-M{indice}", "5", self.operatore,
            )
            avvia_unita(unita, self.operatore)
            assegna_esito_unita(unita, UnitaProduzione.Stato.CONFORME, self.operatore)
            batch.append(unita)
        fase_inv = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        tank = crea_unita(
            fase_inv, self.tipo_carrello, "TANK-MULTI", "7", self.operatore,
            origine=batch[0], quantita_origine="3",
        )
        aggiungi_origine_unita(tank, batch[1], "4", self.operatore)
        self.assertEqual(tank.allocazioni_origine.count(), 2)
        self.assertEqual(
            set(tank.allocazioni_origine.values_list("quantita", flat=True)),
            {Decimal("3"), Decimal("4")},
        )
        batch[0].refresh_from_db()
        batch[1].refresh_from_db()
        self.assertEqual(batch[0].quantita_disponibile, Decimal("2"))
        self.assertEqual(batch[1].quantita_disponibile, Decimal("1"))
        altro_tank = crea_unita(
            fase_inv, self.tipo_carrello, "TANK-MULTI-2", "2", self.operatore,
        )
        with self.assertRaisesMessage(ValidationError, "supera il prodotto disponibile"):
            aggiungi_origine_unita(altro_tank, batch[1], "2", self.operatore)

    def test_lotto_temporaneo_puo_dividersi_in_due_lotti_commerciali(self):
        ordine = prepara_ordine(self.crea_ordine("OP-LOTTI"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        temporaneo = apri_lotto_lavorazione(ordine, "TEMP-B-01", self.operatore)
        chiudi_lotto_lavorazione(temporaneo, self.operatore)
        primo = chiudi_lotto_commerciale(
            ordine, [temporaneo], 100, 2, 3, self.operatore,
        )
        secondo = chiudi_lotto_commerciale(
            ordine, [temporaneo], 80, 1, 4, self.operatore,
        )
        self.assertEqual(primo.codice, timezone.localdate().strftime("%y%m%d"))
        self.assertEqual(secondo.codice, "A" + timezone.localdate().strftime("%y%m%d"))
        self.assertEqual(temporaneo.destinazioni_commerciali.count(), 2)
        self.assertEqual(primo.vasetti_consumati, 102)
        self.assertEqual(primo.capsule_consumate, 105)

    def test_riversamento_batch_tank_nella_stessa_fase(self):
        tipo_tank = TipoUnitaProduzione.objects.create(
            stazione=self.roboqbo, codice="TANK", nome="Tank",
            unita_misura="KG", richiede_quantita=False,
        )
        ordine = prepara_ordine(self.crea_ordine("OP-BATCH-TANK"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        batch = crea_unita(fase, self.tipo_batch, "BATCH-T1", "8", self.operatore)
        avvia_unita(batch, self.operatore)
        assegna_esito_unita(batch, UnitaProduzione.Stato.CONFORME, self.operatore)
        tank = crea_unita(fase, tipo_tank, "TANK-1", None, self.operatore)
        aggiungi_origine_unita(tank, batch, "5", self.operatore)
        tank.refresh_from_db()
        self.assertEqual(tank.quantita, Decimal("5"))
        self.assertEqual(batch.quantita_disponibile, Decimal("3"))

    def test_consuntivo_etichettatura_e_formula_consumo(self):
        ordine = prepara_ordine(self.crea_ordine("OP-ETICHETTE"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        temporaneo = apri_lotto_lavorazione(ordine, "TEMP-ETI", self.operatore)
        chiudi_lotto_lavorazione(temporaneo, self.operatore)
        lotto = chiudi_lotto_commerciale(
            ordine, [temporaneo], 100, 2, 3, self.operatore, codice="LOTTO-ETI",
        )
        consuntivo = registra_consuntivo_etichettatura(
            lotto, 97, 3, 4, self.operatore,
        )
        self.assertEqual(consuntivo.etichette_consumate, 104)
        self.assertTrue(ConsuntivoEtichettatura.objects.filter(pk=consuntivo.pk).exists())
        with self.assertRaisesMessage(ValidationError, "superano quelli ricevuti"):
            registra_consuntivo_etichettatura(lotto, 101, 0, 0, self.operatore)

    def test_controllo_ph_configurabile(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        casi = (
            ("4.10", RilevazioneControllo.Esito.CONFORME),
            ("4.11", RilevazioneControllo.Esito.ALLERTA),
            ("4.40", RilevazioneControllo.Esito.ALLERTA),
            ("4.41", RilevazioneControllo.Esito.NON_CONFORME),
        )
        for valore, esito in casi:
            with self.subTest(valore=valore):
                rilevazione = registra_controllo(
                    fase, self.ph, valore, self.operatore,
                )
                self.assertEqual(rilevazione.esito, esito)
        ordine.refresh_from_db()
        fase.refresh_from_db()
        nc = ordine.non_conformita.get(rilevazione__isnull=False)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.BLOCCATO_NC)
        self.assertEqual(fase.stato, FaseProduzione.Stato.BLOCCATA)
        self.assertEqual(nc.rilevazione.valore, "4.41")

        dashboard = self.client.get(reverse("produzione_v2:dashboard"))
        self.assertContains(dashboard, nc.codice)
        self.assertContains(dashboard, "Controllo pH non conforme")

    def test_fase_richiede_i_controlli_obbligatori(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        with self.assertRaisesMessage(ValidationError, "controlli obbligatori"):
            completa_fase(fase, self.operatore)

    def test_ordine_completa_solo_dopo_tutte_le_fasi(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        seconda = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        completa_fase(seconda, self.operatore)
        ordine = completa_ordine(ordine, self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.COMPLETATO)
        self.assertIsNotNone(ordine.completato_il)

    def test_dashboard_v2_e_separata_e_accessibile(self):
        response = self.client.get(reverse("produzione_v2:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Motore produttivo configurabile")

    def test_report_produzione_filtra_ed_esporta_csv(self):
        incluso = prepara_ordine(self.crea_ordine("OP-REPORT-IN"), self.operatore)
        escluso = self.crea_ordine("OP-REPORT-OUT")
        escluso.pianificato_per = date(2026, 10, 1)
        escluso.save(update_fields=("pianificato_per",))

        filtri = {"dal": "2026-09-01", "al": "2026-09-30", "linea": self.linea.pk}
        pagina = self.client.get(reverse("produzione_v2:report_produzione"), filtri)
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, incluso.codice)
        self.assertNotContains(pagina, escluso.codice)
        self.assertContains(pagina, "Indicatori")

        csv_response = self.client.get(
            reverse("produzione_v2:esporta_report_produzione"), filtri,
        )
        contenuto = csv_response.content.decode("utf-8-sig")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("OP-REPORT-IN", contenuto)
        self.assertNotIn("OP-REPORT-OUT", contenuto)
        self.assertIn("AUDIT_VALIDO", contenuto)
        self.assertIn("SI", contenuto)

    def test_catena_audit_rileva_modifiche_al_registro(self):
        ordine = prepara_ordine(self.crea_ordine("OP-AUDIT"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        valida, numero = EventoProduzione.verifica_catena(ordine)
        self.assertTrue(valida)
        self.assertEqual(numero, 2)
        pagina = self.client.get(reverse(
            "produzione_v2:dettaglio_ordine", args=(ordine.pk,),
        ))
        self.assertContains(pagina, "Integrità registro")
        self.assertContains(pagina, "Verificata")

        EventoProduzione.objects.filter(
            ordine=ordine, tipo="ORDINE_PREPARATO",
        ).update(dati={"alterato": True})
        valida, _ = EventoProduzione.verifica_catena(ordine)
        self.assertFalse(valida)

    def test_preset_roboqbo_invasettamento_e_completo_e_idempotente(self):
        url = reverse("produzione_v2:applica_preset_roboqbo_invasettamento")
        prima = self.client.post(url)
        linea = LineaProduzione.objects.get(codice="RQ-INV-V2")
        self.assertRedirects(
            prima, reverse("produzione_v2:dettaglio_linea", args=(linea.pk,)),
        )
        self.assertEqual(linea.passaggi.count(), 8)
        roboqbo = StazioneLavoro.objects.get(codice="ROBOQBO-V2")
        invasettamento = StazioneLavoro.objects.get(codice="INVASETTAMENTO-V2")
        self.assertEqual(
            set(roboqbo.controlli.values_list("codice", flat=True)),
            {"PH", "BRIX"},
        )
        self.assertEqual(
            set(invasettamento.controlli.values_list("codice", flat=True)),
            {"TEMP", "CHIUSURA"},
        )
        self.assertTrue(roboqbo.richiede_operatore_abilitato)
        self.assertTrue(roboqbo.richiede_risorsa)
        self.assertEqual(
            set(roboqbo.tipi_unita.values_list("codice", flat=True)), {"BATCH", "TANK"},
        )
        self.assertIn("CARRELLO", set(invasettamento.tipi_unita.values_list("codice", flat=True)))
        self.assertEqual(linea.passaggi.get(ordine=2).dipendenze.count(), 1)
        self.assertEqual(
            linea.passaggi.get(ordine=2).dipendenze.get().modalita,
            DipendenzaPassaggio.Modalita.FLUSSO,
        )
        self.assertTrue(LineaProduzione.objects.filter(codice="SEMILAVORATI-V2").exists())

        conteggi = (
            LineaProduzione.objects.count(), StazioneLavoro.objects.count(),
            PassaggioLinea.objects.count(), DefinizioneControllo.objects.count(),
            TipoUnitaProduzione.objects.count(), RisorsaProduzione.objects.count(),
        )
        seconda = self.client.post(url)
        self.assertEqual(seconda.status_code, 302)
        self.assertEqual(conteggi, (
            LineaProduzione.objects.count(), StazioneLavoro.objects.count(),
            PassaggioLinea.objects.count(), DefinizioneControllo.objects.count(),
            TipoUnitaProduzione.objects.count(), RisorsaProduzione.objects.count(),
        ))

    def test_interfacce_guidate_per_postazione(self):
        indice = self.client.get(reverse("produzione_v2:postazioni"))
        self.assertEqual(indice.status_code, 200)
        self.assertContains(indice, "Scegli la tua postazione")
        self.assertContains(indice, "RoboQbo")
        self.assertContains(indice, "Riempimento e trattamento")

        pagina_b = self.client.get(reverse(
            "produzione_v2:postazione_operatore", args=("b",),
        ))
        self.assertEqual(pagina_b.status_code, 200)
        self.assertContains(pagina_b, "OPERATORE B")
        self.assertNotContains(pagina_b, "Configurazione pilota")

    def test_interfaccia_guidata_roboqbo(self):
        linea, _ = PresetRoboQboInvasettamento().applica()
        ordine = OrdineProduzione.objects.create(
            codice="OP-UI-RQ", linea=linea, prodotto=self.prodotto,
            quantita_pianificata=Decimal("10"), creato_da=self.operatore,
        )
        prepara_ordine(ordine, self.operatore)
        ordine.stato = OrdineProduzione.Stato.IN_CORSO
        ordine.save(update_fields=("stato",))
        risposta = self.client.get(reverse(
            "produzione_v2:lavorazione_roboqbo", args=(ordine.pk,),
        ))
        self.assertEqual(risposta.status_code, 200)
        self.assertContains(risposta, "COSA DEVI FARE ADESSO")
        self.assertContains(risposta, "Avvia RoboQbo")
        self.assertContains(risposta, "LOTTO IN LAVORAZIONE")

    def test_flusso_operatore_via_http(self):
        ordine = self.crea_ordine()
        url = reverse("produzione_v2:dettaglio_ordine", args=(ordine.pk,))

        self.client.post(url, {"azione": "prepara"})
        ordine.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.PRONTO)

        self.client.post(url, {"azione": "avvia_ordine"})
        ordine.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)

        prima = ordine.fasi.get(sequenza=1)
        self.client.post(url, {"azione": "avvia_fase", "fase_id": prima.pk})
        self.client.post(url, {
            "azione": "registra_controlli", "fase_id": prima.pk,
            f"controllo_{self.ph.pk}": "4.20",
        })
        self.client.post(url, {"azione": "completa_fase", "fase_id": prima.pk})
        prima.refresh_from_db()
        self.assertEqual(prima.stato, FaseProduzione.Stato.COMPLETATA)
        self.assertEqual(
            prima.rilevazioni.get().esito, RilevazioneControllo.Esito.ALLERTA,
        )

        seconda = ordine.fasi.get(sequenza=2)
        self.client.post(url, {"azione": "avvia_fase", "fase_id": seconda.pk})
        self.client.post(url, {"azione": "completa_fase", "fase_id": seconda.pk})
        self.client.post(url, {"azione": "completa_ordine"})
        ordine.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.COMPLETATO)

    def test_prenotazione_non_modifica_giacenza_e_rispetta_impegni(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        prenota_materiale(fase, self.giacenza, "15", self.operatore)
        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("20"))
        with self.assertRaisesMessage(ValidationError, "prenotabile insufficiente"):
            prenota_materiale(fase, self.giacenza, "6", self.operatore)

    def test_consumo_e_reintegro_usano_i_movimenti_magazzino(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        consumo = prenota_materiale(fase, self.giacenza, "7.5", self.operatore)

        consumo = consuma_materiale(consumo, self.operatore)
        self.giacenza.refresh_from_db()
        self.assertEqual(consumo.stato, ConsumoMateriale.Stato.CONSUMATO)
        self.assertEqual(self.giacenza.quantita, Decimal("12.5"))
        self.assertEqual(consumo.collegamenti_movimento.get().movimento.tipo, Movimento.Tipo.CONSUMO)

        consumo = reintegra_materiale(consumo, self.operatore)
        self.giacenza.refresh_from_db()
        self.assertEqual(consumo.stato, ConsumoMateriale.Stato.REINTEGRATO)
        self.assertEqual(self.giacenza.quantita, Decimal("20"))
        self.assertTrue(
            consumo.collegamenti_movimento.filter(
                movimento__tipo=Movimento.Tipo.REINTEGRO,
            ).exists()
        )

    def test_nc_mette_unita_in_quarantena_e_riprende_la_fase(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        unita = UnitaProduzione.objects.create(
            ordine=ordine, fase=fase, tipo="BATCH", codice="B-1",
            stato=UnitaProduzione.Stato.IN_LAVORAZIONE,
        )

        nc = apri_non_conformita(
            ordine, "Controllo fuori limite", self.operatore,
            fase=fase, unita=unita,
        )
        ordine.refresh_from_db()
        fase.refresh_from_db()
        unita.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.BLOCCATO_NC)
        self.assertEqual(fase.stato, FaseProduzione.Stato.BLOCCATA)
        self.assertEqual(unita.stato, UnitaProduzione.Stato.QUARANTENA)

        chiudi_non_conformita(
            nc, NonConformita.Esito.REINTEGRO, "Controllo RQ positivo", self.operatore,
        )
        ordine.refresh_from_db()
        fase.refresh_from_db()
        unita.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_CORSO)
        self.assertEqual(unita.stato, UnitaProduzione.Stato.REINTEGRATA)

    def test_nc_materiale_reintegra_il_consumo_nella_stessa_posizione(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        consumo = prenota_materiale(fase, self.giacenza, "5", self.operatore)
        consumo = consuma_materiale(consumo, self.operatore)
        nc = apri_non_conformita(
            ordine, "Materiale da verificare", self.operatore,
            fase=fase, consumo=consumo,
        )

        chiudi_non_conformita(
            nc, NonConformita.Esito.REINTEGRO, "Materiale restituito", self.operatore,
        )
        consumo.refresh_from_db()
        self.giacenza.refresh_from_db()
        self.assertEqual(consumo.stato, ConsumoMateriale.Stato.REINTEGRATO)
        self.assertEqual(self.giacenza.quantita, Decimal("20"))

    def test_nc_con_annullamento_aborta_ordine(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        nc = apri_non_conformita(
            ordine, "Produzione non recuperabile", self.operatore, fase=fase,
        )
        chiudi_non_conformita(
            nc, NonConformita.Esito.ANNULLAMENTO, "Produzione abortita", self.operatore,
        )
        ordine.refresh_from_db()
        fase.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.ABORTITO)
        self.assertEqual(fase.stato, FaseProduzione.Stato.ANNULLATA)

    def test_matrice_nc_reintegro_batch_e_materiale_prosegue_con_tutti(self):
        ordine, fase, batch, futuro, consumo, nc_batch, nc_materiale = (
            self.crea_scenario_matrice_nc("OP-MAT-1")
        )
        chiudi_non_conformita(
            nc_batch, NonConformita.Esito.REINTEGRO, "Batch conforme", self.operatore,
        )
        decisiva = chiudi_non_conformita(
            nc_materiale, NonConformita.Esito.REINTEGRO,
            "Ingrediente reintegrato", self.operatore,
        )
        ordine.refresh_from_db()
        futuro.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)
        self.assertEqual(futuro.stato, UnitaProduzione.Stato.CREATA)
        self.assertEqual(
            decisiva.decisione_flusso,
            NonConformita.DecisioneFlusso.PROSEGUE_TUTTI,
        )

    def test_matrice_nc_batch_scartato_materiale_reintegrato_prosegue_senza_batch(self):
        ordine, fase, batch, futuro, consumo, nc_batch, nc_materiale = (
            self.crea_scenario_matrice_nc("OP-MAT-2")
        )
        chiudi_non_conformita(
            nc_batch, NonConformita.Esito.SCARTO, "Batch scartato", self.operatore,
        )
        decisiva = chiudi_non_conformita(
            nc_materiale, NonConformita.Esito.REINTEGRO,
            "Ingrediente reintegrato", self.operatore,
        )
        ordine.refresh_from_db()
        batch.refresh_from_db()
        futuro.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)
        self.assertEqual(batch.stato, UnitaProduzione.Stato.SCARTATA)
        self.assertEqual(futuro.stato, UnitaProduzione.Stato.CREATA)
        self.assertEqual(
            decisiva.decisione_flusso,
            NonConformita.DecisioneFlusso.SENZA_SCARTATI,
        )

    def test_matrice_nc_batch_reintegrato_materiale_scartato_annulla_futuri(self):
        ordine, fase, batch, futuro, consumo, nc_batch, nc_materiale = (
            self.crea_scenario_matrice_nc("OP-MAT-3")
        )
        chiudi_non_conformita(
            nc_batch, NonConformita.Esito.REINTEGRO, "Batch recuperato", self.operatore,
        )
        decisiva = chiudi_non_conformita(
            nc_materiale, NonConformita.Esito.SCARTO,
            "Ingrediente scartato", self.operatore,
        )
        ordine.refresh_from_db()
        batch.refresh_from_db()
        futuro.refresh_from_db()
        fase.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)
        self.assertEqual(batch.stato, UnitaProduzione.Stato.REINTEGRATA)
        self.assertEqual(futuro.stato, UnitaProduzione.Stato.ANNULLATA)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_CORSO)
        self.assertEqual(
            decisiva.decisione_flusso,
            NonConformita.DecisioneFlusso.SOLO_REINTEGRATI,
        )

    def test_matrice_nc_batch_e_materiale_scartati_abortisce(self):
        ordine, fase, batch, futuro, consumo, nc_batch, nc_materiale = (
            self.crea_scenario_matrice_nc("OP-MAT-4")
        )
        chiudi_non_conformita(
            nc_batch, NonConformita.Esito.SCARTO, "Batch scartato", self.operatore,
        )
        decisiva = chiudi_non_conformita(
            nc_materiale, NonConformita.Esito.SCARTO,
            "Ingrediente scartato", self.operatore,
        )
        ordine.refresh_from_db()
        fase.refresh_from_db()
        futuro.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.ABORTITO)
        self.assertEqual(fase.stato, FaseProduzione.Stato.ANNULLATA)
        self.assertEqual(futuro.stato, UnitaProduzione.Stato.ANNULLATA)
        self.assertEqual(
            decisiva.decisione_flusso,
            NonConformita.DecisioneFlusso.PRODUZIONE_ABORTITA,
        )

    def test_ciclo_genera_fabbisogni_proporzionati_e_congelati(self):
        ciclo, riga = self.crea_ciclo()
        ordine = prepara_ordine(self.crea_ordine(ciclo=ciclo), self.operatore)
        fabbisogno = ordine.fabbisogni.get()
        self.assertEqual(fabbisogno.articolo, self.materiale)
        self.assertEqual(fabbisogno.quantita_prevista, Decimal("20"))
        self.assertEqual(fabbisogno.origine_ricetta, riga)
        riga.quantita = Decimal("3")
        riga.save(update_fields=("quantita",))
        fabbisogno.refresh_from_db()
        self.assertEqual(fabbisogno.quantita_prevista, Decimal("20"))

    def test_prenotazione_rispetta_il_fabbisogno_del_ciclo(self):
        ciclo, _ = self.crea_ciclo()
        ordine = prepara_ordine(self.crea_ordine(ciclo=ciclo), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        prenota_materiale(fase, self.giacenza, "15", self.operatore)
        with self.assertRaisesMessage(ValidationError, "fabbisogno residuo"):
            prenota_materiale(fase, self.giacenza, "6", self.operatore)

        estraneo = Articolo.objects.create(
            codice="MP-EST", descrizione="Estraneo",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        lotto = Lotto.objects.create(
            articolo=estraneo, codice_lotto="LOT-EST", tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
        )
        giacenza = Giacenza.objects.create(
            lotto=lotto, ubicazione=self.ubicazione, quantita=Decimal("10"),
        )
        with self.assertRaisesMessage(ValidationError, "non è previsto"):
            prenota_materiale(fase, giacenza, "1", self.operatore)

    def test_prenotazione_automatica_usa_fefo_ed_esclude_scaduti(self):
        oggi = timezone.localdate()
        lotto_scaduto = Lotto.objects.create(
            articolo=self.materiale, codice_lotto="LOT-SCADUTO",
            tipo=Lotto.Tipo.ACQUISTO, quantita_iniziale=Decimal("100"),
            data_scadenza=oggi - timedelta(days=1),
        )
        lotto_prima = Lotto.objects.create(
            articolo=self.materiale, codice_lotto="LOT-PRIMA",
            tipo=Lotto.Tipo.ACQUISTO, quantita_iniziale=Decimal("6"),
            data_scadenza=oggi + timedelta(days=10),
        )
        lotto_dopo = Lotto.objects.create(
            articolo=self.materiale, codice_lotto="LOT-DOPO",
            tipo=Lotto.Tipo.ACQUISTO, quantita_iniziale=Decimal("20"),
            data_scadenza=oggi + timedelta(days=30),
        )
        for lotto, quantita in (
            (lotto_scaduto, "100"), (lotto_prima, "6"), (lotto_dopo, "20"),
        ):
            Giacenza.objects.create(
                lotto=lotto, ubicazione=self.ubicazione, quantita=Decimal(quantita),
            )
        ciclo, _ = self.crea_ciclo()
        ordine = prepara_ordine(
            self.crea_ordine("OP-FEFO", ciclo=ciclo), self.operatore,
        )
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)

        prenotazioni = PianificatoreMaterialiFEFO(fase).prenota(self.operatore)

        self.assertEqual(
            [(p.lotto.codice_lotto, p.quantita) for p in prenotazioni],
            [("LOT-PRIMA", Decimal("6")), ("LOT-DOPO", Decimal("14"))],
        )
        self.assertFalse(ordine.materiali.filter(lotto=lotto_scaduto).exists())
        consumati = consuma_materiali_prenotati(fase, self.operatore)
        self.assertEqual(len(consumati), 2)
        self.assertFalse(
            ordine.materiali.exclude(stato=ConsumoMateriale.Stato.CONSUMATO).exists(),
        )
        self.assertTrue(
            ordine.eventi.filter(tipo="CONSUMO_MATERIALI_CUMULATIVO").exists(),
        )

    def test_prenotazione_fefo_insufficiente_non_lascia_impegni_parziali(self):
        ciclo, _ = self.crea_ciclo()
        ordine = prepara_ordine(
            self.crea_ordine("OP-FEFO-MANCA", ciclo=ciclo), self.operatore,
        )
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        self.giacenza.quantita = Decimal("5")
        self.giacenza.save(update_fields=("quantita",))

        with self.assertRaisesMessage(ValidationError, "Disponibilità insufficiente"):
            PianificatoreMaterialiFEFO(fase).prenota(self.operatore)
        self.assertFalse(ordine.materiali.exists())

    def test_verifica_prontezza_segnala_materiali_risorse_e_abilitazioni(self):
        self.roboqbo.richiede_risorsa = True
        self.roboqbo.richiede_operatore_abilitato = True
        self.roboqbo.save(update_fields=(
            "richiede_risorsa", "richiede_operatore_abilitato",
        ))
        self.giacenza.quantita = Decimal("5")
        self.giacenza.save(update_fields=("quantita",))
        ciclo, _ = self.crea_ciclo()
        ordine = prepara_ordine(
            self.crea_ordine("OP-PRONTO", ciclo=ciclo), self.operatore,
        )
        problemi = ValutatoreProntezzaOrdine(ordine).valuta()
        self.assertEqual(
            {problema.codice for problema in problemi},
            {"MATERIALE", "RISORSA", "OPERATORE"},
        )
        with self.assertRaisesMessage(ValidationError, "Ordine non pronto"):
            avvia_ordine(ordine, self.operatore)
        ordine.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.PRONTO)

        RisorsaProduzione.objects.create(
            stazione=self.roboqbo, codice="RQ-READY", nome="RQ pronta",
            tipo=RisorsaProduzione.Tipo.MACCHINA,
        )
        AbilitazioneOperatore.objects.create(
            operatore=self.operatore, stazione=self.roboqbo,
        )
        self.giacenza.quantita = Decimal("20")
        self.giacenza.save(update_fields=("quantita",))
        self.assertEqual(ValutatoreProntezzaOrdine(ordine).valuta(), [])
        ordine = avvia_ordine(ordine, self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)

    def test_ciclo_vita_unita_e_blocco_chiusura_fase(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        registra_controllo(fase, self.ph, "4.0", self.operatore)
        unita = crea_unita(
            fase, self.tipo_batch, "BATCH-001", "50", self.operatore,
        )
        with self.assertRaisesMessage(ValidationError, "esito definitivo"):
            completa_fase(fase, self.operatore)
        unita = avvia_unita(unita, self.operatore)
        unita = assegna_esito_unita(
            unita, UnitaProduzione.Stato.CONFORME, self.operatore,
        )
        fase = completa_fase(fase, self.operatore)
        self.assertEqual(fase.stato, FaseProduzione.Stato.COMPLETATA)
        self.assertEqual(unita.stato, UnitaProduzione.Stato.CONFORME)

    def test_unita_derivata_conserva_genealogia(self):
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        origine = crea_unita(prima, self.tipo_batch, "BATCH-001", "50", self.operatore)
        origine = avvia_unita(origine, self.operatore)
        origine = assegna_esito_unita(
            origine, UnitaProduzione.Stato.CONFORME, self.operatore,
        )
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        seconda = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        derivata = crea_unita(
            seconda, self.tipo_carrello, "CAR-001", "100", self.operatore,
            origine=origine,
        )
        self.assertEqual(derivata.origine, origine)

    def test_creazione_ordine_da_ciclo_via_http(self):
        ciclo, _ = self.crea_ciclo()
        response = self.client.post(reverse("produzione_v2:nuovo_ordine"), {
            "codice": "OP-WEB",
            "ciclo": ciclo.pk,
            "quantita_pianificata": "25",
            "priorita": "2",
            "pianificato_per": "2026-09-02",
            "note": "Ordine da interfaccia",
        })
        ordine = OrdineProduzione.objects.get(codice="OP-WEB")
        self.assertRedirects(
            response, reverse("produzione_v2:dettaglio_ordine", args=(ordine.pk,)),
        )
        self.assertEqual(ordine.ciclo, ciclo)
        self.assertEqual(ordine.prodotto, ciclo.prodotto)
        self.assertEqual(ordine.linea, ciclo.linea)

    def test_limiti_controllo_del_ciclo_sostituiscono_quelli_generali(self):
        ciclo, _ = self.crea_ciclo()
        brix = DefinizioneControllo.objects.create(
            stazione=self.roboqbo, codice="BRIX-CICLO", nome="Gradi Brix ciclo",
            tipo_dato=DefinizioneControllo.TipoDato.DECIMALE,
            regole={"minimo_fisico": "0", "massimo_fisico": "100"},
        )
        specifica = RegolaControlloCiclo.objects.create(
            ciclo=ciclo, definizione=brix,
            regole={
                "minimo_fisico": "0", "massimo_fisico": "100",
                "conforme_min": "60", "conforme_max": "65",
                "allerta_min_escluso": "65", "allerta_max": "67",
            },
        )
        ordine = prepara_ordine(
            self.crea_ordine("OP-BRIX-SPEC", ciclo=ciclo), self.operatore,
        )
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)

        conforme = registra_controllo(fase, brix, "62", self.operatore)
        allerta = registra_controllo(fase, brix, "66", self.operatore)
        non_conforme = registra_controllo(fase, brix, "68", self.operatore)
        self.assertEqual(conforme.esito, RilevazioneControllo.Esito.CONFORME)
        self.assertEqual(allerta.esito, RilevazioneControllo.Esito.ALLERTA)
        self.assertEqual(non_conforme.esito, RilevazioneControllo.Esito.NON_CONFORME)
        self.assertEqual(conforme.regole_applicate, specifica.regole)

    def test_utente_sola_lettura_non_puo_modificare_v2(self):
        lettore = get_user_model().objects.create_user(username="lettore-v2")
        self.client.force_login(lettore)
        self.assertEqual(
            self.client.get(reverse("produzione_v2:dashboard")).status_code, 200,
        )
        self.assertEqual(
            self.client.get(reverse("produzione_v2:nuovo_ordine")).status_code, 403,
        )
        ordine = self.crea_ordine("OP-READ")
        response = self.client.post(
            reverse("produzione_v2:dettaglio_ordine", args=(ordine.pk,)),
            {"azione": "prepara"},
        )
        self.assertEqual(response.status_code, 403)
        ordine.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.PIANIFICATO)

    def test_coda_operatore_mostra_solo_fasi_eseguibili_e_abilitate(self):
        self.roboqbo.richiede_operatore_abilitato = True
        self.roboqbo.save(update_fields=("richiede_operatore_abilitato",))
        altro_operatore = get_user_model().objects.create_user(username="altro-abilitato")
        AbilitazioneOperatore.objects.create(
            operatore=altro_operatore, stazione=self.roboqbo,
        )
        ordine = prepara_ordine(self.crea_ordine("OP-CODA-OPER"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        url = reverse("produzione_v2:mie_attivita")

        senza_abilitazione = self.client.get(url)
        self.assertEqual(senza_abilitazione.status_code, 200)
        self.assertNotContains(senza_abilitazione, "OP-CODA-OPER")

        AbilitazioneOperatore.objects.create(
            operatore=self.operatore, stazione=self.roboqbo,
        )
        con_abilitazione = self.client.get(url)
        self.assertContains(con_abilitazione, "OP-CODA-OPER")
        self.assertContains(con_abilitazione, "RoboQbo")

    def test_output_crea_lotto_e_carico_e_permette_chiusura_ordine(self):
        ciclo, _ = self.crea_ciclo()
        ordine = OrdineProduzione.objects.create(
            codice="OP-OUT", linea=self.linea, prodotto=self.prodotto, ciclo=ciclo,
            quantita_pianificata=Decimal("100"), creato_da=self.operatore,
        )
        prepara_ordine(ordine, self.operatore)
        avvia_ordine(ordine, self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        consumo = prenota_materiale(prima, self.giacenza, "20", self.operatore)
        consuma_materiale(consumo, self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)

        seconda = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        destinazione = Ubicazione.objects.create(
            nome="Prodotti finiti V2",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        output = registra_output(
            fase=seconda, articolo=self.prodotto, codice_lotto="PF-V2-001",
            quantita="95", ubicazione=destinazione, operatore=self.operatore,
            scaffale="PF", piano="1",
        )
        completa_fase(seconda, self.operatore)
        ordine = completa_ordine(ordine, self.operatore)

        self.assertEqual(ordine.stato, OrdineProduzione.Stato.COMPLETATO)
        self.assertEqual(output.stato, OutputProduzione.Stato.CARICATO)
        self.assertEqual(output.lotto.tipo, Lotto.Tipo.PRODUZIONE)
        giacenza = Giacenza.objects.get(
            lotto=output.lotto, ubicazione=destinazione, scaffale="PF", piano="1",
        )
        self.assertEqual(giacenza.quantita, Decimal("95"))
        self.assertEqual(
            output.collegamenti_movimento.get().movimento.tipo,
            Movimento.Tipo.PRODUZIONE,
        )

    def test_resa_fuori_specifica_apre_nc_e_richiede_deroga(self):
        ciclo, _ = self.crea_ciclo()
        ciclo.resa_minima_percentuale = Decimal("90")
        ciclo.resa_massima_percentuale = Decimal("105")
        ciclo.save(update_fields=(
            "resa_minima_percentuale", "resa_massima_percentuale",
        ))
        ordine = prepara_ordine(
            self.crea_ordine("OP-RESA", ciclo=ciclo), self.operatore,
        )
        self.assertEqual(ordine.resa_minima_percentuale, Decimal("90"))
        avvia_ordine(ordine, self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        consumo = prenota_materiale(prima, self.giacenza, "20", self.operatore)
        consuma_materiale(consumo, self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        seconda = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        registra_output(
            fase=seconda, articolo=self.prodotto, codice_lotto="LOT-RESA-80",
            quantita="80", ubicazione=self.ubicazione, operatore=self.operatore,
        )
        completa_fase(seconda, self.operatore)

        ordine = completa_ordine(ordine, self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.BLOCCATO_NC)
        self.assertEqual(ordine.resa_percentuale, Decimal("80.00"))
        nc = ordine.non_conformita.get(tipo=NonConformita.Tipo.RESA)
        self.assertEqual(nc.stato, NonConformita.Stato.APERTA)

        chiudi_non_conformita(
            nc, NonConformita.Esito.DEROGA, "Resa accettata da RQ", self.operatore,
        )
        ordine = completa_ordine(ordine, self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.COMPLETATO)

    def test_stazione_richiede_operatore_abilitato_e_assegnato(self):
        self.roboqbo.richiede_operatore_abilitato = True
        self.roboqbo.save(update_fields=("richiede_operatore_abilitato",))
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        AbilitazioneOperatore.objects.create(
            operatore=self.operatore, stazione=self.roboqbo, ruolo="Conduttore",
        )
        avvia_ordine(ordine, self.operatore)
        fase = ordine.fasi.get(sequenza=1)
        with self.assertRaisesMessage(ValidationError, "operatore abilitato"):
            avvia_fase(fase, self.operatore)

        assegnazione = assegna_operatore(fase, self.operatore, self.operatore)
        fase = avvia_fase(fase, self.operatore)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_CORSO)
        self.assertIsNone(assegnazione.terminato_il)

    def test_abilitazione_scaduta_non_consente_assegnazione(self):
        self.roboqbo.richiede_operatore_abilitato = True
        self.roboqbo.save(update_fields=("richiede_operatore_abilitato",))
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        fase = ordine.fasi.get(sequenza=1)
        AbilitazioneOperatore.objects.create(
            operatore=self.operatore, stazione=self.roboqbo,
            valida_dal=date(2025, 1, 1), valida_fino_al=date(2025, 12, 31),
        )
        with self.assertRaisesMessage(ValidationError, "abilitazione valida"):
            assegna_operatore(fase, self.operatore, self.operatore)

    def test_dipendenze_permettono_rami_paralleli(self):
        controllo = StazioneLavoro.objects.create(
            codice="CQ", nome="Controllo qualità", tipo=StazioneLavoro.Tipo.CONTROLLO,
        )
        passaggio_1 = self.linea.passaggi.get(ordine=1)
        passaggio_2 = self.linea.passaggi.get(ordine=2)
        passaggio_3 = PassaggioLinea.objects.create(
            linea=self.linea, stazione=controllo, ordine=3,
        )
        aggiungi_dipendenza(passaggio_2, passaggio_1)
        aggiungi_dipendenza(passaggio_3, passaggio_1)
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        seconda = avvia_fase(ordine.fasi.get(sequenza=2), self.operatore)
        terza = avvia_fase(ordine.fasi.get(sequenza=3), self.operatore)
        self.assertEqual(seconda.stato, FaseProduzione.Stato.IN_CORSO)
        self.assertEqual(terza.stato, FaseProduzione.Stato.IN_CORSO)

    def test_preparazione_pianifica_fasi_sequenziali_dalle_otto(self):
        primo = self.linea.passaggi.get(ordine=1)
        secondo = self.linea.passaggi.get(ordine=2)
        primo.durata_standard_minuti = 45
        secondo.durata_standard_minuti = 30
        primo.save(update_fields=("durata_standard_minuti",))
        secondo.save(update_fields=("durata_standard_minuti",))

        ordine = prepara_ordine(self.crea_ordine("OP-PIANO"), self.operatore)
        fase_1 = ordine.fasi.get(sequenza=1)
        fase_2 = ordine.fasi.get(sequenza=2)
        inizio_1 = timezone.localtime(fase_1.pianificata_inizio)
        fine_1 = timezone.localtime(fase_1.pianificata_fine)
        fine_2 = timezone.localtime(fase_2.pianificata_fine)

        self.assertEqual(inizio_1.hour, 8)
        self.assertEqual(inizio_1.minute, 0)
        self.assertEqual(fine_1.hour, 8)
        self.assertEqual(fine_1.minute, 45)
        self.assertEqual(fase_2.pianificata_inizio, fase_1.pianificata_fine)
        self.assertEqual(fine_2.hour, 9)
        self.assertEqual(fine_2.minute, 15)

    def test_pianificazione_rispetta_rami_paralleli(self):
        controllo = StazioneLavoro.objects.create(
            codice="CQ-PLAN", nome="Controllo pianificato",
            tipo=StazioneLavoro.Tipo.CONTROLLO,
        )
        passaggio_1 = self.linea.passaggi.get(ordine=1)
        passaggio_2 = self.linea.passaggi.get(ordine=2)
        passaggio_3 = PassaggioLinea.objects.create(
            linea=self.linea, stazione=controllo, ordine=3,
            durata_standard_minuti=20,
        )
        aggiungi_dipendenza(passaggio_2, passaggio_1)
        aggiungi_dipendenza(passaggio_3, passaggio_1)

        ordine = prepara_ordine(self.crea_ordine("OP-RAMI"), self.operatore)
        fase_1 = ordine.fasi.get(sequenza=1)
        fase_2 = ordine.fasi.get(sequenza=2)
        fase_3 = ordine.fasi.get(sequenza=3)

        self.assertEqual(fase_2.pianificata_inizio, fase_1.pianificata_fine)
        self.assertEqual(fase_3.pianificata_inizio, fase_1.pianificata_fine)

    def test_ordine_senza_data_non_genera_orari_pianificati(self):
        ordine = self.crea_ordine("OP-SENZA-DATA")
        ordine.pianificato_per = None
        ordine.save(update_fields=("pianificato_per",))
        ordine = prepara_ordine(ordine, self.operatore)
        self.assertFalse(
            ordine.fasi.exclude(pianificata_inizio=None).exists()
        )

    def test_avanzamento_ed_eseguibilita_derivano_dallo_stato_delle_fasi(self):
        ordine = prepara_ordine(self.crea_ordine("OP-AVANZ"), self.operatore)
        self.assertEqual(ordine.avanzamento_percentuale, 0)
        self.assertEqual(ordine.fasi_eseguibili, [])

        ordine = avvia_ordine(ordine, self.operatore)
        prima = ordine.fasi.get(sequenza=1)
        seconda = ordine.fasi.get(sequenza=2)
        self.assertTrue(prima.eseguibile)
        self.assertFalse(seconda.eseguibile)

        prima = avvia_fase(prima, self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        ordine.refresh_from_db()
        seconda.refresh_from_db()
        self.assertEqual(ordine.avanzamento_percentuale, 50)
        self.assertTrue(seconda.eseguibile)

    def test_ordini_della_stessa_linea_e_giorno_vengono_accodati(self):
        primo = prepara_ordine(self.crea_ordine("OP-CODA-1"), self.operatore)
        secondo = prepara_ordine(self.crea_ordine("OP-CODA-2"), self.operatore)

        self.assertEqual(secondo.pianificata_inizio, primo.pianificata_fine)
        self.assertEqual(
            timezone.localtime(primo.pianificata_inizio).hour, 8,
        )
        self.assertEqual(
            timezone.localtime(secondo.pianificata_inizio).hour, 10,
        )

    def test_pianificazione_rispetta_turni_e_pausa(self):
        TurnoLinea.objects.create(
            linea=self.linea, giorno_settimana=TurnoLinea.Giorno.MARTEDI,
            ora_inizio=time(8, 0), ora_fine=time(12, 0),
        )
        TurnoLinea.objects.create(
            linea=self.linea, giorno_settimana=TurnoLinea.Giorno.MARTEDI,
            ora_inizio=time(13, 0), ora_fine=time(17, 0),
        )
        primo = self.linea.passaggi.get(ordine=1)
        secondo = self.linea.passaggi.get(ordine=2)
        primo.durata_standard_minuti = 300
        secondo.durata_standard_minuti = 120
        primo.save(update_fields=("durata_standard_minuti",))
        secondo.save(update_fields=("durata_standard_minuti",))

        ordine = prepara_ordine(self.crea_ordine("OP-TURNI"), self.operatore)
        fase_1 = ordine.fasi.get(sequenza=1)
        fase_2 = ordine.fasi.get(sequenza=2)
        self.assertEqual(timezone.localtime(fase_1.pianificata_inizio).time(), time(8, 0))
        self.assertEqual(timezone.localtime(fase_1.pianificata_fine).time(), time(14, 0))
        self.assertEqual(timezone.localtime(fase_2.pianificata_inizio).time(), time(14, 0))
        self.assertEqual(timezone.localtime(fase_2.pianificata_fine).time(), time(16, 0))

    def test_completamento_in_ritardo_ripianifica_le_fasi_residue(self):
        primo = self.linea.passaggi.get(ordine=1)
        secondo = self.linea.passaggi.get(ordine=2)
        primo.durata_standard_minuti = 60
        secondo.durata_standard_minuti = 60
        primo.save(update_fields=("durata_standard_minuti",))
        secondo.save(update_fields=("durata_standard_minuti",))
        ordine = prepara_ordine(self.crea_ordine("OP-RIPIANO"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase_1 = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        registra_controllo(fase_1, self.ph, "4.0", self.operatore)
        fine_reale = timezone.make_aware(datetime(2026, 9, 1, 11, 0))

        with patch("produzione_v2.services.timezone.now", return_value=fine_reale):
            completa_fase(fase_1, self.operatore)

        fase_2 = ordine.fasi.get(sequenza=2)
        self.assertEqual(timezone.localtime(fase_2.pianificata_inizio).time(), time(11, 0))
        self.assertEqual(timezone.localtime(fase_2.pianificata_fine).time(), time(12, 0))
        self.assertTrue(ordine.eventi.filter(tipo="ORDINE_RIPIANIFICATO").exists())

    def test_ritardo_propaga_lo_slittamento_agli_ordini_successivi(self):
        for passaggio in self.linea.passaggi.all():
            passaggio.durata_standard_minuti = 60
            passaggio.save(update_fields=("durata_standard_minuti",))
        ordine_1 = prepara_ordine(self.crea_ordine("OP-LINEA-1"), self.operatore)
        ordine_2 = prepara_ordine(self.crea_ordine("OP-LINEA-2"), self.operatore)
        self.assertEqual(
            timezone.localtime(ordine_2.pianificata_inizio).time(), time(10, 0),
        )
        avvia_ordine(ordine_1, self.operatore)
        fase_1 = avvia_fase(ordine_1.fasi.get(sequenza=1), self.operatore)
        registra_controllo(fase_1, self.ph, "4.0", self.operatore)
        fine_reale = timezone.make_aware(datetime(2026, 9, 1, 11, 0))

        with patch("produzione_v2.services.timezone.now", return_value=fine_reale):
            completa_fase(fase_1, self.operatore)

        ordine_2.refresh_from_db()
        self.assertEqual(
            timezone.localtime(ordine_2.pianificata_inizio).time(), time(12, 0),
        )
        self.assertEqual(
            timezone.localtime(ordine_2.pianificata_fine).time(), time(14, 0),
        )
        self.assertTrue(
            ordine_2.eventi.filter(tipo="ORDINE_RIPIANIFICATO_PER_LINEA").exists(),
        )

    def test_ordine_annullato_non_occupa_la_linea(self):
        primo = prepara_ordine(self.crea_ordine("OP-LIBERA-1"), self.operatore)
        annulla_ordine(primo, "Piano annullato", self.operatore)
        secondo = prepara_ordine(self.crea_ordine("OP-LIBERA-2"), self.operatore)

        self.assertEqual(
            timezone.localtime(secondo.pianificata_inizio).hour, 8,
        )

    def test_tracciabilita_ordine_mostra_lotto_e_csv_auditabile(self):
        ordine = prepara_ordine(self.crea_ordine("OP-TRACE"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        prenota_materiale(fase, self.giacenza, "4", self.operatore)

        pagina = self.client.get(reverse(
            "produzione_v2:tracciabilita_ordine", args=(ordine.pk,),
        ))
        self.assertEqual(pagina.status_code, 200)
        self.assertContains(pagina, "Tracciabilità ordine OP-TRACE")
        self.assertContains(pagina, self.lotto.codice_lotto)

        esportazione = self.client.get(reverse(
            "produzione_v2:esporta_tracciabilita_ordine", args=(ordine.pk,),
        ))
        contenuto = esportazione.content.decode("utf-8-sig")
        self.assertEqual(esportazione.status_code, 200)
        self.assertIn("text/csv", esportazione["Content-Type"])
        self.assertIn("MATERIALE", contenuto)
        self.assertIn(self.lotto.codice_lotto, contenuto)

    def test_ricerca_inversa_lotto_individua_ordine_e_prodotto(self):
        ordine = prepara_ordine(self.crea_ordine("OP-RICHIAMO"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        prenota_materiale(fase, self.giacenza, "3", self.operatore)

        risposta = self.client.get(
            reverse("produzione_v2:ricerca_tracciabilita"),
            {"lotto": self.lotto.codice_lotto},
        )
        self.assertEqual(risposta.status_code, 200)
        self.assertContains(risposta, "OP-RICHIAMO")
        self.assertContains(risposta, self.lotto.codice_lotto)
        self.assertContains(risposta, self.prodotto.nome_per_produzione)

    def test_catena_lotto_attraversa_piu_ordini_a_valle(self):
        ordine_1 = prepara_ordine(self.crea_ordine("OP-CATENA-1"), self.operatore)
        fase_1 = ordine_1.fasi.get(sequenza=1)
        ConsumoMateriale.objects.create(
            ordine=ordine_1, fase=fase_1, articolo=self.materiale,
            lotto=self.lotto, giacenza=self.giacenza, ubicazione=self.ubicazione,
            quantita=Decimal("2"), stato=ConsumoMateriale.Stato.CONSUMATO,
        )
        lotto_intermedio = Lotto.objects.create(
            articolo=self.prodotto, codice_lotto="LOT-INTERMEDIO-V2",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=Decimal("2"),
        )
        OutputProduzione.objects.create(
            ordine=ordine_1, fase=fase_1, articolo=self.prodotto,
            codice_lotto=lotto_intermedio.codice_lotto, quantita=Decimal("2"),
            ubicazione=self.ubicazione, lotto=lotto_intermedio,
            stato=OutputProduzione.Stato.CARICATO, creato_da=self.operatore,
        )

        ordine_2 = prepara_ordine(self.crea_ordine("OP-CATENA-2"), self.operatore)
        fase_2 = ordine_2.fasi.get(sequenza=1)
        ConsumoMateriale.objects.create(
            ordine=ordine_2, fase=fase_2, articolo=self.prodotto,
            lotto=lotto_intermedio, ubicazione=self.ubicazione,
            quantita=Decimal("2"), stato=ConsumoMateriale.Stato.CONSUMATO,
        )
        lotto_finale = Lotto.objects.create(
            articolo=self.prodotto, codice_lotto="LOT-FINALE-V2",
            tipo=Lotto.Tipo.PRODUZIONE, quantita_iniziale=Decimal("2"),
        )
        OutputProduzione.objects.create(
            ordine=ordine_2, fase=fase_2, articolo=self.prodotto,
            codice_lotto=lotto_finale.codice_lotto, quantita=Decimal("2"),
            ubicazione=self.ubicazione, lotto=lotto_finale,
            stato=OutputProduzione.Stato.CARICATO, creato_da=self.operatore,
        )

        risposta = self.client.get(
            reverse("produzione_v2:ricerca_tracciabilita"),
            {"lotto": self.lotto.codice_lotto},
        )
        self.assertContains(risposta, "LOT-INTERMEDIO-V2")
        self.assertContains(risposta, "LOT-FINALE-V2")
        self.assertContains(risposta, "OP-CATENA-1")
        self.assertContains(risposta, "OP-CATENA-2")

    def test_dipendenza_ciclica_viene_rifiutata(self):
        passaggio_1 = self.linea.passaggi.get(ordine=1)
        passaggio_2 = self.linea.passaggi.get(ordine=2)
        aggiungi_dipendenza(passaggio_2, passaggio_1)
        with self.assertRaisesMessage(ValidationError, "creerebbe un ciclo"):
            aggiungi_dipendenza(passaggio_1, passaggio_2)

    def test_fase_facoltativa_puo_essere_saltata_solo_in_sequenza(self):
        passaggio_2 = self.linea.passaggi.get(ordine=2)
        passaggio_2.obbligatoria = False
        passaggio_2.save(update_fields=("obbligatoria",))
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        seconda = ordine.fasi.get(sequenza=2)
        with self.assertRaisesMessage(ValidationError, "fasi precedenti"):
            salta_fase(seconda, "Non richiesta", self.operatore)
        prima = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        registra_controllo(prima, self.ph, "4.0", self.operatore)
        completa_fase(prima, self.operatore)
        seconda = salta_fase(seconda, "Formato non previsto", self.operatore)
        self.assertEqual(seconda.stato, FaseProduzione.Stato.SALTATA)

    def test_stazione_puo_richiedere_una_risorsa(self):
        self.roboqbo.richiede_risorsa = True
        self.roboqbo.save(update_fields=("richiede_risorsa",))
        risorsa = RisorsaProduzione.objects.create(
            stazione=self.roboqbo, codice="RQ-01", nome="RoboQbo 1",
            tipo=RisorsaProduzione.Tipo.MACCHINA,
        )
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = ordine.fasi.get(sequenza=1)
        with self.assertRaisesMessage(ValidationError, "risorsa produttiva"):
            avvia_fase(fase, self.operatore)
        impegna_risorsa(fase, risorsa, self.operatore)
        fase = avvia_fase(fase, self.operatore)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_CORSO)

    def test_risorsa_non_puo_essere_usata_da_due_ordini(self):
        risorsa = RisorsaProduzione.objects.create(
            stazione=self.roboqbo, codice="RQ-UNICA", nome="RoboQbo unica",
            tipo=RisorsaProduzione.Tipo.MACCHINA,
        )
        ordine_1 = prepara_ordine(self.crea_ordine("OP-R1"), self.operatore)
        ordine_2 = prepara_ordine(self.crea_ordine("OP-R2"), self.operatore)
        fase_1 = ordine_1.fasi.get(sequenza=1)
        fase_2 = ordine_2.fasi.get(sequenza=1)
        impegno = impegna_risorsa(fase_1, risorsa, self.operatore)
        with self.assertRaisesMessage(ValidationError, "già impegnata"):
            impegna_risorsa(fase_2, risorsa, self.operatore)
        rilascia_risorsa(impegno, self.operatore)
        secondo_impegno = impegna_risorsa(fase_2, risorsa, self.operatore)
        self.assertIsNone(secondo_impegno.rilasciata_il)

    def test_sospensione_rilascia_risorse_e_ripresa_richiede_riassegnazione(self):
        self.roboqbo.richiede_risorsa = True
        self.roboqbo.richiede_operatore_abilitato = True
        self.roboqbo.save(update_fields=(
            "richiede_risorsa", "richiede_operatore_abilitato",
        ))
        risorsa = RisorsaProduzione.objects.create(
            stazione=self.roboqbo, codice="RQ-SOSP", nome="RoboQbo sospensione",
            tipo=RisorsaProduzione.Tipo.MACCHINA,
        )
        AbilitazioneOperatore.objects.create(
            operatore=self.operatore, stazione=self.roboqbo,
        )
        ordine = prepara_ordine(self.crea_ordine(), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = ordine.fasi.get(sequenza=1)
        assegna_operatore(fase, self.operatore, self.operatore)
        impegno = impegna_risorsa(fase, risorsa, self.operatore)
        fase = avvia_fase(fase, self.operatore)

        ordine = sospendi_ordine(ordine, "Fermo tecnico", self.operatore)
        fase.refresh_from_db()
        impegno.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.SOSPESO)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_ATTESA)
        self.assertIsNotNone(impegno.rilasciata_il)

        ordine = riprendi_ordine(ordine, self.operatore)
        with self.assertRaisesMessage(ValidationError, "Riassegna una risorsa"):
            riprendi_fase(fase, self.operatore)
        assegna_operatore(fase, self.operatore, self.operatore)
        impegna_risorsa(fase, risorsa, self.operatore)
        fase = riprendi_fase(fase, self.operatore)
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.IN_CORSO)
        self.assertEqual(fase.stato, FaseProduzione.Stato.IN_CORSO)

    def test_annullamento_rilascia_prenotazioni_ma_blocca_materiali_consumati(self):
        ordine = prepara_ordine(self.crea_ordine("OP-ANN"), self.operatore)
        avvia_ordine(ordine, self.operatore)
        fase = avvia_fase(ordine.fasi.get(sequenza=1), self.operatore)
        consumo = prenota_materiale(fase, self.giacenza, "5", self.operatore)
        ordine = sospendi_ordine(ordine, "Da annullare", self.operatore)
        ordine = annulla_ordine(ordine, "Ordine cliente annullato", self.operatore)
        consumo.refresh_from_db()
        self.assertEqual(ordine.stato, OrdineProduzione.Stato.ANNULLATO)
        self.assertEqual(consumo.stato, ConsumoMateriale.Stato.REINTEGRATO)
        self.giacenza.refresh_from_db()
        self.assertEqual(self.giacenza.quantita, Decimal("20"))

        ordine_2 = prepara_ordine(self.crea_ordine("OP-ANN-2"), self.operatore)
        avvia_ordine(ordine_2, self.operatore)
        fase_2 = avvia_fase(ordine_2.fasi.get(sequenza=1), self.operatore)
        consumo_2 = prenota_materiale(fase_2, self.giacenza, "5", self.operatore)
        consuma_materiale(consumo_2, self.operatore)
        ordine_2 = sospendi_ordine(ordine_2, "Verifica", self.operatore)
        with self.assertRaisesMessage(ValidationError, "materiali consumati"):
            annulla_ordine(ordine_2, "Tentativo non sicuro", self.operatore)
