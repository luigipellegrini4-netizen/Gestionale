import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .backup_db import crea_backup, ripristina_backup
from .models import (
    Articolo, BatchProduzione, CarrelloProduzione, Fornitore, Giacenza,
    Lotto, Movimento, Produzione, TankProduzione, Ubicazione,
)


class BackupDatabaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            username="backup-admin",
            password="password-di-test",
            email="admin@example.com",
        )
        cls.operatore = get_user_model().objects.create_user(
            username="backup-operatore",
            password="password-di-test",
        )
        cls.utente_normale = get_user_model().objects.create_user(
            username="backup-normale",
            password="password-di-test",
        )
        cls.fornitore = Fornitore.objects.create(
            codice="FOR-BACKUP",
            ragione_sociale="Fornitore backup",
        )
        cls.articolo = Articolo.objects.create(
            codice="ART-BACKUP",
            descrizione="Articolo backup",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Ubicazione backup",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )
        cls.lotto = Lotto.objects.create(
            articolo=cls.articolo,
            fornitore=cls.fornitore,
            codice_lotto="LOT-BACKUP",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto,
            ubicazione=cls.ubicazione,
            quantita=Decimal("7"),
        )
        Movimento.objects.create(
            tipo=Movimento.Tipo.CARICO,
            lotto=cls.lotto,
            quantita=Decimal("10"),
            ubicazione_destinazione=cls.ubicazione,
            eseguito_da=cls.operatore,
        )

    def test_esportazione_web_e_riservata_al_superuser(self):
        self.client.force_login(self.utente_normale)
        response = self.client.get(reverse("esporta_backup"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("esporta_backup"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        documento = json.loads(response.content)
        self.assertEqual(documento["formato"], "MIRA_BACKUP")
        self.assertIn("magazzino.registrooperazione", documento["conteggi"])

    def test_round_trip_sostituisce_i_dati_e_preserva_utenti(self):
        contenuto = crea_backup().encode("utf-8")
        Fornitore.objects.filter(pk=self.fornitore.pk).update(
            ragione_sociale="Nome modificato"
        )
        Fornitore.objects.create(
            codice="DA-RIMUOVERE",
            ragione_sociale="Record successivo",
        )

        with TemporaryDirectory() as cartella:
            with override_settings(BASE_DIR=cartella):
                risultato = ripristina_backup(contenuto)
                self.assertTrue(
                    (Path(cartella) / "backups" / risultato["backup_precedente"]).exists()
                )

        self.assertEqual(
            Fornitore.objects.get(codice="FOR-BACKUP").ragione_sociale,
            "Fornitore backup",
        )
        self.assertFalse(Fornitore.objects.filter(codice="DA-RIMUOVERE").exists())
        self.assertTrue(get_user_model().objects.filter(username="backup-admin").exists())
        movimento = Movimento.objects.get()
        self.assertEqual(movimento.eseguito_da.username, "backup-operatore")
        self.assertEqual(Giacenza.objects.get().quantita, Decimal("7"))

    def test_backup_non_valido_non_modifica_i_dati(self):
        with self.assertRaisesMessage(ValueError, "Formato o versione"):
            ripristina_backup(b'{"formato":"ALTRO","versione":1,"dati":[]}')

        self.assertTrue(Fornitore.objects.filter(codice="FOR-BACKUP").exists())

    def test_round_trip_include_batch_e_carrelli_indipendenti(self):
        prodotto = Articolo.objects.create(
            codice="PF-BACKUP", descrizione="Prodotto backup",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        produzione = Produzione.objects.create(
            articolo=prodotto, data_produzione="2026-08-28",
            numero_batch_previsti=1, lotto_provvisorio="260829",
        )
        tank = TankProduzione.objects.create(
            produzione=produzione, numero=1, numero_batch=1,
            gradi_brix=Decimal("42"), ph=Decimal("4.0"),
        )
        BatchProduzione.objects.create(
            produzione=produzione, tank=tank, numero=1,
            ora_inizio="08:00", ora_fine="08:20",
            esito_conformita="C", registrato_da=self.operatore,
        )
        CarrelloProduzione.objects.create(
            produzione=produzione, numero=1,
            numero_pezzi=500, esito_pastorizzazione="C",
            registrato_da=self.operatore,
        )
        contenuto = crea_backup().encode("utf-8")

        with TemporaryDirectory() as cartella, override_settings(BASE_DIR=cartella):
            ripristina_backup(contenuto)

        carrello = CarrelloProduzione.objects.select_related("registrato_da").get()
        self.assertEqual(carrello.registrato_da.username, "backup-operatore")
        self.assertEqual(BatchProduzione.objects.get().tank.numero, 1)
