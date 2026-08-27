from django.test import TestCase

from .forms import ArticoloForm, RicettaForm, RigaRicettaForm
from .models import Articolo, Ricetta


class ArticoloFormTests(TestCase):
    def dati_validi(self):
        return {
            "codice": "ART-FORM",
            "descrizione": "Articolo form",
            "nome_produzione": "",
            "categoria": Articolo.Categoria.MATERIA_PRIMA,
            "unita_misura": Articolo.UnitaMisura.KG,
            "quantita_per_confezione": "1.250",
            "scorta_minima": "0",
            "criterio_rotazione": Articolo.CriterioRotazione.FIFO,
            "tipo_packaging": "",
            "pezzi_per_imballo": "",
            "attivo": "on",
            "note": "",
        }

    def test_accetta_quantita_per_confezione_positiva(self):
        form = ArticoloForm(data=self.dati_validi())

        self.assertTrue(form.is_valid(), form.errors)

    def test_rifiuta_quantita_per_confezione_non_positiva(self):
        dati = self.dati_validi()
        dati["quantita_per_confezione"] = "0"
        form = ArticoloForm(data=dati)

        self.assertFalse(form.is_valid())
        self.assertIn("quantita_per_confezione", form.errors)


class RicettaFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.prodotto = Articolo.objects.create(
            codice="RIC-FORM",
            descrizione="Prodotto ricetta form",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ingrediente = Articolo.objects.create(
            codice="ING-FORM",
            descrizione="Ingrediente ricetta form",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        Ricetta.objects.create(
            articolo=cls.prodotto,
            nome="Ricetta attiva esistente",
            versione="1",
            attiva=True,
        )

    def test_non_consente_due_ricette_attive_per_articolo(self):
        form = RicettaForm(
            data={
                "tipo_prodotto": Articolo.Categoria.PRODOTTO_FINITO,
                "articolo": self.prodotto.pk,
                "nome": "Seconda ricetta",
                "attiva": "on",
                "note": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("attiva", form.errors)

    def test_consente_una_seconda_versione_non_attiva(self):
        form = RicettaForm(
            data={
                "tipo_prodotto": Articolo.Categoria.PRODOTTO_FINITO,
                "articolo": self.prodotto.pk,
                "nome": "Seconda ricetta",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        ricetta = form.save()
        self.assertEqual(ricetta.versione, "2")

    def test_filtra_i_prodotti_in_base_al_tipo(self):
        semilavorato = Articolo.objects.create(
            codice="SL-FORM",
            descrizione="Semilavorato form",
            categoria=Articolo.Categoria.SEMILAVORATO,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        form = RicettaForm(
            data={
                "tipo_prodotto": Articolo.Categoria.SEMILAVORATO,
                "articolo": semilavorato.pk,
                "nome": "Ricetta semilavorato",
                "attiva": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn(self.prodotto, form.fields["articolo"].queryset)

    def test_quantita_ingrediente_deve_essere_positiva(self):
        form = RigaRicettaForm(
            data={
                "articolo": self.ingrediente.pk,
                "quantita": "-1",
                "ingrediente_prodotto": "on",
                "note": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("quantita", form.errors)
