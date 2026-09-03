from .calendar import CalendarioLinea
from .models import DipendenzaPassaggio, FaseProduzione


class PianificatoreDinamicoOrdine:
    def __init__(self, ordine):
        self.ordine = ordine
        self.calendario = CalendarioLinea(ordine.linea)

    def ripianifica_residue(self):
        fasi = list(self.ordine.fasi.select_related("passaggio").order_by("sequenza"))
        per_passaggio = {fase.passaggio_id: fase for fase in fasi}
        modificate = []
        for fase in fasi:
            if fase.stato != FaseProduzione.Stato.DA_AVVIARE:
                continue
            dipendenze = list(fase.passaggio.dipendenze.all())
            predecessori_ids = [d.predecessore_id for d in dipendenze]
            if not dipendenze:
                predecessori_ids = [
                    altra.passaggio_id for altra in fasi if altra.sequenza < fase.sequenza
                ]
            fini = []
            pianificabile = True
            dipendenze_per_id = {d.predecessore_id: d for d in dipendenze}
            for predecessore_id in predecessori_ids:
                predecessore = per_passaggio[predecessore_id]
                dipendenza = dipendenze_per_id.get(predecessore_id)
                if dipendenza and dipendenza.modalita == DipendenzaPassaggio.Modalita.FLUSSO:
                    fine = predecessore.iniziata_il or predecessore.pianificata_inizio
                else:
                    fine = (
                        predecessore.completata_il
                        if predecessore.stato in (
                            FaseProduzione.Stato.COMPLETATA,
                            FaseProduzione.Stato.SALTATA,
                        ) and predecessore.completata_il
                        else predecessore.pianificata_fine
                    )
                if fine is None:
                    pianificabile = False
                    break
                fini.append(fine)
            if not pianificabile:
                continue
            nuovo_inizio = max(fini) if fini else fase.pianificata_inizio
            if nuovo_inizio is None:
                continue
            nuovo_inizio = self.calendario.normalizza(nuovo_inizio)
            nuova_fine = self.calendario.aggiungi_minuti(
                nuovo_inizio, fase.passaggio.durata_standard_minuti,
            )
            if (
                fase.pianificata_inizio != nuovo_inizio
                or fase.pianificata_fine != nuova_fine
            ):
                fase.pianificata_inizio = nuovo_inizio
                fase.pianificata_fine = nuova_fine
                fase.save(update_fields=("pianificata_inizio", "pianificata_fine"))
                modificate.append(fase)
        return modificate

    def ripianifica_intero_da(self, inizio_minimo):
        fasi = list(self.ordine.fasi.select_related("passaggio").order_by("sequenza"))
        if any(fase.stato != FaseProduzione.Stato.DA_AVVIARE for fase in fasi):
            return []
        per_passaggio = {fase.passaggio_id: fase for fase in fasi}
        non_pianificate = set(per_passaggio)
        modificate = []
        while non_pianificate:
            avanzamento = False
            for passaggio_id in list(non_pianificate):
                fase = per_passaggio[passaggio_id]
                dipendenze = list(fase.passaggio.dipendenze.all())
                predecessori = [d.predecessore_id for d in dipendenze]
                if not dipendenze:
                    predecessori = [
                        altra.passaggio_id for altra in fasi
                        if altra.sequenza < fase.sequenza
                    ]
                if any(pk in non_pianificate for pk in predecessori):
                    continue
                dipendenze_per_id = {d.predecessore_id: d for d in dipendenze}
                fini = [
                    (
                        per_passaggio[pk].pianificata_inizio
                        if dipendenze_per_id.get(pk)
                        and dipendenze_per_id[pk].modalita == DipendenzaPassaggio.Modalita.FLUSSO
                        else per_passaggio[pk].pianificata_fine
                    )
                    for pk in predecessori
                ]
                nuovo_inizio = max(fini) if fini else inizio_minimo
                nuovo_inizio = self.calendario.normalizza(nuovo_inizio)
                nuova_fine = self.calendario.aggiungi_minuti(
                    nuovo_inizio, fase.passaggio.durata_standard_minuti,
                )
                if (
                    fase.pianificata_inizio != nuovo_inizio
                    or fase.pianificata_fine != nuova_fine
                ):
                    fase.pianificata_inizio = nuovo_inizio
                    fase.pianificata_fine = nuova_fine
                    fase.save(update_fields=("pianificata_inizio", "pianificata_fine"))
                    modificate.append(fase)
                non_pianificate.remove(passaggio_id)
                avanzamento = True
            if not avanzamento:
                break
        return modificate


class PianificatoreDinamicoLinea:
    def __init__(self, linea):
        self.linea = linea

    def propaga_dopo(self, ordine):
        fine_corrente = ordine.pianificata_fine
        if fine_corrente is None:
            return []
        candidati = list(self.linea.ordini.exclude(pk=ordine.pk).filter(
            stato__in=("PRONTO", "IN_CORSO"),
            fasi__pianificata_inizio__isnull=False,
        ).distinct().prefetch_related("fasi__passaggio"))
        ordini = sorted(
            (
                candidato for candidato in candidati
                if candidato.pianificata_inizio is not None
                and candidato.pianificata_inizio >= ordine.pianificata_inizio
            ),
            key=lambda candidato: (candidato.pianificata_inizio, candidato.codice),
        )
        risultati = []
        for successivo in ordini:
            if successivo.pianificata_fine is None:
                continue
            if successivo.pianificata_inizio < fine_corrente:
                modificate = PianificatoreDinamicoOrdine(successivo).ripianifica_intero_da(
                    fine_corrente,
                )
                if modificate:
                    risultati.append((successivo, modificate))
                    successivo.refresh_from_db()
            fine_corrente = max(fine_corrente, successivo.pianificata_fine)
        return risultati
