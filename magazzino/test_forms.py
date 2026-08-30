from decimal import Decimal

from django.test import TestCase

from .forms import ArticoloForm, CaricoLottoForm, RicettaForm, RigaRicettaForm
from .models import Articolo, Ricetta, Ubicazione


class CaricoLottoFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.articolo = Articolo.objects.create(
            codice="CAR-FORM",
            descrizione="Articolo carico form",
            categoria=Articolo.Categoria.MATERIA_PRIMA,
            unita_misura=Articolo.UnitaMisura.KG,
        )
        cls.ubicazione = Ubicazione.objects.create(
            nome="Ubicazione carico form",
            tipo_magazzino=Ubicazione.TipoMagazzino.MP,
        )

    def dati_validi(self):
        return {
            "articolo": self.articolo.pk,
            "codice_lotto": "LOT-FORM",
            "quantita": "10",
            "numero_colli": "1",
            "unita_acquisto_per_collo": "4",
            "peso_unita_acquisto": "2.5",
            "ddt": "DDT-123",
            "ubicazione": self.ubicazione.pk,
            "data_arrivo": "2026-08-28",
        }

    def test_richiede_almeno_fattura_o_ddt(self):
        dati = self.dati_validi()
        dati["ddt"] = ""
        form = CaricoLottoForm(data=dati)

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
        self.assertIn("Fattura oppure DDT", form.errors["__all__"][0])

    def test_ddt_soddisfa_il_requisito_del_documento(self):
        form = CaricoLottoForm(data=self.dati_validi())

        self.assertTrue(form.is_valid(), form.errors)

    def test_lotto_rimane_obbligatorio_per_articolo_tracciato(self):
        dati = self.dati_validi()
        dati["codice_lotto"] = ""
        form = CaricoLottoForm(data=dati)
        self.assertFalse(form.is_valid())
        self.assertIn("codice_lotto", form.errors)

    def test_lotto_non_e_richiesto_per_articolo_non_tracciato(self):
        articolo = Articolo.objects.create(
            codice="IGIENE-NO-LOTTO", descrizione="Sapone",
            categoria=Articolo.Categoria.IGIENE,
            unita_misura=Articolo.UnitaMisura.PZ,
            tracciabilita_lotto=False,
        )
        dati = self.dati_validi()
        dati["articolo"] = articolo.pk
        dati["codice_lotto"] = ""
        form = CaricoLottoForm(data=dati)
        self.assertTrue(form.is_valid(), form.errors)

    def test_fattura_soddisfa_il_requisito_del_documento(self):
        dati = self.dati_validi()
        dati["ddt"] = ""
        dati["fattura"] = "FATT-123"
        form = CaricoLottoForm(data=dati)

        self.assertTrue(form.is_valid(), form.errors)

    def test_calcola_peso_uda_mancante(self):
        dati = self.dati_validi()
        dati["peso_unita_acquisto"] = ""
        form = CaricoLottoForm(data=dati)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["peso_unita_acquisto"], Decimal("2.500000"))

    def test_calcola_numero_colli_mancante(self):
        dati = self.dati_validi()
        dati["numero_colli"] = ""
        form = CaricoLottoForm(data=dati)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["numero_colli"], 1)

    def test_calcola_numero_uda_per_collo_mancante(self):
        dati = self.dati_validi()
        dati["unita_acquisto_per_collo"] = ""
        form = CaricoLottoForm(data=dati)

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["unita_acquisto_per_collo"], 4)

    def test_rifiuta_tre_valori_non_coerenti(self):
        dati = self.dati_validi()
        dati["peso_unita_acquisto"] = "3"
        form = CaricoLottoForm(data=dati)

        self.assertFalse(form.is_valid())
        self.assertIn("non sono coerenti", form.errors["__all__"][0])


class ArticoloFormTests(TestCase):
    def dati_validi(self):
        return {
            "codice": "ART-FORM",
            "descrizione": "Articolo form",
            "nome_produzione": "",
            "categoria": Articolo.Categoria.MATERIA_PRIMA,
            "unita_misura": Articolo.UnitaMisura.KG,
            "scorta_minima": "0",
            "tipo_packaging": "",
            "attivo": "on",
            "note": "",
        }

    def test_accetta_articolo_valido(self):
        form = ArticoloForm(data=self.dati_validi())

        self.assertTrue(form.is_valid(), form.errors)

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
