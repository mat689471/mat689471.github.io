# -*- coding: utf-8 -*-
"""Il contratto di un canale di uscita. Non importa nient'altro dell'app.

Domani WhatsApp o l'SMS entrano scrivendo una classe con questa stessa firma:
il resto del programma non cambia di una riga.
"""
from abc import ABC, abstractmethod


class Canale(ABC):
    nome = "astratto"

    @abstractmethod
    def invia(self, destinatario, testo):
        """Manda un messaggio di testo. Ritorna sempre lo stesso dizionario:

        {"ok": bool, "canale": str, "destinatario": str,
         "id_messaggio": str|None, "errore": str|None, "simulato": bool}
        """
        raise NotImplementedError
