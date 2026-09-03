from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone


class CalendarioLinea:
    def __init__(self, linea):
        self.linea = linea

    @property
    def configurato(self):
        return self.linea.turni.filter(attivo=True).exists()

    def normalizza(self, istante):
        if not self.configurato:
            return istante
        finestra = self._finestra_successiva(istante)
        return finestra[0]

    def aggiungi_minuti(self, istante, minuti):
        if minuti <= 0:
            raise ValidationError("La durata pianificata deve essere positiva.")
        if not self.configurato:
            return istante + timedelta(minutes=minuti)
        residui = minuti
        cursore = istante
        while residui > 0:
            inizio, fine = self._finestra_successiva(cursore)
            cursore = max(cursore, inizio)
            disponibili = int((fine - cursore).total_seconds() // 60)
            if residui <= disponibili:
                return cursore + timedelta(minutes=residui)
            residui -= disponibili
            cursore = fine + timedelta(microseconds=1)
        return cursore

    def _finestra_successiva(self, istante):
        zona = timezone.get_current_timezone()
        locale = timezone.localtime(istante, zona)
        for distanza in range(15):
            giorno = locale.date() + timedelta(days=distanza)
            turni = self.linea.turni.filter(
                attivo=True, giorno_settimana=giorno.weekday(),
            ).order_by("ora_inizio")
            for turno in turni:
                inizio = timezone.make_aware(datetime.combine(giorno, turno.ora_inizio), zona)
                fine = timezone.make_aware(datetime.combine(giorno, turno.ora_fine), zona)
                if locale <= fine:
                    return max(locale, inizio), fine
        raise ValidationError("Nessun turno attivo trovato nei prossimi 15 giorni.")
