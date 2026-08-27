from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Articolo, Fornitore, Ubicazione


class ImportazioneCSVTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="importazioni-test",
            password="password-di-test",
        )
        cls.user.user_permissions.add(
            Permission.objects.get(codename="operare_magazzino")
        )

    def setUp(self):
        self.client.force_login(self.user)

    def carica(self, tipo, testo):
        file_csv = SimpleUploadedFile(
            f"{tipo}.csv",
            testo.encode("utf-8"),
            content_type="text/csv",
        )
        return self.client.post(
            reverse("importazione_csv"),
            {"tipo": tipo, "file_csv": file_csv},
        )

    def test_template_fornitori_e_scaricabile(self):
        response = self.client.get(
            reverse("template_csv", args=["fornitori"])
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("codice;ragione_sociale", response.content.decode("utf-8-sig"))

    def test_template_articoli_include_quantita_per_confezione(self):
        response = self.client.get(reverse("template_csv", args=["articoli"]))

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "unita_misura;quantita_per_confezione;scorta_minima",
            response.content.decode("utf-8-sig"),
        )

    def test_import_fornitori_crea_e_aggiorna(self):
        intestazione = (
            "codice;ragione_sociale;partita_iva;telefono;email;"
            "indirizzo;attivo;note\n"
        )
        response = self.carica(
            "fornitori",
            intestazione
            + "FOR-1;Fornitore Uno;123;;uno@example.com;;vero;Prima importazione\n",
        )
        self.assertRedirects(response, reverse("importazione_csv"))
        self.assertTrue(Fornitore.objects.filter(codice="FOR-1").exists())

        self.carica(
            "fornitori",
            intestazione
            + "FOR-1;Fornitore Aggiornato;123;;;;falso;Aggiornato\n",
        )
        fornitore = Fornitore.objects.get(codice="FOR-1")
        self.assertEqual(fornitore.ragione_sociale, "Fornitore Aggiornato")
        self.assertFalse(fornitore.attivo)

    def test_file_con_una_riga_errata_non_importa_nulla(self):
        response = self.carica(
            "fornitori",
            "codice;ragione_sociale;partita_iva;telefono;email;"
            "indirizzo;attivo;note\n"
            "OK-1;Fornitore valido;;;;;vero;\n"
            "ERR-1;Email errata;;;non-e-una-email;;vero;\n",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Importazione annullata")
        self.assertFalse(Fornitore.objects.exists())

    def test_intestazioni_errate_mostrano_un_errore_comprensibile(self):
        response = self.carica(
            "fornitori",
            "codice;nome_errato\nFOR-1;Fornitore\n",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intestazioni CSV non valide")
        self.assertFalse(Fornitore.objects.exists())

    def test_importa_ubicazione_e_articolo(self):
        self.carica(
            "ubicazioni",
            "nome;tipo_magazzino;scaffale;piano;attiva\n"
            "Cella A;MP;S1;P2;si\n",
        )
        self.carica(
            "articoli",
            "codice;descrizione;nome_produzione;categoria;unita_misura;"
            "quantita_per_confezione;scorta_minima;"
            "criterio_rotazione;tipo_packaging;pezzi_per_imballo;"
            "attivo;note\n"
            "MP-CSV;Materia prima CSV;Materia CSV;MATERIA_PRIMA;KG;1,25;2,5;"
            "FEFO;;;vero;\n",
        )

        self.assertTrue(Ubicazione.objects.filter(nome="Cella A").exists())
        articolo = Articolo.objects.get(codice="MP-CSV")
        self.assertEqual(articolo.descrizione, "Materia prima CSV")
        self.assertEqual(articolo.nome_produzione, "Materia CSV")
        self.assertEqual(articolo.quantita_per_confezione, Decimal("1.250"))
        self.assertEqual(str(articolo.scorta_minima), "2.500")
