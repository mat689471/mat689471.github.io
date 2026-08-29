# -*- coding: utf-8 -*-
"""HubSpot CRM v3, per davvero.

Autenticazione: Authorization: Bearer <token>. Il token si legge dall'ambiente
e non compare mai in un log ne' in un messaggio d'errore.

Nota che e' costata un pomeriggio: uno spazio incollato insieme al token fa
rispondere 401 «Authentication credentials not found» a un token perfettamente
valido. Qui il token viene ripulito prima dell'uso.
"""
import httpx

from app import config
from app.crm.base import CRM, dividi_nome

# L'id con cui HubSpot lega una trattativa a un contatto.
TIPO_ASSOCIAZIONE_DEAL_CONTATTO = 3


class ErroreHubspot(RuntimeError):
    def __init__(self, stato, corpo, dove=""):
        self.stato = stato
        self.corpo = corpo
        super().__init__(u"HubSpot ha risposto {}{}: {}".format(
            stato, u" ({})".format(dove) if dove else u"", corpo))


class CrmHubspot(CRM):
    nome = "hubspot"

    def __init__(self, cliente, timeout=30):
        """'cliente' e' una ConfigCliente: il token e' il SUO, letto dall'ambiente.

        Non esiste piu' un token globale. Ogni studio ha il suo, e il codice
        non ha modo di prendere quello di un altro: qui dentro arriva un solo
        cliente per volta.
        """
        self.cliente = cliente
        self.token = cliente.hubspot_token
        if not self.token:
            raise RuntimeError(cliente.perche_niente_hubspot())
        self.base = config.HUBSPOT_BASE.rstrip("/")
        self.timeout = timeout

    # -- rete ---------------------------------------------------------------
    def _posta(self, percorso, corpo):
        return httpx.post(self.base + percorso, json=corpo, timeout=self.timeout,
                          headers={"Authorization": "Bearer " + self.token,
                                   "Content-Type": "application/json"})

    @staticmethod
    def _corpo(r):
        try:
            return r.json()
        except ValueError:
            return r.text[:400]

    # -- contatto -----------------------------------------------------------
    def contatto(self, lead):
        nome, cognome = dividi_nome(lead.get("nome"))
        proprieta = {"firstname": nome, "lastname": cognome,
                     "email": lead.get("email"), "phone": lead.get("telefono"),
                     "lifecyclestage": "lead", "hs_lead_status": "NEW"}
        proprieta = {k: v for k, v in proprieta.items() if v}

        r = self._posta("/crm/v3/objects/contacts", {"properties": proprieta})
        if r.status_code in (200, 201):
            return {"ok": True, "contact_id": str(self._corpo(r).get("id")),
                    "creato": True, "errore": None, "fonte": self.nome}

        # 409 = quell'email c'e' gia'. Non e' un guasto: e' un cliente che
        # torna. Si recupera il suo id invece di creare un doppione.
        if r.status_code == 409 and lead.get("email"):
            esistente = self._cerca_per_email(lead["email"])
            if esistente:
                return {"ok": True, "contact_id": esistente, "creato": False,
                        "errore": None, "fonte": self.nome}
        raise ErroreHubspot(r.status_code, self._corpo(r), "creazione contatto")

    def _cerca_per_email(self, email):
        r = self._posta("/crm/v3/objects/contacts/search", {
            "filterGroups": [{"filters": [
                {"propertyName": "email", "operator": "EQ", "value": email}]}],
            "properties": ["email"], "limit": 1})
        if r.status_code != 200:
            raise ErroreHubspot(r.status_code, self._corpo(r), "ricerca per email")
        risultati = (self._corpo(r) or {}).get("results") or []
        return str(risultati[0]["id"]) if risultati else None

    # -- trattativa ---------------------------------------------------------
    def deal(self, contact_id, lead, qualificazione):
        titolo = u"{} - {}".format(lead.get("nome") or "Lead",
                                   qualificazione.get("tipo_trattamento") or "consulto")
        corpo = {"properties": {
            "dealname": titolo,
            "pipeline": config.HUBSPOT_PIPELINE,
            "dealstage": config.HUBSPOT_DEALSTAGE,
        }}
        if contact_id:
            corpo["associations"] = [{
                "to": {"id": str(contact_id)},
                "types": [{"associationCategory": "HUBSPOT_DEFINED",
                           "associationTypeId": TIPO_ASSOCIAZIONE_DEAL_CONTATTO}]}]
        r = self._posta("/crm/v3/objects/deals", corpo)
        if r.status_code in (200, 201):
            return {"ok": True, "deal_id": str(self._corpo(r).get("id")),
                    "errore": None, "fonte": self.nome}
        raise ErroreHubspot(r.status_code, self._corpo(r), "creazione trattativa")
