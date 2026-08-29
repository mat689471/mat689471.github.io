# -*- coding: utf-8 -*-
"""SQLite: lo schema e le poche funzioni per leggerlo e scriverlo.

Solo la libreria standard. Una connessione per operazione, chiusa subito.

OGNI RIGA PORTA IL SUO CLIENTE. Non c'e' una tabella per studio: c'e' una
colonna 'cliente' su ogni tabella, e ogni interrogazione la filtra. Cosi' un
paziente dello Studio Rossi non puo' comparire nell'agenda, nel CRM o nella
coda del Centro Bianchi, nemmeno per sbaglio: non e' una promessa, e' una
clausola WHERE che il test di isolamento verifica.
"""
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from app import config

ORA = "strftime('%Y-%m-%dT%H:%M:%SZ','now')"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente          TEXT NOT NULL DEFAULT '',
    nome             TEXT,
    email            TEXT,
    telefono         TEXT,
    canale           TEXT NOT NULL,
    canale_id        TEXT,
    campagna         TEXT,
    stato            TEXT NOT NULL DEFAULT 'nuovo',
    tipo_trattamento TEXT,
    urgenza          TEXT,
    serve_umano      INTEGER NOT NULL DEFAULT 0,
    consenso         INTEGER NOT NULL DEFAULT 0,
    crm_contact_id   TEXT,
    crm_deal_id      TEXT,
    creato_il        TEXT NOT NULL DEFAULT (%(ora)s),
    aggiornato_il    TEXT NOT NULL DEFAULT (%(ora)s)
);
CREATE INDEX IF NOT EXISTS i_leads_cliente  ON leads(cliente, id);
CREATE INDEX IF NOT EXISTS i_leads_stato    ON leads(cliente, stato);
CREATE INDEX IF NOT EXISTS i_leads_telefono ON leads(cliente, telefono);

CREATE TABLE IF NOT EXISTS messaggi (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id   INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    ruolo     TEXT NOT NULL,
    testo     TEXT NOT NULL,
    extra     TEXT,
    creato_il TEXT NOT NULL DEFAULT (%(ora)s)
);
CREATE INDEX IF NOT EXISTS i_messaggi_lead ON messaggi(lead_id, id);

CREATE TABLE IF NOT EXISTS disponibilita (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente   TEXT NOT NULL DEFAULT '',
    inizio    TEXT NOT NULL,
    fine      TEXT NOT NULL,
    studio    TEXT,
    stato     TEXT NOT NULL DEFAULT 'libero',
    lead_id   INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    creato_il TEXT NOT NULL DEFAULT (%(ora)s)
);
CREATE INDEX IF NOT EXISTS i_disp ON disponibilita(cliente, stato, inizio);

CREATE TABLE IF NOT EXISTS crm_records (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente            TEXT NOT NULL DEFAULT '',
    lead_id            INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    email              TEXT,
    firstname          TEXT,
    lastname           TEXT,
    phone              TEXT,
    lifecyclestage     TEXT,
    hs_lead_status     TEXT,
    dealname           TEXT,
    pipeline           TEXT,
    dealstage          TEXT,
    amount             TEXT,
    closedate          TEXT,
    treatment_type     TEXT,
    urgency            TEXT,
    hubspot_contact_id TEXT,
    hubspot_deal_id    TEXT,
    sincronizzato      INTEGER NOT NULL DEFAULT 0,
    ultimo_errore      TEXT,
    creato_il          TEXT NOT NULL DEFAULT (%(ora)s),
    aggiornato_il      TEXT NOT NULL DEFAULT (%(ora)s)
);
CREATE INDEX IF NOT EXISTS i_crm_cliente ON crm_records(cliente, lead_id);
CREATE INDEX IF NOT EXISTS i_crm_sync    ON crm_records(cliente, sincronizzato);

