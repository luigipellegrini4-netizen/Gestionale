from django.core.management.base import BaseCommand, CommandError
from magazzino.backup_db import svuota_dati_magazzino


class Command(BaseCommand):
    help = (
        "Elimina esclusivamente i dati dell'app magazzino, conservando "
        "utenti, gruppi, permessi e amministratori."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--conferma",
            action="store_true",
            help="Conferma l'eliminazione irreversibile dei dati di magazzino.",
        )

    def handle(self, *args, **options):
        if not options["conferma"]:
            raise CommandError(
                "Operazione annullata. Ripeti aggiungendo --conferma."
            )

        conteggi = svuota_dati_magazzino()

        totale = sum(conteggi.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Dati di magazzino eliminati: {totale} record. "
                "Utenti, gruppi e permessi sono stati conservati."
            )
        )
