from decimal import Decimal
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from magazzino.models import (
    Articolo,
    Fornitore,
    Ricetta,
    RigaRicetta,
    Ubicazione,
)
from magazzino.services import registra_carico_lotto


UBICAZIONI = [
    ("Magazzino stoccaggio MP", "MP"),
    ("Cella stoccaggio MP positiva", "MP"),
    ("Cella stoccaggio MP negativa", "MP"),
    ("Magazzino igiene", "IGIENE"),
    ("Magazzino MOCA", "MOCA"),
    ("Cella stoccaggio SL positiva", "SEMILAVORATI"),
    ("Cella stoccaggio SL negativa", "SEMILAVORATI"),
    ("Magazzino produzione", "PRODUZIONE"),
    ("Magazzino packaging", "PACKAGING"),
    ("Magazzino prodotti finiti", "PRODOTTI_FINITI"),
]

FORNITORI = [
    ("FOR-FRUTTA", "Frutta Italiana Demo", "Materie prime ortofrutticole"),
    ("FOR-ZUCCHERO", "Zuccheri Alimentari Demo", "Zucchero e derivati"),
    ("FOR-INGREDIENTI", "Ingredienti Tecnici Demo", "Pectina e correttori"),
    ("FOR-VETRO", "Vetri Alimentari Demo", "Vasetti e capsule MOCA"),
    ("FOR-PACK", "Packaging Etichette Demo", "Etichette e scatole"),
    ("FOR-IGIENE", "Igiene Industria Demo", "Materiali per pulizia e igiene"),
]

ARTICOLI = [
    ("MP-FRAGOLA", "Fragole", "MATERIA_PRIMA", "KG", "10", "FEFO", ""),
    ("MP-ZUCCHERO", "Zucchero semolato", "MATERIA_PRIMA", "KG", "25", "FIFO", ""),
    ("MP-LIMONE", "Succo di limone", "MATERIA_PRIMA", "L", "5", "FEFO", ""),
    ("SL-PECTINA", "Pectina", "SEMILAVORATO", "KG", "1", "FIFO", ""),
    ("MOCA-VASO-250", "Vasetto vetro 250 g", "MOCA", "PZ", "1", "FIFO", ""),
    ("MOCA-CAPS-63", "Capsula twist-off 63 mm", "MOCA", "PZ", "1", "FIFO", ""),
    ("ETI-FRAG-250", "Etichetta confettura fragole 250 g", "PACKAGING", "PZ", "1", "FIFO", "ETICHETTA"),
    ("SCA-12X250", "Scatola 12 vasetti da 250 g", "PACKAGING", "PZ", "1", "FIFO", "SCATOLA"),
    ("PF-FRAG-250", "Confettura extra di fragole 250 g", "PRODOTTO_FINITO", "PZ", None, "FIFO", ""),
    ("IGI-DETERGENTE", "Detergente impianti alimentari", "IGIENE", "L", "5", "FIFO", ""),
]