CREATE TABLE IF NOT EXISTS coda_operatore (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente   TEXT NOT NULL DEFAULT '',
    lead_id   INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    motivo    TEXT NOT NULL,
    priorita  INTEGER NOT NULL DEFAULT 5,
    contesto  TEXT,
    stato     TEXT NOT NULL DEFAULT 'aperto',
    operatore TEXT,
    creato_il TEXT NOT NULL DEFAULT (%(ora)s),
    chiuso_il TEXT
);
CREATE INDEX IF NOT EXISTS i_coda ON coda_operatore(cliente, stato, priorita, creato_il);
""" % {"ora": ORA}

# Database nato prima dei clienti: si aggiunge la colonna invece di buttarlo.
DA_MIGRARE = ("leads", "disponibilita", "crm_records", "coda_operatore")


def connessione():
    percorso = config.DB_PATH
    cartella = os.path.dirname(percorso)
    if cartella:
        os.makedirs(cartella, exist_ok=True)
    conn = sqlite3.connect(percorso)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _migra(conn, predefinito):
    for tabella in DA_MIGRARE:
        colonne = {r["name"] for r in conn.execute("PRAGMA table_info(%s)" % tabella)}
        if not colonne or "cliente" in colonne:
            continue
        conn.execute("ALTER TABLE %s ADD COLUMN cliente TEXT NOT NULL DEFAULT ''"
                     % tabella)
        # Le righe di prima erano tutte di un solo studio: diventano sue.
        conn.execute("UPDATE %s SET cliente = ? WHERE cliente = ''" % tabella,
                     (predefinito,))


def prepara(clienti_config=None):
    """Crea le tabelle (si puo' richiamare sempre) e riempie l'agenda di ognuno."""
    from app import clienti as mod_clienti
    elenco = clienti_config or list(mod_clienti.tutti().values())
    pred = mod_clienti.predefinito()
    conn = connessione()
    try:
        conn.executescript(SCHEMA)
        _migra(conn, pred.slug if pred else "")
        for c in elenco:
            gia = conn.execute("SELECT COUNT(*) n FROM disponibilita WHERE cliente = ?",
                               (c.slug,)).fetchone()["n"]
            if gia:
                continue
            domani = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
                minute=0, second=0, microsecond=0)
            righe = []
            for giorno in range(c.giorni):
                for ora in c.ore:
                    inizio = domani.replace(hour=ora) + timedelta(days=giorno)
                    righe.append((c.slug,
                                  inizio.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  (inizio + timedelta(minutes=c.durata_min)
                                   ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                  c.studio, "libero"))
            conn.executemany("INSERT INTO disponibilita "
                             "(cliente,inizio,fine,studio,stato) VALUES (?,?,?,?,?)",
                             righe)
        conn.commit()
    finally:
        conn.close()


# ---- lead -----------------------------------------------------------------
CAMPI_LEAD = ("cliente", "nome", "email", "telefono", "canale", "canale_id",
              "campagna", "stato", "tipo_trattamento", "urgenza", "serve_umano",
              "consenso", "crm_contact_id", "crm_deal_id")


def crea_lead(dati):
    colonne = [c for c in CAMPI_LEAD if c in dati]
    if "canale" not in colonne:
        raise ValueError("un lead ha bisogno almeno del campo 'canale'")
    if not dati.get("cliente"):
        raise ValueError("un lead deve appartenere a un cliente")
    conn = connessione()
    try:
        cur = conn.execute(
            "INSERT INTO leads ({}) VALUES ({})".format(
                ", ".join(colonne), ", ".join("?" * len(colonne))),
            [dati[c] for c in colonne])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def leggi_lead(lead_id, cliente=None):
    """Con 'cliente' la lettura e' vincolata: un id di un altro studio non esce."""
    conn = connessione()
    try:
        if cliente:
            r = conn.execute("SELECT * FROM leads WHERE id = ? AND cliente = ?",
                             (lead_id, cliente)).fetchone()
        else:
            r = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def lead_per_telefono(telefono, cliente):
    """Il piu' recente con quel numero DENTRO quel cliente.

    Senza il filtro, due studi con lo stesso paziente si scambierebbero le
    conversazioni: e' il buco piu' facile da aprire in un sistema multi-cliente.
    """
    if not telefono or not cliente:
        return None
    conn = connessione()
    try:
        r = conn.execute("SELECT id FROM leads WHERE telefono = ? AND cliente = ? "
                         "ORDER BY id DESC LIMIT 1", (telefono, cliente)).fetchone()
        return r["id"] if r else None
    finally:
        conn.close()


def aggiorna_lead(lead_id, **campi):
    campi = {k: v for k, v in campi.items() if k in CAMPI_LEAD and k != "cliente"}
    if not campi:
        return
    conn = connessione()
    try:
        conn.execute("UPDATE leads SET {}, aggiornato_il = {} WHERE id = ?".format(
            ", ".join(k + " = ?" for k in campi), ORA),
            list(campi.values()) + [lead_id])
        conn.commit()
    finally:
        conn.close()


# ---- messaggi -------------------------------------------------------------
def aggiungi_messaggio(lead_id, ruolo, testo, extra=None):
    conn = connessione()
    try:
        cur = conn.execute("INSERT INTO messaggi (lead_id,ruolo,testo,extra) "
                           "VALUES (?,?,?,?)", (lead_id, ruolo, testo, extra))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def storico(lead_id):
    conn = connessione()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT ruolo, testo, creato_il FROM messaggi WHERE lead_id = ? "
            "ORDER BY id ASC", (lead_id,)).fetchall()]
    finally:
        conn.close()


