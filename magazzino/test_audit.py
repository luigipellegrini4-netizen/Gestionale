from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from .models import Fornitore, RegistroOperazione


class RegistroOperazioniTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operatore = get_user_model().objects.create_user(
            username="audit-operatore",
            password="password-di-test",
        )
        cls.operatore.user_permissions.add(
            Permission.objects.get(codename="operare_magazzino")
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username="audit-admin",
            password="password-di-test",
            email="audit@example.com",
        )

    def test_post_riuscito_registra_utente_data_e_operazione(self):
        self.client.force_login(self.operatore)
        response = self.client.post(
            reverse("nuovo_fornitore"),
            {
                "codice": "FOR-AUDIT",
                "ragione_sociale": "Fornitore audit",
                "attivo": "on",
            },
            REMOTE_ADDR="127.0.0.1",
        )

        self.assertRedirects(response, reverse("elenco_fornitori"))
        self.assertTrue(Fornitore.objects.filter(codice="FOR-AUDIT").exists())
        log = RegistroOperazione.objects.get()
        self.assertEqual(log.utente, self.operatore)
        self.assertEqual(log.azione, "Creazione fornitore")
        self.assertEqual(log.area, "Anagrafiche")
        self.assertIn("Ragione sociale: Fornitore audit", log.descrizione)
        self.assertNotIn("csrf", log.descrizione.lower())
        self.assertEqual(log.dettagli["codice"], "FOR-AUDIT")
        self.assertEqual(log.indirizzo_ip, "127.0.0.1")
        self.assertIsNotNone(log.data_ora)
        self.assertEqual(log.esito, RegistroOperazione.Esito.RIUSCITA)
        self.assertIsNotNone(log.codice_operazione)

    def test_registro_e_visibile_solo_al_superuser(self):
        self.client.force_login(self.operatore)
        response = self.client.get(reverse("registro_operazioni"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("registro_operazioni"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registro operazioni")

    def test_modifica_salva_valori_prima_e_dopo_ed_e_ricercabile(self):
        fornitore = Fornitore.objects.create(
            codice="FOR-STORICO",
            ragione_sociale="Nome precedente",
        )
        self.client.force_login(self.operatore)
        response = self.client.post(
            reverse("modifica_fornitore", args=[fornitore.pk]),
            {
                "codice": fornitore.codice,
                "ragione_sociale": "Nome successivo",
                "attivo": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        log = RegistroOperazione.objects.get(azione="Modifica fornitore")
        self.assertEqual(log.modello, "magazzino.fornitore")
        self.assertEqual(log.record_id, str(fornitore.pk))
        self.assertEqual(log.valori_precedenti["ragione_sociale"], "Nome precedente")
        self.assertEqual(log.valori_successivi["ragione_sociale"], "Nome successivo")

        self.client.force_login(self.superuser)
        ricerca = self.client.get(reverse("registro_operazioni"), {"q": "Nome successivo"})
        self.assertContains(ricerca, "Nome successivo")
        dettaglio = self.client.get(reverse("dettaglio_registro_operazione", args=[log.pk]))
        self.assertContains(dettaglio, "Nome precedente")
        self.assertContains(dettaglio, "Nome successivo")
