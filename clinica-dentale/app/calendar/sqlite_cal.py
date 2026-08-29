# -*- coding: utf-8 -*-
"""Calendario sulla tabella 'disponibilita'. UNA agenda per cliente.

Il cliente si passa al costruttore e non si puo' dimenticare: ogni query lo
porta dentro. Lo Studio Rossi non vede - e non puo' occupare - un posto del
Centro Bianchi.

Domani Google Calendar entra da qui: una classe con le stesse due firme.
"""
import sqlite3

from app import db
from app.calendar.base import Calendario


class CalendarioSqlite(Calendario):

    def __init__(self, cliente):
        if not cliente:
            raise ValueError("il calendario ha bisogno di sapere di quale cliente e'")
        self.cliente = cliente

    @staticmethod
    def _fascia(preferenza):
        if not preferenza:
            return None
        p = preferenza.lower()
        if "mattin" in p:
            return "mattina"
        if "pomerigg" in p or "sera" in p:
            return "pomeriggio"
        return None

    @staticmethod
    def _ora(inizio):
        try:
            return int(inizio.split("T", 1)[1][:2])
        except (IndexError, ValueError, AttributeError):
            return None

    def slot_libero(self, preferenza=None, urgenza=None):
        # Chi ha un'emergenza prende il primo posto che c'e', non quello che
        # preferisce: la fascia conta solo quando si puo' scegliere.
        fascia = None if urgenza == "emergenza" else self._fascia(preferenza)
        conn = db.connessione()
        try:
            righe = conn.execute(
                "SELECT * FROM disponibilita WHERE stato = 'libero' AND cliente = ? "
                "ORDER BY inizio ASC", (self.cliente,)).fetchall()
        finally:
            conn.close()
        ripiego = None
        for r in righe:
            voce = {"slot_id": r["id"], "inizio": r["inizio"],
                    "fine": r["fine"], "studio": r["studio"]}
            if fascia:
                ora = self._ora(r["inizio"])
                if ora is not None:
                    giusta = (ora < 13) if fascia == "mattina" else (ora >= 13)
                    if not giusta:
                        # Se la fascia preferita non c'e', meglio proporre
                        # qualcosa che dire "niente": si tiene il primo libero.
                        ripiego = ripiego or voce
                        continue
            return voce
        return ripiego

    def prenota(self, slot_id, lead_id):
        conn = db.connessione()
        try:
            r = conn.execute("SELECT * FROM disponibilita WHERE id = ? AND cliente = ?",
                             (slot_id, self.cliente)).fetchone()
            if r is None:
                return {"ok": False, "slot_id": slot_id, "inizio": None, "fine": None,
                        "errore": u"questo posto non esiste per %s" % self.cliente}
            if r["stato"] != "libero":
                if r["lead_id"] == lead_id:
                    return {"ok": True, "slot_id": slot_id, "inizio": r["inizio"],
                            "fine": r["fine"], "errore": None}
                return {"ok": False, "slot_id": slot_id, "inizio": r["inizio"],
                        "fine": r["fine"], "errore": "posto gia' occupato da un altro"}
            try:
                conn.execute("UPDATE disponibilita SET stato='occupato', lead_id=? "
                             "WHERE id = ? AND stato = 'libero' AND cliente = ?",
                             (lead_id, slot_id, self.cliente))
                conn.commit()
            except sqlite3.IntegrityError as e:
                conn.rollback()
                return {"ok": False, "slot_id": slot_id, "inizio": r["inizio"],
                        "fine": r["fine"],
                        "errore": u"non posso prenotare per il lead %s (%s)" % (lead_id, e)}
            return {"ok": True, "slot_id": slot_id, "inizio": r["inizio"],
                    "fine": r["fine"], "errore": None}
        finally:
            conn.close()
