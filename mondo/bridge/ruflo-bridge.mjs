/**
 * ruflo-bridge.mjs
 * -------------------------------------------------------------
 * Ponte tra ruflo (sul tuo PC) e il mondo "L'Ecosistema".
 *
 * Il browser NON può leggere direttamente lo stato di ruflo:
 * questo script legge lo stato reale degli agenti e scrive un file
 * `state.json` che la pagina del mondo poi legge e visualizza.
 *
 * COME SI USA (Windows / Mac / Linux, serve Node.js 18+):
 *
 *   1) Apri un terminale nella cartella del sito.
 *   2) Lancia:   node mondo/bridge/ruflo-bridge.mjs
 *   3) Apri la pagina del mondo (mondo/index.html) da un piccolo server
 *      locale, ad esempio:   npx serve .   oppure:   python -m http.server
 *      e vai su  http://localhost:3000/mondo/  (o la porta indicata).
 *
 * Il mondo, in modalità "auto", rileva state.json e passa da solo ai
 * dati reali (il badge in alto diventa verde "collegato a ruflo").
 *
 * -------------------------------------------------------------
 * DA PERSONALIZZARE:
 *   La funzione leggiStatoRuflo() qui sotto è uno STUB con dati finti.
 *   Sostituiscila con la lettura reale del tuo ruflo. Le opzioni tipiche:
 *     - eseguire un comando ruflo che stampa lo stato in JSON
 *       (es. `npx ruflo status --json`) e fare il parse dell'output;
 *     - leggere un file di stato/log che ruflo/agente.py già scrivono
 *       (es. la cartella memoria/ del tuo agente.py);
 *     - interrogare il server MCP di ruflo (claude-flow).
 *   L'importante è restituire un oggetto nel formato di state.example.json.
 *
 *   AVATAR MESHY (importante per la sicurezza):
 *   NON mettere mai la tua chiave API Meshy nella pagina web.
 *   La generazione degli avatar 3D va fatta QUI (lato "server"/PC), dove
 *   la chiave sta in una variabile d'ambiente (process.env.MESHY_API_KEY).
 *   Il bridge poi scrive solo l'URL del file .glb dentro state.json:
 *   la pagina legge l'URL, non la chiave.
 * -------------------------------------------------------------
 */

import { writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUTPUT = path.join(__dirname, "..", "state.json"); // -> mondo/state.json
const INTERVALLO_MS = 2000;

// Chiave Meshy (facoltativa): impostala come variabile d'ambiente, MAI nel codice.
//   Windows PowerShell:  $env:MESHY_API_KEY="la-tua-chiave"
//   Mac/Linux:           export MESHY_API_KEY="la-tua-chiave"
const MESHY_API_KEY = process.env.MESHY_API_KEY || null;

// ------------------------------------------------------------------
// STUB: sostituisci con la lettura reale dello stato di ruflo.
// Deve restituire un oggetto nel formato di state.example.json.
// ------------------------------------------------------------------
let _demoTick = 0;
async function leggiStatoRuflo() {
  // >>> QUI colleghi ruflo davvero. <<<
  // Esempio (da adattare): eseguire un comando e leggerne l'output JSON:
  //
  //   import { execFile } from "node:child_process";
  //   const out = await new Promise((res, rej) =>
  //     execFile("npx", ["ruflo", "status", "--json"], (e, so) => e ? rej(e) : res(so)));
  //   return mappaVersoFormatoMondo(JSON.parse(out));
  //
  // Per ora restituiamo dati dimostrativi che cambiano nel tempo:
  _demoTick++;
  const p = (Math.sin(_demoTick / 6) + 1) / 2;
  return {
    boss: { id: "boss", name: "Orchestratore", status: "coordina" },
    agents: [
      { id: "sviluppatore", name: "Sviluppatore", role: "code",     status: "working", task: "Refactor del modulo auth", progress: p },
      { id: "tester",       name: "Tester",       role: "qa",       status: "idle",    task: null, progress: 0 },
      { id: "architetto",   name: "Architetto",   role: "design",   status: "working", task: "Diagramma componenti", progress: (p + .4) % 1 },
      { id: "ricercatore",  name: "Ricercatore",  role: "research", status: "talking", task: null, message: "trovato un edge case" },
      { id: "revisore",     name: "Revisore",     role: "review",   status: "idle",    task: null, progress: 0 },
      { id: "documentatore",name: "Documentatore",role: "docs",     status: "working", task: "Aggiorna README", progress: (p + .7) % 1 },
    ],
    queue: ["Scrivi i test unitari", "Configura la pipeline CI", "Ottimizza le query"],
    stats: { done: 10 + (_demoTick % 20), messages: 25 + _demoTick },
    events: [{ who: "bridge", color: "#4ce0a5", msg: "stato aggiornato #" + _demoTick }],
  };
}

// ------------------------------------------------------------------
// (Facoltativo) Genera un avatar 3D con Meshy e restituisce l'URL .glb.
// Da chiamare quando crei un nuovo agente. Esempio di scheletro:
// ------------------------------------------------------------------
// async function generaAvatarMeshy(descrizione) {
//   if (!MESHY_API_KEY) return null;
//   // 1) POST alla API Meshy (text-to-3d) con Authorization: Bearer MESHY_API_KEY
//   // 2) attendi il completamento del task
//   // 3) restituisci l'URL del file .glb prodotto
//   return "https://.../avatar.glb";
// }

async function ciclo() {
  try {
    const stato = await leggiStatoRuflo();
    stato._generatoIl = new Date().toISOString();
    await writeFile(OUTPUT, JSON.stringify(stato, null, 2), "utf8");
    process.stdout.write(`\r[${new Date().toLocaleTimeString()}] state.json aggiornato  `);
  } catch (e) {
    console.error("\nErrore nell'aggiornamento:", e.message);
  }
}

console.log("ruflo-bridge avviato.");
console.log("Scrivo lo stato in:", OUTPUT);
console.log("Meshy:", MESHY_API_KEY ? "chiave rilevata ✓" : "nessuna chiave (avatar 3D disabilitati)");
console.log("Premi Ctrl+C per fermare.\n");
await ciclo();
setInterval(ciclo, INTERVALLO_MS);
