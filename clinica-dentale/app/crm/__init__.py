# -*- coding: utf-8 -*-
"""Chi fa il CRM per QUESTO cliente: il suo HubSpot, oppure la copia in casa.

Se manca il token di uno studio, quello studio scrive in locale e lo dice.
Gli altri continuano a lavorare: un cliente mal configurato non ferma nessuno.
"""
from app.crm.base import CRM
from app.crm.sqlite_crm import CrmLocale


def scegli_crm(cliente):
    """Ritorna (crm, nota). La nota si puo' loggare: non contiene segreti."""
    if not cliente.ha_hubspot:
        motivo = cliente.perche_niente_hubspot()
        return CrmLocale(cliente.slug, motivo), motivo
    try:
        from app.crm.hubspot import CrmHubspot
        return CrmHubspot(cliente), u"HubSpot v3 (token da %s)" % cliente.token_env
    except Exception as e:
        motivo = u"HubSpot non utilizzabile (%s): scrivo in locale" % type(e).__name__
        return CrmLocale(cliente.slug, motivo), motivo


__all__ = ["CRM", "CrmLocale", "scegli_crm"]
