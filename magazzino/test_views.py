from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import (
    Articolo,
    Giacenza,
    Inscatolamento,
    Lotto,
    Movimento,
    Ubicazione,
)


class SituazioneMagazzinoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="situazione-test",
            password="password-di-test",
        )
        cls.prodotto = Articolo.objects.create(
            codice="PF-TEST",
            descrizione="Prodotto finito test",
            categoria=Articolo.Categoria.PRODOTTO_FINITO,
            unita_misura=Articolo.UnitaMisura.PZ,
        )
        cls.imballo = Articolo.objects.create(
            codice="SCATOLA-TEST",
            descrizione="Scatola test",
            categoria=Articolo.Categoria.PACKAGING,
            unita_misura=Articolo.UnitaMisura.PZ,
            tipo_packaging=Articolo.TipoPackaging.SCATOLA,
            pezzi_per_imballo=6,
        )
        cls.ubicazione_a = Ubicazione.objects.create(
            nome="Prodotti finiti A",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.ubicazione_b = Ubicazione.objects.create(
            nome="Prodotti finiti B",
            tipo_magazzino=Ubicazione.TipoMagazzino.PRODOTTI_FINITI,
        )
        cls.lotto_prodotto = Lotto.objects.create(
            articolo=cls.prodotto,
            codice_lotto="PF-LOT",
            tipo=Lotto.Tipo.PRODUZIONE,
            quantita_iniziale=Decimal("10"),
        )
        cls.lotto_imballo = Lotto.objects.create(
            articolo=cls.imballo,
            codice_lotto="IMB-LOT",
            tipo=Lotto.Tipo.ACQUISTO,
            quantita_iniziale=Decimal("10"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_prodotto,
            ubicazione=cls.ubicazione_a,
            quantita=Decimal("7"),
        )
        Giacenza.objects.create(
            lotto=cls.lotto_prodotto,
            ubicazione=cls.ubicazione_b,
            quantita=Decimal("3"),
        )
        Inscatolamento.objects.create(
            lotto_prodotto=cls.lotto_prodotto,
            lotto_imballo=cls.lotto_imballo,
            quantita_prodotti=Decimal("6"),
            quantita_imballi=Decimal("1"),
            pezzi_per_imballo=6,
            data_inscatolamento=date.today(),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_totali_sono_calcolati_correttamente(self):
        response = self.client.get(reverse("situazione_magazzino"))

        self.assertEqual(response.status_code, 200)
        prodotto = next(
            articolo
            for articolo in response.context["articoli"]
            if articolo.pk == self.prodotto.pk
        )
        self.assertEqual(prodotto.giacenza_totale, Decimal("10"))

        giacenze_prodotto = [
            giacenza
            for giacenza in response.context["giacenze"]
            if giacenza.lotto_id == self.lotto_prodotto.pk
        ]
        self.assertEqual(len(giacenze_prodotto), 2)
        for giacenza in giacenze_prodotto:
            self.assertEqual(giacenza.quantita_totale, Decimal("10"))
            self.assertEqual(giacenza.quantita_inscatolata, Decimal("6"))
            self.assertEqual(giacenza.quantita_sfusa, Decimal("4"))

    def test_numero_query_non_cresce_per_articolo_o_lotto(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("situazione_magazzino"))

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 10)

    def test_movimenti_sono_paginati_a_cinquanta(self):
        Movimento.objects.bulk_create(
            [
                Movimento(
                    tipo=Movimento.Tipo.CARICO,
                    lotto=self.lotto_prodotto,
                    quantita=Decimal("1"),
                    ubicazione_destinazione=self.ubicazione_a,
                )
                for _ in range(51)
            ]
        )

        prima_pagina = self.client.get(reverse("elenco_movimenti"))
        seconda_pagina = self.client.get(
            reverse("elenco_movimenti"),
            {"page": 2},
        )

        self.assertEqual(len(prima_pagina.context["movimenti"]), 50)
        self.assertEqual(len(seconda_pagina.context["movimenti"]), 1)
        self.assertContains(prima_pagina, "Pagina 1 di 2")
