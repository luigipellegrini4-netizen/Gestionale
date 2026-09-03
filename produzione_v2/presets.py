from django.db import transaction
from django.db.models import Q

from .models import (
    DefinizioneControllo, DipendenzaPassaggio, LineaProduzione, PassaggioLinea,
    RisorsaProduzione, StazioneLavoro, TipoUnitaProduzione,
)


class PresetRoboQboInvasettamento:
    """Configurazione iniziale ripetibile della prima linea pilota V2."""

    @transaction.atomic
    def applica(self):
        creati = 0
        linea, nuovo = LineaProduzione.objects.get_or_create(
            codice="RQ-INV-V2",
            defaults={
                "nome": "RoboQbo e invasettamento V2",
                "descrizione": "Linea pilota configurabile del nuovo motore produttivo.",
            },
        )
        creati += nuovo
        roboqbo, nuovo = StazioneLavoro.objects.get_or_create(
            codice="ROBOQBO-V2",
            defaults={
                "nome": "RoboQbo V2",
                "tipo": StazioneLavoro.Tipo.TRASFORMAZIONE,
                "richiede_operatore_abilitato": True,
                "richiede_risorsa": True,
                "configurazione": {"preset": "roboqbo_invasettamento", "versione": 1},
            },
        )
        creati += nuovo
        invasettamento, nuovo = StazioneLavoro.objects.get_or_create(
            codice="INVASETTAMENTO-V2",
            defaults={
                "nome": "Invasettamento V2",
                "tipo": StazioneLavoro.Tipo.CONFEZIONAMENTO,
                "richiede_operatore_abilitato": True,
                "richiede_risorsa": True,
                "configurazione": {"preset": "roboqbo_invasettamento", "versione": 1},
            },
        )
        creati += nuovo
        passaggio_rq, nuovo = PassaggioLinea.objects.get_or_create(
            linea=linea, stazione=roboqbo,
            defaults={"ordine": 1, "durata_standard_minuti": 120},
        )
        creati += nuovo
        passaggio_inv, nuovo = PassaggioLinea.objects.get_or_create(
            linea=linea, stazione=invasettamento,
            defaults={"ordine": 2, "durata_standard_minuti": 180},
        )
        creati += nuovo
        dipendenza, nuovo = DipendenzaPassaggio.objects.get_or_create(
            passaggio=passaggio_inv, predecessore=passaggio_rq,
            defaults={"modalita": DipendenzaPassaggio.Modalita.FLUSSO},
        )
        creati += nuovo
        if dipendenza.modalita != DipendenzaPassaggio.Modalita.FLUSSO:
            dipendenza.modalita = DipendenzaPassaggio.Modalita.FLUSSO
            dipendenza.quantita_minima_avvio = 0
            dipendenza.save(update_fields=("modalita", "quantita_minima_avvio"))

        creati += self._controllo(
            roboqbo, "PH", "pH", 1, "", {
                "minimo_fisico": "0", "massimo_fisico": "14",
                "conforme_max": "4.1", "allerta_min_escluso": "4.1",
                "allerta_max": "4.4",
            },
        )
        creati += self._controllo(
            roboqbo, "BRIX", "Gradi Brix", 2, "°Bx", {
                "minimo_fisico": "0", "massimo_fisico": "100",
            },
        )
        creati += self._controllo(
            invasettamento, "TEMP", "Temperatura di invasettamento", 1, "°C", {
                "minimo_fisico": "0", "massimo_fisico": "150",
            },
        )
        chiusura, nuovo = DefinizioneControllo.objects.get_or_create(
            stazione=invasettamento, codice="CHIUSURA",
            defaults={
                "nome": "Chiusura contenitore conforme",
                "tipo_dato": DefinizioneControllo.TipoDato.BOOLEANO,
                "regole": {"atteso": True}, "ordine": 2,
            },
        )
        creati += nuovo

        for stazione, codice, nome, unita in (
            (roboqbo, "BATCH", "Batch RoboQbo", "KG"),
            (roboqbo, "TANK", "Tank RoboQbo", "KG"),
            (invasettamento, "LOTTO_CONF", "Lotto confezionato", "PZ"),
        ):
            _, nuovo = TipoUnitaProduzione.objects.get_or_create(
                stazione=stazione, codice=codice,
                defaults={"nome": nome, "unita_misura": unita},
            )
            creati += nuovo
        TipoUnitaProduzione.objects.filter(
            stazione=roboqbo, codice="TANK",
        ).update(richiede_quantita=False)
        for stazione, codice, nome in (
            (roboqbo, "RQ-01-V2", "RoboQbo 1"),
            (invasettamento, "INV-01-V2", "Linea invasettamento 1"),
        ):
            _, nuovo = RisorsaProduzione.objects.get_or_create(
                codice=codice,
                defaults={
                    "stazione": stazione, "nome": nome,
                    "tipo": RisorsaProduzione.Tipo.MACCHINA,
                },
            )
            creati += nuovo

        stazioni_successive = (
            ("PASTORIZZAZIONE-V2", "Pastorizzazione V2", StazioneLavoro.Tipo.TRASFORMAZIONE, 3, "PAST-01-V2", "Pastorizzatore 1"),
            ("ABBATTIMENTO-V2", "Abbattimento termico V2", StazioneLavoro.Tipo.TRASFORMAZIONE, 4, "ABB-01-V2", "Abbattitore 1"),
            ("VUOTO-V2", "Controllo vuoto V2", StazioneLavoro.Tipo.CONTROLLO, 5, "VUOTO-01-V2", "Postazione vuoto 1"),
            ("CHIUSURA-C-V2", "Chiusura lavorazione C", StazioneLavoro.Tipo.CONTROLLO, 6, None, None),
            ("ETICHETTATURA-V2", "Etichettatura V2", StazioneLavoro.Tipo.CONFEZIONAMENTO, 7, "ETI-01-V2", "Etichettatrice 1"),
            ("CONFEZIONAMENTO-V2", "Confezionamento V2", StazioneLavoro.Tipo.CONFEZIONAMENTO, 8, "CONF-01-V2", "Postazione confezionamento 1"),
        )
        passaggi = [passaggio_rq, passaggio_inv]
        for codice_stazione, nome_stazione, tipo, ordine, codice_risorsa, nome_risorsa in stazioni_successive:
            stazione, nuovo = StazioneLavoro.objects.get_or_create(
                codice=codice_stazione,
                defaults={
                    "nome": nome_stazione, "tipo": tipo,
                    "richiede_operatore_abilitato": True,
                    "richiede_risorsa": bool(codice_risorsa),
                    "configurazione": {"preset": "roboqbo_invasettamento", "versione": 2},
                },
            )
            creati += nuovo
            passaggio, nuovo = PassaggioLinea.objects.get_or_create(
                linea=linea, stazione=stazione,
                defaults={"ordine": ordine, "durata_standard_minuti": 60},
            )
            creati += nuovo
            passaggi.append(passaggio)
            if codice_risorsa:
                _, nuovo = RisorsaProduzione.objects.get_or_create(
                    codice=codice_risorsa,
                    defaults={
                        "stazione": stazione, "nome": nome_risorsa,
                        "tipo": RisorsaProduzione.Tipo.MACCHINA,
                    },
                )
                creati += nuovo

        for precedente, successivo in zip(passaggi[1:], passaggi[2:]):
            modalita = (
                DipendenzaPassaggio.Modalita.FLUSSO
                if successivo.ordine <= 5
                else DipendenzaPassaggio.Modalita.COMPLETAMENTO
            )
            dipendenza, nuovo = DipendenzaPassaggio.objects.get_or_create(
                passaggio=successivo, predecessore=precedente,
                defaults={"modalita": modalita},
            )
            creati += nuovo
            if dipendenza.modalita != modalita:
                dipendenza.modalita = modalita
                dipendenza.save(update_fields=("modalita",))

        for stazione in [passaggio.stazione for passaggio in passaggi[1:5]]:
            _, nuovo = TipoUnitaProduzione.objects.get_or_create(
                stazione=stazione, codice="CARRELLO",
                defaults={"nome": "Carrello", "unita_misura": "PZ", "richiede_quantita": False},
            )
            creati += nuovo

        linea_sl, nuovo = LineaProduzione.objects.get_or_create(
            codice="SEMILAVORATI-V2",
            defaults={
                "nome": "Produzione semilavorati V2",
                "descrizione": "Linea autonoma: output a magazzino o buffer di produzione.",
            },
        )
        creati += nuovo
        stazione_sl, nuovo = StazioneLavoro.objects.get_or_create(
            codice="SEMILAVORATI-V2",
            defaults={
                "nome": "Preparazione semilavorati V2",
                "tipo": StazioneLavoro.Tipo.PREPARAZIONE,
                "richiede_operatore_abilitato": True,
                "configurazione": {"usa_ricetta": True, "output_lottizzato": True},
            },
        )
        creati += nuovo
        _, nuovo = PassaggioLinea.objects.get_or_create(
            linea=linea_sl, stazione=stazione_sl,
            defaults={"ordine": 1, "durata_standard_minuti": 90},
        )
        creati += nuovo
        # Semilavorati è una linea autonoma, non una fase obbligatoria di Marmellate.
        # Eliminiamo soltanto eventuali collegamenti configurativi spuri non ancora usati.
        for intruso in PassaggioLinea.objects.filter(linea=linea, stazione=stazione_sl):
            if not intruso.fasi.exists():
                DipendenzaPassaggio.objects.filter(
                    Q(passaggio=intruso) | Q(predecessore=intruso),
                ).delete()
                intruso.delete()
        return linea, creati

    @staticmethod
    def _controllo(stazione, codice, nome, ordine, unita_misura, regole):
        _, nuovo = DefinizioneControllo.objects.get_or_create(
            stazione=stazione, codice=codice,
            defaults={
                "nome": nome,
                "tipo_dato": DefinizioneControllo.TipoDato.DECIMALE,
                "unita_misura": unita_misura, "regole": regole, "ordine": ordine,
            },
        )
        return int(nuovo)
