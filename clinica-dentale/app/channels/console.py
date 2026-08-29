# -*- coding: utf-8 -*-
"""Canale di prova: non manda niente a nessuno, scrive a schermo e su file.

Ogni messaggio porta il marchio [SIMULATO] e il dizionario ha simulato=True:
cosi' non puo' capitare di credere che sia partito un SMS vero.
"""
import os
import uuid
from datetime import datetime, timezone

from app import config
from app.channels.base import Canale

MARCHIO = "[SIMULATO - canale di prova, non e' un SMS o WhatsApp vero]"
_FILE = os.path.join(config.RADICE, "dati", "messaggi-inviati.log")


class CanaleConsole(Canale):
    """Canale finto, ma gia' intestato a un cliente.

    Il giorno che si innesta WhatsApp o l'SMS, ogni studio avra' il suo numero
    e le sue credenziali: la configurazione per-cliente c'e' gia' (campo
    'canale' in clienti.json), qui la si porta dentro fin da adesso cosi' il
    passaggio non tocca il resto del programma.
    """
    nome = "console"

    def __init__(self, cliente=None, config_canale=None):
        self.cliente = cliente or "-"
        self.config = dict(config_canale or {})

    def invia(self, destinatario, testo):
        ora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        corpo = u"{} {}".format(MARCHIO, testo)
        riga = u"[{}] [{}] -> {} | {}".format(ora, self.cliente, destinatario, corpo)
        print(riga)
        errore = None
        try:
            os.makedirs(os.path.dirname(_FILE), exist_ok=True)
            with open(_FILE, "a", encoding="utf-8") as f:
                f.write(riga + "\n")
        except OSError as e:
            # Un problema di disco non deve far fallire l'invio simulato,
            # ma nemmeno passare sotto silenzio.
            errore = str(e)
        return {"ok": True, "canale": self.nome, "cliente": self.cliente,
                "destinatario": destinatario, "id_messaggio": uuid.uuid4().hex,
                "errore": errore, "simulato": True, "testo": corpo}
