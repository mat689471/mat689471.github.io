# -*- coding: utf-8 -*-
"""Il CRM di scorta, in casa, separato per cliente.

Se HubSpot non c'e' o non risponde, il lead NON si perde: finisce qui, in
'crm_records', con i nomi di colonna identici a quelli che HubSpot si aspetta
e sincronizzato=0. Il giorno che il CRM torna, il travaso e' una copia.
"""
from app import config, db
from app.crm.base import CRM, dividi_nome


class CrmLocale(CRM):
    nome = "sqlite"

    def __init__(self, cliente, motivo=None):
        if not cliente:
            raise ValueError("il CRM locale ha bisogno di sapere di quale cliente e'")
        self.cliente = cliente
        self.motivo = motivo or "HubSpot non configurato"

    def contatto(self, lead):
        nome, cognome = dividi_nome(lead.get("nome"))
        conn = db.connessione()
        try:
            riga = None
            if lead.get("email"):
                riga = conn.execute(
                    "SELECT id FROM crm_records WHERE email = ? AND cliente = ? "
                    "ORDER BY id DESC LIMIT 1",
                    (lead["email"], self.cliente)).fetchone()
            if riga:
                rec = riga["id"]
                conn.execute(
                    "UPDATE crm_records SET firstname=?, lastname=?, phone=?, "
                    "lifecyclestage='lead', hs_lead_status='NEW', lead_id=?, "
                    "sincronizzato=0, ultimo_errore=?, aggiornato_il={} "
                    "WHERE id=?".format(db.ORA),
                    (nome, cognome, lead.get("telefono"), lead.get("id"),
                     self.motivo, rec))
                creato = False
            else:
                cur = conn.execute(
                    "INSERT INTO crm_records (cliente,lead_id,email,firstname,lastname,"
                    "phone,lifecyclestage,hs_lead_status,sincronizzato,ultimo_errore) "
                    "VALUES (?,?,?,?,?,?,'lead','NEW',0,?)",
                    (self.cliente, lead.get("id"), lead.get("email"), nome, cognome,
                     lead.get("telefono"), self.motivo))
                rec = cur.lastrowid
                creato = True
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "contact_id": "locale:%d" % rec, "creato": creato,
                "errore": None, "fonte": self.nome}

    def deal(self, contact_id, lead, qualificazione):
        rec = None
        if isinstance(contact_id, str) and contact_id.startswith("locale:"):
            try:
                rec = int(contact_id.split(":", 1)[1])
            except ValueError:
                rec = None
        titolo = u"{} - {}".format(lead.get("nome") or "Lead",
                                   qualificazione.get("tipo_trattamento") or "consulto")
        conn = db.connessione()
        try:
            esiste = rec is not None and conn.execute(
                "SELECT 1 FROM crm_records WHERE id = ? AND cliente = ?",
                (rec, self.cliente)).fetchone()
            if esiste:
                conn.execute(
                    "UPDATE crm_records SET dealname=?, pipeline=?, dealstage=?, "
                    "treatment_type=?, urgency=?, sincronizzato=0, ultimo_errore=?, "
                    "aggiornato_il={} WHERE id=?".format(db.ORA),
                    (titolo, config.HUBSPOT_PIPELINE, config.HUBSPOT_DEALSTAGE,
                     qualificazione.get("tipo_trattamento"),
                     qualificazione.get("urgenza"), self.motivo, rec))
            else:
                cur = conn.execute(
                    "INSERT INTO crm_records (cliente,lead_id,dealname,pipeline,"
                    "dealstage,treatment_type,urgency,sincronizzato,ultimo_errore) "
                    "VALUES (?,?,?,?,?,?,?,0,?)",
                    (self.cliente, lead.get("id"), titolo, config.HUBSPOT_PIPELINE,
                     config.HUBSPOT_DEALSTAGE, qualificazione.get("tipo_trattamento"),
                     qualificazione.get("urgenza"), self.motivo))
                rec = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        return {"ok": True, "deal_id": "locale:%d" % rec, "errore": None,
                "fonte": self.nome}
