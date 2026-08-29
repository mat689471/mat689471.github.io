# -*- coding: utf-8 -*-
"""Il canale WhatsApp, pronto ma spento finche' non c'e' un cliente vero.

Parla con la **Cloud API di Meta**. E' scritto per intero e provato contro un
finto Meta che risponde come quello vero: il giorno che arriva un cliente si
riempiono due campi e parte, senza toccare il resto del programma.

## Perche' e' spento

Non per pigrizia: perche' **non e' roba tua**. Per mandare un messaggio
WhatsApp servono un numero verificato, un'azienda verificata da Meta e dei
modelli approvati - e tutte e tre le cose sono intestate **alla clinica**, non
a chi costruisce il sistema. Non si puo' fare prima di avere un cliente, e
provarci a nome di nessuno e' tempo buttato.

## La regola delle 24 ore, che decide tutto

Meta lascia scrivere **testo libero solo entro 24 ore** dall'ultimo messaggio
mandato dal paziente. Fuori da quella finestra passano soltanto i **modelli
approvati** in anticipo.

Per noi non e' un dettaglio, e' il caso normale:

  - il paziente ci ha scritto **su WhatsApp** -> siamo dentro la finestra,
    si risponde con il testo che ha scritto il modello. Perfetto;
  - il lead e' arrivato **da un modulo o da una campagna Meta** -> il paziente
    non ci ha mai scritto su WhatsApp, la finestra **non e' mai stata aperta**,
    e il testo libero viene rifiutato. Serve un modello approvato.

Quindi in `clienti.json` si scrive il nome del modello di quella clinica. Se
non c'e', questo canale **lo dice** invece di provarci e fallire in silenzio:
meglio un errore chiaro che un paziente convinto di aver ricevuto risposta.
"""
import os
import re

import httpx

from app.channels.base import Canale

BASE = (os.environ.get("WHATSAPP_BASE") or "").strip() or "https://graph.facebook.com"
VERSIONE = (os.environ.get("WHATSAPP_VERSIONE") or "").strip() or "v21.0"


def numero_pulito(grezzo):
    """Da «+39 340 1122334» a «393401122334»: Meta vuole solo cifre.

    Un numero italiano scritto senza prefisso (comincia per 3 e ha 9-10 cifre)
    prende il 39 davanti. Non si indovina oltre: se non torna, si dice.
    """
    cifre = re.sub(r"\D", "", grezzo or "")
    if not cifre:
        return ""
    if cifre.startswith("00"):
        cifre = cifre[2:]
    if cifre.startswith("3") and len(cifre) in (9, 10):
        cifre = "39" + cifre
    return cifre


class CanaleWhatsapp(Canale):
    """Manda la risposta su WhatsApp, col numero e il token DI QUESTA clinica."""

    nome = "whatsapp"

    def __init__(self, cliente=None, config_canale=None):
        self.cliente = cliente or "-"
        self.config = dict(config_canale or {})

    # -- le credenziali di QUESTA clinica -----------------------------------
    @property
    def id_numero(self):
        """L'identificativo del numero. Non e' un segreto: sta in chiaro."""
        return str(self.config.get("id_numero") or "").strip()

    @property
    def token_env(self):
        """Il NOME della variabile col token. Mai il token."""
        return (self.config.get("token_env") or "").strip()

    @property
    def token(self):
        if not self.token_env:
            return ""
        return (os.environ.get(self.token_env) or "").strip()

    @property
    def modello(self):
        """Il modello approvato, per quando la finestra di 24 ore e' chiusa."""
        return (self.config.get("modello") or "").strip()

    @property
    def lingua_modello(self):
        return (self.config.get("lingua_modello") or "it").strip()

    def _perche_non_posso(self, dentro_finestra):
        if not self.id_numero:
            return (u"manca «id_numero» nel canale di «%s»: e' il numero WhatsApp "
                    u"della clinica, lo da' Meta" % self.cliente)
        if not self.token_env:
            return (u"manca «token_env» nel canale di «%s»: qui va il NOME della "
                    u"variabile d'ambiente col token, mai il token" % self.cliente)
        if not self.token:
            return (u"la variabile %s non e' impostata: il WhatsApp di «%s» non e' "
                    u"raggiungibile" % (self.token_env, self.cliente))
        if not dentro_finestra and not self.modello:
            return (u"il paziente non ci ha scritto su WhatsApp nelle ultime 24 ore "
                    u"e «%s» non ha un modello approvato: Meta rifiuterebbe il testo "
                    u"libero. Configura «modello» nel canale." % self.cliente)
        return None

    def _corpo(self, a, testo, dentro_finestra):
        if dentro_finestra:
            return {"messaging_product": "whatsapp", "to": a, "type": "text",
                    "text": {"body": testo, "preview_url": False}}
        return {"messaging_product": "whatsapp", "to": a, "type": "template",
                "template": {"name": self.modello,
                             "language": {"code": self.lingua_modello},
                             "components": [{"type": "body", "parameters": [
                                 {"type": "text", "text": testo}]}]}}

    def invia(self, destinatario, testo, dentro_finestra=False):
        """Manda il messaggio.

        `dentro_finestra` dice se il paziente ci ha scritto su WhatsApp nelle
        ultime 24 ore. Chi chiama lo sa - noi non lo indoviniamo, perche'
        indovinarlo male vuol dire un messaggio rifiutato da Meta e un paziente
        che non riceve niente.
        """
        esito = {"ok": False, "canale": self.nome, "cliente": self.cliente,
                 "destinatario": destinatario, "id_messaggio": None,
                 "errore": None, "simulato": False, "testo": testo}

        manca = self._perche_non_posso(dentro_finestra)
        if manca:
            esito["errore"] = manca
            return esito

        a = numero_pulito(destinatario)
        if not a:
            esito["errore"] = u"«%s» non e' un numero di telefono" % destinatario
            return esito
        esito["destinatario"] = a

        indirizzo = "%s/%s/%s/messages" % (BASE.rstrip("/"), VERSIONE, self.id_numero)
        try:
            risposta = httpx.post(
                indirizzo,
                headers={"Authorization": "Bearer %s" % self.token,
                         "Content-Type": "application/json"},
                json=self._corpo(a, testo, dentro_finestra),
                timeout=20.0)
        except Exception as e:
            esito["errore"] = u"%s: %s" % (type(e).__name__, e)
            return esito

        if risposta.status_code >= 400:
            # L'errore di Meta si riporta com'e': dice cosa correggere meglio
            # di qualunque frase che potrei inventare io.
            dettaglio = ""
            try:
                dettaglio = (risposta.json().get("error") or {}).get("message") or ""
            except Exception:
                dettaglio = (risposta.text or "")[:200]
            esito["errore"] = u"Meta ha rifiutato (HTTP %d): %s" % (
                risposta.status_code, dettaglio)
            return esito

        try:
            messaggi = risposta.json().get("messages") or []
            esito["id_messaggio"] = (messaggi[0] or {}).get("id")
        except Exception:
            pass
        esito["ok"] = True
        return esito
