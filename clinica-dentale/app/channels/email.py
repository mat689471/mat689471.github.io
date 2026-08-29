# -*- coding: utf-8 -*-
"""Il canale email: la risposta al paziente parte davvero.

Fino a ieri il sistema capiva, prenotava e scriveva sul CRM - e poi stampava
la risposta su un file di log. Il paziente non riceveva niente. Questo e' il
pezzo che chiude il giro.

## Chi manda, e da dove

Il server SMTP e' **uno solo, globale**: e' l'infrastruttura di chi fa girare
il servizio, come la chiave Anthropic. Non e' una scorciatoia, e' l'unica cosa
che si puo' fare all'inizio - mandare come la clinica richiederebbe il SUO
dominio, con SPF e DKIM configurati da loro, e non si chiede a un cliente di
toccare i DNS prima ancora di aver firmato.

Quello che cambia per cliente e' come la mail SI PRESENTA:

  - il **nome** del mittente e' quello della clinica, cosi' nella posta si
    legge «Clinica Estetica Aurora» e non il tuo indirizzo;
  - il **rispondi-a** e' la casella della clinica, cosi' se il paziente
    risponde la mail arriva a loro, non a te.

Questa e' la strada onesta finche' non c'e' un contratto. Col primo cliente
che paga si passa al suo dominio, e la cosa migliora da sola.

## Cosa non fa

Non promette la consegna. Se il server SMTP rifiuta, torna ok=False con il
motivo: non si finge di aver mandato qualcosa. Chi chiama questo canale
decide cosa fare - e in app/main.py, se la risposta non parte, il paziente
passa a una persona invece di restare in silenzio.
"""
import os
import smtplib
import ssl
import uuid
from email.headerregistry import Address
from email.message import EmailMessage

from app.channels.base import Canale

# Il server di posta di chi fa girare il servizio. Solo dall'ambiente.
HOST = (os.environ.get("SMTP_HOST") or "").strip()
PORTA = int((os.environ.get("SMTP_PORT") or "587").strip() or 587)
UTENTE = (os.environ.get("SMTP_USER") or "").strip()
PAROLA = os.environ.get("SMTP_PASSWORD") or ""
MITTENTE = (os.environ.get("SMTP_FROM") or UTENTE or "").strip()
# In prova si punta a un finto server che non parla TLS.
SENZA_TLS = (os.environ.get("SMTP_SENZA_TLS") or "").strip().lower() in ("1", "si", "true", "yes")


class CanaleEmail(Canale):
    """Manda la risposta per email, a nome della clinica."""

    nome = "email"

    def __init__(self, cliente=None, config_canale=None):
        self.cliente = cliente or "-"
        self.config = dict(config_canale or {})

    # -- come si presenta questa clinica ------------------------------------
    @property
    def nome_mittente(self):
        return (self.config.get("nome_mittente") or self.cliente).strip()

    @property
    def rispondi_a(self):
        return (self.config.get("rispondi_a") or "").strip()

    @property
    def oggetto(self):
        return (self.config.get("oggetto") or u"La sua richiesta").strip()

    def _perche_non_posso(self):
        """Cosa manca, detto per nome. Mai un valore, solo il nome."""
        for chiave, valore in (("SMTP_HOST", HOST), ("SMTP_USER", UTENTE),
                               ("SMTP_PASSWORD", PAROLA), ("SMTP_FROM", MITTENTE)):
            if not valore:
                return u"manca %s: non posso mandare email (non fingo di averlo fatto)" % chiave
        return None

    def _messaggio(self, destinatario, testo):
        m = EmailMessage()
        m["Subject"] = self.oggetto
        utente, dominio = MITTENTE.rsplit("@", 1)
        m["From"] = Address(self.nome_mittente, utente, dominio)
        m["To"] = destinatario
        if self.rispondi_a:
            m["Reply-To"] = self.rispondi_a
        m.set_content(testo)
        return m

    def invia(self, destinatario, testo):
        esito = {"ok": False, "canale": self.nome, "cliente": self.cliente,
                 "destinatario": destinatario, "id_messaggio": None,
                 "errore": None, "simulato": False, "testo": testo}

        manca = self._perche_non_posso()
        if manca:
            esito["errore"] = manca
            return esito

        if "@" not in (destinatario or ""):
            # Il lead e' arrivato col telefono ma senza email: non e' un
            # guasto, e' un dato che non c'e'. Va detto chiaro.
            esito["errore"] = u"«%s» non e' un indirizzo email" % destinatario
            return esito

        try:
            messaggio = self._messaggio(destinatario, testo)
            if SENZA_TLS:
                with smtplib.SMTP(HOST, PORTA, timeout=20) as posta:
                    posta.send_message(messaggio)
            else:
                with smtplib.SMTP(HOST, PORTA, timeout=20) as posta:
                    posta.starttls(context=ssl.create_default_context())
                    posta.login(UTENTE, PAROLA)
                    posta.send_message(messaggio)
        except Exception as e:
            # Il motivo si logga, la parola d'ordine no: smtplib non la mette
            # mai nel testo dell'errore, ma il tipo lo diciamo comunque a parte.
            esito["errore"] = u"%s: %s" % (type(e).__name__, e)
            return esito

        esito["ok"] = True
        esito["id_messaggio"] = uuid.uuid4().hex
        return esito
