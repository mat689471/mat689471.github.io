# -*- coding: utf-8 -*-
"""Configurazione. I segreti si leggono SOLO dall'ambiente, mai dal codice.

Se una chiave manca non si finge: si dice quale manca e cosa succede senza.
"""
import os

# --- L'unico segreto globale ------------------------------------------------
# La chiave Anthropic e' UNA SOLA: e' il costo di chi fa girare il servizio,
# non del singolo studio. I token HubSpot invece sono uno per cliente e stanno
# in app/clienti.py, letti dall'ambiente col nome scritto in clienti.json.
ANTHROPIC_API_KEY = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()

# --- Modello -----------------------------------------------------------------
# Nomi validi, scritti esatti e senza date in coda: claude-opus-5,
# claude-sonnet-5, claude-haiku-4-5. Un 404 dall'API significa nome sbagliato,
# non chiave sbagliata (401 = chiave, 403 = permessi, 429 = troppo traffico).
MODELLO = os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-sonnet-5"

# --- Percorsi: ancorati al file, non alla cartella da cui lanci il comando ---
RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DB_PATH", "").strip() or os.path.join(RADICE, "dati", "clinica.db")

# --- HubSpot -----------------------------------------------------------------
HUBSPOT_PIPELINE = os.environ.get("HUBSPOT_PIPELINE", "").strip() or "default"
HUBSPOT_DEALSTAGE = os.environ.get("HUBSPOT_DEALSTAGE", "").strip() or "appointmentscheduled"
# Serve ai test: puntando altrove si prova il client senza toccare HubSpot vero.
HUBSPOT_BASE = os.environ.get("HUBSPOT_BASE", "").strip() or "https://api.hubapi.com"


def diagnosi():
    """Cosa c'e' e cosa manca, senza mai mostrare un valore.

    Del CRM non si parla qui: non e' piu' una cosa sola. Ogni cliente ha il suo,
    e chi vuole saperlo guarda /health o /api/clienti.
    """
    return {
        "anthropic": bool(ANTHROPIC_API_KEY),
        "modello": MODELLO,
        "db": DB_PATH,
    }
