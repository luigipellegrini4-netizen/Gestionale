"""Pulizia selettiva: nessuna rettifica automatica delle giacenze."""
import hashlib
import os
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from magazzino import backup_db as db


TARGET = (
    db.EventoProduzione, db.ConsuntivoEtichettatura, db.OrigineLottoCommerciale,
    db.LottoCommerciale, db.AppartenenzaUnitaLotto, db.AllocazioneOrigineUnita,
    db.NonConformita, db.MovimentoOutput, db.MovimentoProduzione,
    db.RilevazioneControllo, db.OutputProduzione, db.FabbisognoMateriale,
    db.ConsumoMateriale, db.UnitaProduzione, db.LottoLavorazione,
    db.ImpegnoRisorsa, db.AssegnazioneOperatore, db.FaseProduzione,
    db.OrdineProduzione, db.MaterialeSospesoNonConformita,
    db.CarrelloProduzione, db.BatchProduzione, db.TankProduzione,
    db.LottoUscitaProduzione, db.NonConformitaLotto,
    db.ConsumoConfezionamento, db.Inscatolamento, db.Confezionamento,
    db.PrelievoProduzioneSemilavorato, db.PrelievoProduzione,
    db.ProduzioneSemilavorato, db.Produzione,
)


def impronta_conservati():
    digest = hashlib.sha256()
    for model in db.MODELLI:
        if model not in TARGET:
            digest.update(serializers.serialize(
                "json", model.objects.order_by("pk"),
            ).encode("utf-8"))
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Elimina produzioni e NC di prova, conservando magazzino e configurazione."

    def add_arguments(self, parser):
        parser.add_argument("--conferma", action="store_true")

    def handle(self, *args, **options):
        for model in TARGET:
            self.stdout.write(f"{model._meta.label}: {model.objects.count()}")
        if not options["conferma"]:
            self.stdout.write("Solo anteprima. Arrestare il server e ripetere con --conferma.")
            return
        directory = Path(settings.BASE_DIR) / "backup_pre_pulizia"
        directory.mkdir(exist_ok=True)
        backup = directory / f"produzioni_{uuid4().hex}.json"
        try:
            with transaction.atomic():
                prima = impronta_conservati()
                documento = db.crea_backup()
                with backup.open("x", encoding="utf-8") as stream:
                    stream.write(documento)
                    stream.flush()
                    os.fsync(stream.fileno())
                self.stdout.write(f"Backup: {backup}")
                db.Produzione.objects.update(derivata_da=None, bloccata_da_nc=None)
                db.NonConformitaLotto.objects.update(produzione=None, batch=None)
                db.UnitaProduzione.objects.update(origine=None)
                for model in TARGET:
                    model.objects.all().delete()
                if any(model.objects.exists() for model in TARGET):
                    raise CommandError("Pulizia incompleta: ripristino transazione.")
                if impronta_conservati() != prima:
                    raise CommandError("Dati conservati modificati: ripristino transazione.")
        except Exception as exc:
            raise CommandError(f"Pulizia annullata: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(
            "Produzioni e NC eliminate. Magazzino, ricette e configurazione invariati."
        ))
