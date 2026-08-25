/**
 * ruflo-bridge.mjs
 * -------------------------------------------------------------
 * Ponte tra l'attività reale sul tuo PC e il mondo "L'Ecosistema".
 *
 * Il browser NON può leggere direttamente ciò che accade sul PC:
 * questo script legge l'attività reale e scrive un file `state.json`
 * che la pagina del mondo poi visualizza (agenti, task, eventi).
 *
 * COSA LEGGE ORA (dati reali del tuo agente.py):
 *   - agent_log.txt        -> ogni comando eseguito diventa un evento reale
 *   - memoria/memoria.json -> i "fatti" memorizzati dall'agente
 * Entrambi sono cercati nella cartella del sito (accanto ad agente.py).
 * Se non esistono ancora, il mondo resta collegato ma "in attesa":
 * avvia agente.py e vedrai comparire l'attività vera in tempo reale.
 *
 * COME SI USA: normalmente parte da solo tramite  mondo/avvia.mjs
 * (doppio clic su AVVIA-WINDOWS.bat, oppure  node mondo/avvia.mjs).
 *
 * -------------------------------------------------------------
 * COLLEGARE ANCHE ruflo (plugin/MCP) — passo successivo:
 *   Se in futuro ruflo espone lo stato della sua "swarm" (es. un comando
 *   che stampa JSON, o il server MCP claude-flow), basta aggiungere qui
 *   la lettura e unirla al risultato di leggiStato(). Il formato da
 *   produrre è quello di state.example.json.
 *
 * AVATAR MESHY (sicurezza): la chiave API Meshy NON va mai nella pagina.
 *   La generazione avviene QUI, con la chiave in una variabile d'ambiente
 *   (process.env.MESHY_API_KEY). Il ponte scrive solo l'URL del .glb in
 *   state.json; la pagina legge l'URL, mai la chiave.
 * -------------------------------------------------------------
 */

import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, "..", "..");            // dove sta agente.py
const OUTPUT    = path.join(__dirname, "..", "state.json");    // -> mondo/state.json
const LOG_FILE  = path.join(REPO_ROOT, "agent_log.txt");
const MEM_FILE  = path.join(REPO_ROOT, "memoria", "memoria.json");
const INTERVALLO_MS = 1500;

const MESHY_API_KEY = process.env.MESHY_API_KEY || null;

// ---- lettura file reali ---------------------------------------------------
function accorcia(s, n = 64) { s = (s || "").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

function parseRiga(l) {
  const parts = l.split("\t");
  if (parts.length < 2) return null;
  const get = (k) => { const p = parts.find(x => x.startsWith(k + "=")); return p ? p.slice(k.length + 1) : null; };
  return { ts: parts[0], rc: get("RC"), distruttivo: get("distruttivo"), confermato: get("confermato"), comando: get("comando") || "" };
}

async function leggiLog() {
  try {
    const txt = await readFile(LOG_FILE, "utf8");
    return txt.split(/\r?\n/).filter(Boolean).map(parseRiga).filter(Boolean);
  } catch { return []; }
}
async function leggiMemoria() {
  try { return JSON.parse(await readFile(MEM_FILE, "utf8")); } catch { return null; }
}

// ---- costruzione dello stato per il mondo --------------------------------
async function leggiStato() {
  const righe = await leggiLog();
  const memoria = await leggiMemoria();
  const factCount = memoria && memoria.fatti ? Object.keys(memoria.fatti).length : 0;

  const totale = righe.length;
  const ok = righe.filter(r => r.rc === "0").length;
  const now = Date.now();
  const last = righe[righe.length - 1];
  const lastAge = last ? (now - Date.parse(last.ts)) / 1000 : Infinity;
  const lastErr = [...righe].reverse().find(r => r.rc && r.rc !== "0");
  const errAge = lastErr ? (now - Date.parse(lastErr.ts)) / 1000 : Infinity;

  // Sviluppatore = l'esecutore dei comandi (agente.py)
  const sviluppatore = {
    id: "sviluppatore", role: "code", name: "Sviluppatore",
    status: lastAge < 8 ? "working" : "idle",
    task: lastAge < 45 ? accorcia(last.comando) : null,
    progress: lastAge < 8 ? Math.min(0.95, lastAge / 8) : (lastAge < 45 ? 1 : 0),
  };
  // Tester = reagisce agli errori (RC diverso da 0)
  const tester = {
    id: "tester", role: "qa", name: "Tester",
    status: errAge < 10 ? "talking" : "idle",
    message: errAge < 10 ? ("errore RC=" + lastErr.rc) : null,
  };
  // Documentatore = memoria/fatti salvati
  const documentatore = {
    id: "documentatore", role: "docs", name: "Documentatore",
    status: "idle", task: factCount > 0 ? (factCount + " fatti in memoria") : null,
  };

  const events = righe.slice(-8).reverse().map(r => ({
    who: "agente.py",
    color: r.rc === "0" ? "#4ce0a5" : (r.rc ? "#ff9f6b" : "#8a96b3"),
    msg: (r.rc === "0" ? "✓ " : (r.rc ? "✗ " : "")) + accorcia(r.comando) + (r.rc && r.rc !== "0" ? " (RC=" + r.rc + ")" : ""),
  }));
  if (totale === 0) {
    events.push({ who: "bridge", color: "#f5b942", msg: "in attesa — avvia agente.py per vedere l'attività reale" });
  }

  return {
    boss: { id: "boss", name: "Orchestratore", status: "coordina" },
    agents: [sviluppatore, tester, documentatore],
    queue: [],
    stats: { done: ok, messages: totale },
    events,
    _fonte: totale ? ("agent_log.txt (" + totale + " comandi, " + factCount + " fatti)") : "in attesa di attività da agente.py",
  };
}

// (Facoltativo) generazione avatar Meshy — da completare quando crei un agente.
// async function generaAvatarMeshy(descrizione){ if(!MESHY_API_KEY) return null; /* POST text-to-3d, attendi, ritorna URL .glb */ }

async function ciclo() {
  try {
    const stato = await leggiStato();
    stato._generatoIl = new Date().toISOString();
    await writeFile(OUTPUT, JSON.stringify(stato, null, 2), "utf8");
    process.stdout.write(`\r[${new Date().toLocaleTimeString()}] ${stato._fonte}      `);
  } catch (e) {
    console.error("\nErrore:", e.message);
  }
}

console.log("ruflo-bridge avviato.");
console.log("Leggo l'attività da:", LOG_FILE);
console.log("Scrivo lo stato in:", OUTPUT);
console.log("Meshy:", MESHY_API_KEY ? "chiave rilevata ✓" : "nessuna chiave (avatar 3D segnaposto)");
console.log("");
await ciclo();
setInterval(ciclo, INTERVALLO_MS);