# ---- coda operatore -------------------------------------------------------
def accoda_operatore(cliente, lead_id, motivo, priorita=5, contesto=None):
    conn = connessione()
    try:
        cur = conn.execute("INSERT INTO coda_operatore "
                           "(cliente,lead_id,motivo,priorita,contesto) "
                           "VALUES (?,?,?,?,?)",
                           (cliente, lead_id, motivo, priorita, contesto))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _filtro(cliente, prefisso=""):
    """(pezzo di WHERE, parametri) — vuoto se si guarda tutto."""
    if not cliente:
        return "", []
    return " AND {}cliente = ?".format(prefisso), [cliente]


def coda_aperta(cliente=None):
    dove, par = _filtro(cliente)
    conn = connessione()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM coda_operatore WHERE stato = 'aperto'" + dove +
            " ORDER BY priorita ASC, creato_il ASC", par).fetchall()]
    finally:
        conn.close()


def in_carico_a_operatore(lead_id):
    conn = connessione()
    try:
        r = conn.execute("SELECT 1 FROM coda_operatore WHERE lead_id = ? "
                         "AND stato IN ('aperto','preso') LIMIT 1",
                         (lead_id,)).fetchone()
        return r is not None
    finally:
        conn.close()


# ---- quello che serve al cruscotto ----------------------------------------
def elenco_leads(cliente=None, limite=100):
    dove, par = _filtro(cliente, "l.")
    conn = connessione()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT l.*,
                   (SELECT testo FROM messaggi m WHERE m.lead_id = l.id
                     AND m.ruolo = 'user' ORDER BY m.id DESC LIMIT 1) AS ultimo_messaggio,
                   (SELECT COUNT(*) FROM messaggi m WHERE m.lead_id = l.id) AS n_messaggi,
                   (SELECT inizio FROM disponibilita d WHERE d.lead_id = l.id
                     ORDER BY d.inizio ASC LIMIT 1) AS appuntamento
            FROM leads l WHERE 1=1""" + dove +
            " ORDER BY l.id DESC LIMIT ?", par + [limite]).fetchall()]
    finally:
        conn.close()


def agenda(cliente=None, quanti=20):
    dove, par = _filtro(cliente, "d.")
    conn = connessione()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT d.*, l.nome, l.telefono, l.tipo_trattamento
            FROM disponibilita d LEFT JOIN leads l ON l.id = d.lead_id
            WHERE d.stato = 'occupato'""" + dove +
            " ORDER BY d.inizio ASC LIMIT ?", par + [quanti]).fetchall()]
    finally:
        conn.close()


