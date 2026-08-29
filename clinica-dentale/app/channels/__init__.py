# -*- coding: utf-8 -*-
"""Quale canale usa QUESTO cliente.

Stessa forma di scegli_crm: torna (canale, nota). La nota si puo' mettere nel
diario perche' non contiene segreti - solo il NOME delle variabili, mai il
valore.

La regola: non si ripiega mai in silenzio su un canale che non manda niente.
Se un cliente e' configurato per l'email e l'email non e' pronta, il sistema
lo dice e il paziente passa a una persona. Un messaggio che il paziente crede
di aver ricevuto e non ha ricevuto e' peggio di nessun messaggio.
"""
from app.channels.base import Canale
from app.channels.console import CanaleConsole


def scegli_canale(cliente):
    """Ritorna (canale, nota)."""
    config = dict(getattr(cliente, "canale", None) or {})
    tipo = (config.get("tipo") or "console").strip().lower()
    slug = getattr(cliente, "slug", "-")

    if tipo == "email":
        from app.channels.email import CanaleEmail
        return CanaleEmail(slug, config), u"email (server SMTP globale)"

    if tipo == "whatsapp":
        from app.channels.whatsapp import CanaleWhatsapp
        canale = CanaleWhatsapp(slug, config)
        return canale, u"WhatsApp Cloud API (numero %s, token da %s)" % (
            canale.id_numero or "non configurato",
            canale.token_env or "non configurato")

    if tipo != "console":
        # Un tipo scritto male non deve diventare un invio finto senza che
        # nessuno se ne accorga: si usa la console, ma il diario lo grida.
        return CanaleConsole(slug, config), (
            u"canale «%s» sconosciuto per «%s»: uso la console, che NON manda "
            u"niente. I tipi validi sono console, email, whatsapp." % (tipo, slug))

    return CanaleConsole(slug, config), u"console (simulato: non manda niente)"


__all__ = ["Canale", "CanaleConsole", "scegli_canale"]