class Command(BaseCommand):
    help = "Crea o aggiorna anagrafiche demo per il flusso di produzione."

    @transaction.atomic
    def handle(self, *args, **options):
        for nome, tipo in UBICAZIONI:
            Ubicazione.objects.update_or_create(
                nome=nome,
                defaults={
                    "tipo_magazzino": tipo,
                    "scaffale": "",
                    "piano": "",
                    "attiva": True,
                },
            )

        for codice, ragione_sociale, note in FORNITORI:
            Fornitore.objects.update_or_create(
                codice=codice,
                defaults={
                    "ragione_sociale": ragione_sociale,
                    "attivo": True,
                    "note": note,
                },
            )

        articoli = {}
        for codice, descrizione, categoria, unita, confezione, rotazione, packaging in ARTICOLI:
            valori = {
                "descrizione": descrizione,
                "nome_produzione": descrizione,
                "categoria": categoria,
                "unita_misura": unita,
                "quantita_per_confezione": (
                    Decimal(confezione) if confezione is not None else None
                ),
                "scorta_minima": Decimal("0"),
                "criterio_rotazione": rotazione,
                "tipo_packaging": packaging,
                "attivo": True,
                "note": "Dato dimostrativo",
            }
            if packaging == "SCATOLA":
                valori["pezzi_per_imballo"] = 12
            articolo, _ = Articolo.objects.update_or_create(
                codice=codice,
                defaults=valori,
            )
            articoli[codice] = articolo

        Ricetta.objects.filter(
            articolo=articoli["PF-FRAG-250"],
            attiva=True,
        ).exclude(versione="1").update(attiva=False)
        ricetta, _ = Ricetta.objects.update_or_create(
            articolo=articoli["PF-FRAG-250"],
            versione="1",
            defaults={
                "nome": "Ricetta base Robocubo - 1 batch",
                "attiva": True,
                "note": "Quantità teoriche per un batch dimostrativo.",
            },
        )
        righe = [
            ("MP-FRAGOLA", "18", True),
            ("MP-ZUCCHERO", "12", True),
            ("MP-LIMONE", "0.20", True),
            ("SL-PECTINA", "0.30", True),
            ("MOCA-VASO-250", "1", False),
            ("MOCA-CAPS-63", "1", False),
        ]
        ricetta.righe.exclude(
            articolo__codice__in=[codice for codice, _, _ in righe]
        ).delete()
        for codice, quantita, entra_nel_prodotto in righe:
            RigaRicetta.objects.update_or_create(
                ricetta=ricetta,
                articolo=articoli[codice],
                defaults={
                    "quantita": Decimal(quantita),
                    "ingrediente_prodotto": entra_nel_prodotto,
                    "note": "Dato dimostrativo",
                },
            )

        carichi = [
            ("MP-FRAGOLA", "LOT-FRAG-001", "FOR-FRUTTA", "250", "Cella stoccaggio MP positiva", "F1", "P1", 30),
            ("MP-ZUCCHERO", "LOT-ZUC-001", "FOR-ZUCCHERO", "500", "Magazzino stoccaggio MP", "S1", "P1", None),
            ("MP-LIMONE", "LOT-LIM-001", "FOR-INGREDIENTI", "100", "Cella stoccaggio MP positiva", "F2", "P1", 90),
            ("SL-PECTINA", "LOT-PEC-001", "FOR-INGREDIENTI", "50", "Cella stoccaggio SL positiva", "S1", "P1", 365),
            ("MOCA-VASO-250", "LOT-VASO-001", "FOR-VETRO", "2000", "Magazzino MOCA", "V1", "P1", None),
            ("MOCA-CAPS-63", "LOT-CAPS-001", "FOR-VETRO", "2000", "Magazzino MOCA", "V2", "P1", None),
            ("ETI-FRAG-250", "LOT-ETI-001", "FOR-PACK", "2000", "Magazzino packaging", "E1", "P1", None),
            ("SCA-12X250", "LOT-SCA-001", "FOR-PACK", "200", "Magazzino packaging", "S1", "P1", None),
        ]
        carichi_creati = 0
        for articolo_codice, lotto_codice, fornitore_codice, quantita, ubicazione_nome, scaffale, piano, giorni_scadenza in carichi:
            if articoli[articolo_codice].lotti.filter(
                codice_lotto=lotto_codice
            ).exists():
                continue
            registra_carico_lotto(
                articolo=articoli[articolo_codice],
                codice_lotto=lotto_codice,
                fornitore=Fornitore.objects.get(codice=fornitore_codice),
                quantita=Decimal(quantita),
                ubicazione=Ubicazione.objects.get(nome=ubicazione_nome),
                scaffale=scaffale,
                piano=piano,
                data_arrivo=date.today(),
                data_scadenza=(
                    date.today() + timedelta(days=giorni_scadenza)
                    if giorni_scadenza is not None else None
                ),
                causale="Carico dati dimostrativi",
                note="Dato dimostrativo",
            )
            carichi_creati += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Dati demo caricati: 10 ubicazioni, 6 fornitori, "
                "10 articoli e 1 ricetta Robocubo. "
                f"Nuovi carichi registrati: {carichi_creati}."
            )
        )
