from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from .models import DefinizioneControllo, RilevazioneControllo


class ValutatoreControllo:
    """Valuta un controllo usando regole dichiarative salvate sulla definizione."""

    def __init__(self, definizione, regole=None):
        self.definizione = definizione
        self.regole = definizione.regole if regole is None else regole

    def valuta(self, valore):
        tipo = self.definizione.tipo_dato
        if tipo == DefinizioneControllo.TipoDato.DECIMALE:
            return self._valuta_decimale(valore)
        if tipo == DefinizioneControllo.TipoDato.INTERO:
            try:
                valore = int(valore)
            except (TypeError, ValueError) as errore:
                raise ValidationError("Il valore deve essere un numero intero.") from errore
            return self._valuta_numero(Decimal(valore))
        if tipo == DefinizioneControllo.TipoDato.BOOLEANO:
            if not isinstance(valore, bool):
                raise ValidationError("Il valore deve essere booleano.")
            atteso = self.definizione.regole.get("atteso", True)
            return (
                RilevazioneControllo.Esito.CONFORME
                if valore == atteso else RilevazioneControllo.Esito.NON_CONFORME
            )
        if valore in (None, ""):
            raise ValidationError("Il valore del controllo è obbligatorio.")
        return RilevazioneControllo.Esito.CONFORME

    def _valuta_decimale(self, valore):
        try:
            numero = Decimal(str(valore).replace(",", "."))
        except (InvalidOperation, TypeError, ValueError) as errore:
            raise ValidationError("Il valore deve essere un numero decimale.") from errore
        return self._valuta_numero(numero)

    def _valuta_numero(self, numero):
        regole = self.regole
        minimo_fisico = self._decimale(regole.get("minimo_fisico"))
        massimo_fisico = self._decimale(regole.get("massimo_fisico"))
        if minimo_fisico is not None and numero < minimo_fisico:
            raise ValidationError("Valore inferiore al minimo fisicamente ammesso.")
        if massimo_fisico is not None and numero > massimo_fisico:
            raise ValidationError("Valore superiore al massimo fisicamente ammesso.")

        minimo = self._decimale(regole.get("conforme_min"))
        massimo = self._decimale(regole.get("conforme_max"))
        conforme = ((minimo is None or numero >= minimo) and
                    (massimo is None or numero <= massimo))
        if conforme:
            return RilevazioneControllo.Esito.CONFORME

        allerta_min = self._decimale(regole.get("allerta_min_escluso"))
        allerta_max = self._decimale(regole.get("allerta_max"))
        if (allerta_min is not None and numero > allerta_min and
                allerta_max is not None and numero <= allerta_max):
            return RilevazioneControllo.Esito.ALLERTA
        return RilevazioneControllo.Esito.NON_CONFORME

    @staticmethod
    def _decimale(valore):
        return None if valore is None else Decimal(str(valore))
