# -*- coding: utf-8 -*-
"""I clienti: uno studio dentistico ciascuno, ognuno chiuso in casa propria.

Un cliente e' un contenitore isolato. Ha il suo nome, i suoi orari, i suoi
trattamenti, la sua agenda, la sua coda operatore e - soprattutto - il SUO
token HubSpot.

Regola che non si piega: in clienti.json si scrive il NOME della variabile
d'ambiente che contiene il token, mai il token. Il file di configurazione si
puo' leggere, mandare per email, mettere in un repository: dentro non c'e'
niente di segreto. I valori veri stanno solo nell'ambiente - sul tuo computer
o fra i secret del provider quando e' online.
"""
import json
import os

from app import config

FILE = os.environ.get("CLIENTI_JSON", "").strip() or \
    os.path.join(config.RADICE, "clienti.json")

# Un token vero non finisce mai qui dentro. Se qualcuno lo incolla per sbaglio
# nel file di configurazione, ce ne accorgiamo all'avvio invece che mai.
INIZI_SOSPETTI = ("pat-", "sk-", "Bearer ", "pat_", "xoxb-", "ghp_")


class ConfigCliente(object):
    """Tutto quello che serve per servire UN cliente."""

    def __init__(self, dati):
        self.slug = str(dati["slug"]).strip().lower()
        self.nome = dati.get("nome") or self.slug
        self.token_env = (dati.get("hubspot_token_env") or "").strip()
        self.orari = dati.get("orari") or "lunedi-venerdi 9:00-19:00"
        self.indirizzo = dati.get("indirizzo") or ""
        self.trattamenti = list(dati.get("trattamenti") or [])
        self.prima_visita_gratuita = bool(dati.get("prima_visita_gratuita", True))
        self.canale = dict(dati.get("canale") or {"tipo": "console"})
        agenda = dict(dati.get("agenda") or {})
        self.ore = [int(o) for o in (agenda.get("ore") or [9, 15])]
        self.giorni = int(agenda.get("giorni") or 5)
        self.durata_min = int(agenda.get("durata_min") or 45)
        self.studio = agenda.get("studio") or "Studio 1"

    # -- il token, che sta solo nell'ambiente -------------------------------
    @property
    def hubspot_token(self):
        if not self.token_env:
            return ""
        return (os.environ.get(self.token_env) or "").strip()

    @property
    def ha_hubspot(self):
        return bool(self.hubspot_token)

    def perche_niente_hubspot(self):
        """Frase da mettere nel log e nel record locale. Mai il valore."""
        if not self.token_env:
            return u"nessun token HubSpot configurato per «%s»" % self.slug
        return (u"la variabile d'ambiente %s non e' impostata: il CRM di «%s» "
                u"non e' raggiungibile" % (self.token_env, self.slug))

    def pubblico(self):
        """Quello che si puo' mostrare: niente segreti, solo se ci sono."""
        return {"slug": self.slug, "nome": self.nome, "orari": self.orari,
                "indirizzo": self.indirizzo, "trattamenti": self.trattamenti,
                "prima_visita_gratuita": self.prima_visita_gratuita,
                "canale": self.canale.get("tipo", "console"),
                "hubspot": self.ha_hubspot,
                "hubspot_env": self.token_env or None}

    def __repr__(self):
        return "<Cliente %s>" % self.slug


class ErroreClienti(RuntimeError):
    pass


_registro = None
_predefinito = None


def _leggi():
    try:
        with open(FILE, encoding="utf-8") as f:
            dati = json.load(f)
    except OSError as e:
        raise ErroreClienti(u"non riesco a leggere %s: %s" % (FILE, e))
    except ValueError as e:
        raise ErroreClienti(u"%s non e' un JSON valido: %s" % (FILE, e))

    elenco = dati.get("clienti") or []
    if not elenco:
        raise ErroreClienti(u"in %s non c'e' nemmeno un cliente" % FILE)

    registro, visti = {}, set()
    for voce in elenco:
        if not voce.get("slug"):
            raise ErroreClienti(u"un cliente e' senza 'slug' in %s" % FILE)
        c = ConfigCliente(voce)
        if c.slug in visti:
            raise ErroreClienti(u"due clienti hanno lo stesso slug: %s" % c.slug)
        # Il controllo che salva la faccia: un token incollato nel file.
        for chiave, valore in voce.items():
            if isinstance(valore, str) and valore.startswith(INIZI_SOSPETTI):
                raise ErroreClienti(
                    u"in %s il campo '%s' del cliente '%s' sembra un segreto vero. "
                    u"Qui va SOLO il nome della variabile d'ambiente "
                    u"(es. HUBSPOT_TOKEN_%s), mai il token."
                    % (FILE, chiave, c.slug, c.slug.upper()))
        visti.add(c.slug)
        registro[c.slug] = c

    pred = (dati.get("predefinito") or "").strip().lower()
    if pred and pred not in registro:
        raise ErroreClienti(u"il cliente predefinito '%s' non esiste" % pred)
    return registro, (pred or None)


def ricarica():
    global _registro, _predefinito
    _registro, _predefinito = _leggi()
    return _registro


def tutti():
    if _registro is None:
        ricarica()
    return _registro


def cerca(slug):
    """Il cliente, o None. Nessuna eccezione: decide chi chiama."""
    if not slug:
        return predefinito()
    return tutti().get(str(slug).strip().lower())


def predefinito():
    if _registro is None:
        ricarica()
    if _predefinito:
        return _registro[_predefinito]
    return next(iter(_registro.values())) if _registro else None


def elenco_pubblico():
    return [c.pubblico() for c in tutti().values()]
