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

    def test_registro_e_visibile_solo_al_superuser(self):
        self.client.force_login(self.operatore)
        response = self.client.get(reverse("registro_operazioni"))
        self.assertEqual(response.status_code, 302)

        self.client.force_login(self.superuser)
        response = self.client.get(reverse("registro_operazioni"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Registro operazioni")
