/**
 * ruflo-bridge.mjs
 * -------------------------------------------------------------
 * Ponte tra l'attività reale sul tuo PC e il mondo "L'Ecosistema".
 *
 * Due sorgenti, in ordine di priorità:
 *
 *  1) mondo/live.json  — scritto dall'ORCHESTRATORE (agente.py --mondo).
 *     È lo stato vivo e completo dell'ecosistema: agenti creati al volo,
 *     chat della Sala Comando, avanzamenti, anteprime, richieste di
 *     autorizzazione, passaggi di lavoro fra agenti, resoconti.
 *     Quando è presente e recente, comanda lui.
 *
 *  2) agent_log.txt + memoria/memoria.json — l'attività grezza di agente.py
 *     usata in assenza dell'orchestratore, per non lasciare il mondo muto.
 *
 * Il risultato viene scritto in mondo/state.json, l'unico file che la
 * pagina legge.
 *
 * USO: normalmente parte da solo tramite mondo/avvia.mjs
 * (doppio clic su AVVIA-WINDOWS.bat, oppure  node mondo/avvia.mjs).
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
const REPO_ROOT = path.join(__dirname, "..", "..");
const OUTPUT    = path.join(__dirname, "..", "state.json");
const LIVE_FILE = path.join(__dirname, "..", "live.json");
const LOG_FILE  = path.join(REPO_ROOT, "agent_log.txt");
const MEM_FILE  = path.join(REPO_ROOT, "memoria", "memoria.json");
const INTERVALLO_MS = 900;
const LIVE_MAX_ETA_MS = 15000; // oltre questo, live.json è considerato vecchio

const MESHY_API_KEY = process.env.MESHY_API_KEY || null;

// ---- utilità --------------------------------------------------------------
function accorcia(s, n = 64) { s = (s || "").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

function parseRiga(l) {
  const parts = l.split("\t");
  if (parts.length < 2) return null;
  const get = (k) => { const p = parts.find(x => x.startsWith(k + "=")); return p ? p.slice(k.length + 1) : null; };
  return { ts: parts[0], rc: get("RC"), comando: get("comando") || "" };
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
async function leggiLive() {
  try {
    const dati = JSON.parse(await readFile(LIVE_FILE, "utf8"));
    // _epoch è una marca assoluta in ms: non dipende dal fuso orario.
    const marca = Number(dati._epoch) || Date.parse(dati._generatoIl || 0);
    const eta = Date.now() - marca;
    if (Number.isFinite(eta) && eta <= LIVE_MAX_ETA_MS) return dati;
    return { ...dati, _stantio: true };
  } catch { return null; }
}

// ---- costruzione dello stato per il mondo ---------------------------------
async function leggiStato() {
  const live = await leggiLive();

  // 1) Orchestratore attivo: lo stato vivo comanda.
  if (live && !live._stantio) {
    const righe = await leggiLog();
    const ok = righe.filter(r => r.rc === "0").length;
    return {
      ...live,
      orchestratore: true,
      stats: { ...(live.stats || {}), comandi: righe.length, riusciti: ok },
      _fonte: `orchestratore attivo (${(live.agents || []).length} agenti, ${righe.length} comandi)`,
    };
  }

  // 2) Nessun orchestratore: mostriamo l'attività grezza di agente.py.
  const righe = await leggiLog();
  const memoria = await leggiMemoria();
  const factCount = memoria && memoria.fatti ? Object.keys(memoria.fatti).length : 0;
  const totale = righe.length;
  const ok = righe.filter(r => r.rc === "0").length;
  const now = Date.now();
  const last = righe[righe.length - 1];
  const lastAge = last ? (now - Date.parse(last.ts)) / 1000 : Infinity;

  const events = righe.slice(-8).reverse().map((r, i) => ({
    ts: r.ts + "#" + (totale - i),
    who: "agente.py",
    color: r.rc === "0" ? "#4ce0a5" : (r.rc ? "#ff9f6b" : "#8a96b3"),
    msg: (r.rc === "0" ? "✓ " : (r.rc ? "✗ " : "")) + accorcia(r.comando) + (r.rc && r.rc !== "0" ? " (RC=" + r.rc + ")" : ""),
  }));
  events.push({
    ts: "hint",
    who: "bridge",
    color: "#f5b942",
    msg: live ? "orchestratore fermo — riavvia: python agente.py --mondo"
              : "avvia l'ecosistema con: python agente.py --mondo",
  });

  return {
    orchestratore: false,
    boss: { id: "boss", name: "Orchestratore", status: "idle", task: null },
    agents: [{
      id: "code", role: "code", name: "Sviluppatore",
      status: lastAge < 8 ? "working" : "idle",
      task: lastAge < 45 ? accorcia(last.comando) : null,
      progress: lastAge < 8 ? Math.min(0.95, lastAge / 8) : 0,
      color: "#35d0d6",
    }],
    chat: [], handoffs: [], pending: null, fullaccess: false, report: null,
    stats: { done: ok, messages: 0, comandi: totale, riusciti: ok },
    events,
    _fonte: totale ? `agent_log.txt (${totale} comandi, ${factCount} fatti)`
                   : "in attesa — avvia python agente.py --mondo",
  };
}

// (Facoltativo) generazione avatar Meshy — da completare quando crei un agente.
// async function generaAvatarMeshy(descrizione){ if(!MESHY_API_KEY) return null; /* POST text-to-3d, attendi, ritorna URL .glb */ }

async function ciclo() {
  try {
    const stato = await leggiStato();
    stato._aggiornatoIl = new Date().toISOString();
    await writeFile(OUTPUT, JSON.stringify(stato, null, 2), "utf8");
    process.stdout.write(`\r[${new Date().toLocaleTimeString()}] ${stato._fonte}                    `);
  } catch (e) {
    console.error("\nErrore:", e.message);
  }
}

console.log("ruflo-bridge avviato.");
console.log("Stato vivo dell'ecosistema:", LIVE_FILE);
console.log("Attività grezza:", LOG_FILE);
console.log("Scrivo lo stato in:", OUTPUT);
console.log("Meshy:", MESHY_API_KEY ? "chiave rilevata ✓" : "nessuna chiave (avatar 3D segnaposto)");
console.log("");
await ciclo();
setInterval(ciclo, INTERVALLO_MS);