def numeri(cliente=None):
    dove, par = _filtro(cliente)
    conn = connessione()
    try:
        u = lambda q, p=None: conn.execute(q, p or par).fetchone()[0]
        return {
            "pazienti": u("SELECT COUNT(*) FROM leads WHERE 1=1" + dove),
            "prenotati": u("SELECT COUNT(*) FROM leads WHERE stato='prenotato'" + dove),
            "in_coda": u("SELECT COUNT(*) FROM coda_operatore WHERE stato='aperto'" + dove),
            "urgenti": u("SELECT COUNT(*) FROM coda_operatore WHERE stato='aperto' "
                         "AND priorita <= 2" + dove),
            "slot_liberi": u("SELECT COUNT(*) FROM disponibilita WHERE stato='libero'" + dove),
        }
    finally:
        conn.close()


def coda_con_nomi(cliente=None):
    dove, par = _filtro(cliente, "c.")
    conn = connessione()
    try:
        return [dict(r) for r in conn.execute("""
            SELECT c.*, l.nome, l.telefono, l.email, l.tipo_trattamento, l.urgenza
            FROM coda_operatore c JOIN leads l ON l.id = c.lead_id
            WHERE c.stato IN ('aperto','preso')""" + dove + """
            ORDER BY CASE c.stato WHEN 'preso' THEN 1 ELSE 0 END,
                     c.priorita ASC, c.creato_il ASC""", par).fetchall()]
    finally:
        conn.close()


def cancella_lead(lead_id):
    """Il paziente sparisce davvero: messaggi, coda, CRM locale, e il posto
    in agenda torna libero invece di restare occupato da un fantasma.

    Serve al diritto alla cancellazione: chi scrive del suo mal di denti lascia
    un dato di salute, e se chiede di essere cancellato non basta nasconderlo.
    """
    conn = connessione()
    try:
        conti = {}
        # Prima l'agenda: il posto si libera, non si cancella.
        cur = conn.execute("UPDATE disponibilita SET stato = 'libero', lead_id = NULL "
                           "WHERE lead_id = ?", (lead_id,))
        conti["posti_liberati"] = cur.rowcount
        for tabella in ("messaggi", "crm_records", "coda_operatore"):
            cur = conn.execute("DELETE FROM %s WHERE lead_id = ?" % tabella, (lead_id,))
            conti[tabella] = cur.rowcount
        cur = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
        conti["paziente"] = cur.rowcount
        conn.commit()
        return conti
    finally:
        conn.close()


def cambia_voce_coda(voce_id, stato, operatore=None):
    if stato not in ("aperto", "preso", "chiuso"):
        raise ValueError("stato non previsto: " + str(stato))
    conn = connessione()
    try:
        r = conn.execute("SELECT lead_id, cliente FROM coda_operatore WHERE id = ?",
                         (voce_id,)).fetchone()
        if not r:
            return None
        chiusura = ORA if stato == "chiuso" else "NULL"
        conn.execute("UPDATE coda_operatore SET stato = ?, operatore = ?, "
                     "chiuso_il = {} WHERE id = ?".format(chiusura),
                     (stato, operatore, voce_id))
        if stato == "chiuso":
            conn.execute("UPDATE leads SET stato = 'chiuso', aggiornato_il = {} "
                         "WHERE id = ?".format(ORA), (r["lead_id"],))
        conn.commit()
        return {"lead_id": r["lead_id"], "cliente": r["cliente"]}
    finally:
        conn.close()
