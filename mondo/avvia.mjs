/**
 * avvia.mjs — Avvio a un clic del mondo "L'Ecosistema".
 *
 * Fa tre cose insieme:
 *   1) accende il "ponte" verso ruflo (aggiorna state.json);
 *   2) avvia un piccolo server web locale (nessuna dipendenza da installare);
 *   3) apre il mondo nel browser, già collegato.
 *
 * USO:
 *   - Windows: doppio clic su  AVVIA-WINDOWS.bat  (nella stessa cartella)
 *              oppure da PowerShell:   node mondo/avvia.mjs
 *   - Mac/Linux:                       node mondo/avvia.mjs
 *
 * Per fermare tutto: chiudi la finestra o premi Ctrl+C.
 */

import http from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import { Cassaforte } from "./vault.mjs";
import { Registro } from "./ledger.mjs";
import { Strumenti } from "./strumenti.mjs";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { exec } from "node:child_process";
import path from "node:path";

const ROOT = path.dirname(fileURLToPath(import.meta.url)); // cartella mondo/
const PORT_BASE = 5178;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml", ".gif": "image/gif", ".webp": "image/webp",
  ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
  ".ico": "image/x-icon", ".woff2": "font/woff2",
};

const JSONH = { "Content-Type": "application/json" };
const INBOX = path.join(ROOT, "inbox.json");
const DATI = path.join(ROOT, "..", "dati");   // cassaforte + contabilità (fuori da git)

const cassaforte = new Cassaforte(DATI);
const registro = new Registro(DATI);
const strumenti = new Strumenti(path.join(ROOT, ".."));

function json(res, code, obj) { res.writeHead(code, JSONH); res.end(JSON.stringify(obj)); }
function leggiCorpo(req) {
  return new Promise((ris, rif) => {
    let b = "";
    req.on("data", c => { b += c; if (b.length > 200000) { req.destroy(); rif(new Error("troppo grande")); } });
    req.on("end", () => { try { ris(JSON.parse(b || "{}")); } catch (e) { rif(e); } });
    req.on("error", rif);
  });
}
/** Le API scrivono e leggono segreti: accettiamo solo richieste dal PC stesso. */
function daLocale(req) {
  const a = req.socket.remoteAddress || "";
  return a === "127.0.0.1" || a === "::1" || a === "::ffff:127.0.0.1";
}

// Coda dei comandi dalla pagina: append serializzato per non perdere voci.
let codaInbox = Promise.resolve();
function appendInbox(voce) {
  codaInbox = codaInbox.then(async () => {
    let items = [];
    try { items = JSON.parse(await readFile(INBOX, "utf8")).items || []; } catch { /* prima voce */ }
    items.push(voce);
    if (items.length > 200) items = items.slice(-200);
    await writeFile(INBOX, JSON.stringify({ items }, null, 2), "utf8");
  }).catch(() => {});
  return codaInbox;
}

const server = http.createServer(async (req, res) => {
  try {
    // API: la Sala Comando invia qui messaggi, approvazioni e interruttori.
    // Tutto finisce in inbox.json, che l'Orchestratore (agente.py --mondo) legge.
    const apiPath = req.url.split("?")[0];
    if (req.method === "POST" && (apiPath === "/api/control" || apiPath === "/api/objective")) {
      let body = "";
      req.on("data", (c) => { body += c; if (body.length > 200000) req.destroy(); });
      req.on("end", async () => {
        try {
          const p = JSON.parse(body || "{}");
          const type = String(p.type || "message");
          const voce = { id: Date.now(), type, ts: new Date().toISOString() };
          if (type === "message") {
            voce.text = String(p.text || "").slice(0, 2000).trim();
            if (!voce.text) { res.writeHead(400, JSONH); return res.end('{"ok":false,"err":"vuoto"}'); }
          } else if (type === "fullaccess" || type === "agente_personale") {
            voce.value = !!p.value;
          } else if (type === "riprendi" || type === "elimina_sessione") {
            // 'id' è il numero d'ordine nella coda: il lavoro da riprendere va
            // in un campo suo, altrimenti l'ordine dei messaggi si rompe.
            voce.sessione = String(p.id || p.sessione || "");
            if (!voce.sessione) { res.writeHead(400, JSONH); return res.end('{"ok":false,"err":"id"}'); }
          } else if (type !== "approve" && type !== "deny" && type !== "nuova_sessione") {
            res.writeHead(400, JSONH); return res.end('{"ok":false,"err":"tipo"}');
          }
          await appendInbox(voce);
          console.log(`\n[mondo] ${type}${voce.text ? ": " + voce.text : ""}${voce.value !== undefined ? ": " + voce.value : ""}`);
          res.writeHead(200, JSONH); res.end('{"ok":true}');
        } catch (e) { res.writeHead(500, JSONH); res.end('{"ok":false}'); }
      });
      return;
    }

    // ---- CASSAFORTE -------------------------------------------------------
    // Solo dal PC stesso: qui passano credenziali.
    if (apiPath.startsWith("/api/vault") || apiPath === "/api/secret") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });

      if (apiPath === "/api/vault" && req.method === "GET")
        return json(res, 200, cassaforte.elenco());

      // Valore in chiaro: lo usa solo l'ecosistema locale per costruire
      // l'ambiente dei comandi. Gli agenti non lo vedono mai.
      if (apiPath === "/api/secret" && req.method === "GET") {
        const nome = new URL(req.url, "http://x").searchParams.get("nome");
        if (nome) {
          const v = cassaforte.valore(nome);
          return v === null ? json(res, 404, { ok: false }) : json(res, 200, { ok: true, valore: v });
        }
        return json(res, 200, { ok: true, ambiente: cassaforte.ambiente() });
      }

      if (apiPath === "/api/vault" && req.method === "POST") {
        const p = await leggiCorpo(req);
        try {
          switch (p.azione) {
            case "imposta":   return json(res, 200, await cassaforte.imposta(p.nome, p.valore, { tipo: p.tipo, note: p.note }));
            case "rimuovi":   return json(res, 200, await cassaforte.rimuovi(p.nome));
            case "sblocca":   return json(res, 200, await cassaforte.sblocca(p.passphrase));
            case "chiudi":    cassaforte.chiudi(); return json(res, 200, { ok: true });
            case "passphrase":return json(res, 200, await cassaforte.impostaPassphrase(p.passphrase || null));
            default:          return json(res, 400, { ok: false, errore: "azione sconosciuta" });
          }
        } catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      return json(res, 405, { ok: false });
    }

    // ---- STRUMENTI: competenze (Skill) e server MCP -----------------------
    // Accendere un MCP significa dare nuovi poteri agli agenti: solo da qui.
    if (apiPath === "/api/strumenti") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      if (req.method === "GET")
        return json(res, 200, { ok: true, server: await strumenti.server(), competenze: await strumenti.competenze() });
      if (req.method === "POST") {
        const p = await leggiCorpo(req);
        try {
          switch (p.azione) {
            case "accendi": return json(res, 200, await strumenti.accendi(p.id, p.attivo));
            case "aggiungi": return json(res, 200, await strumenti.aggiungi(p));
            case "rimuovi":  return json(res, 200, await strumenti.rimuovi(p.id));
            default:         return json(res, 400, { ok: false, errore: "azione sconosciuta" });
          }
        } catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      return json(res, 405, { ok: false });
    }

    // ---- PROGETTI E CONTABILITÀ ------------------------------------------
    if (apiPath.startsWith("/api/progetti")) {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      if (req.method === "GET") return json(res, 200, registro.vista());
      if (req.method === "POST") {
        const p = await leggiCorpo(req);
        try {
          switch (p.azione) {
            case "crea":       return json(res, 200, await registro.creaProgetto(p));
            case "aggiorna":   return json(res, 200, await registro.aggiornaProgetto(p.id, p));
            case "elimina":    return json(res, 200, await registro.eliminaProgetto(p.id));
            case "movimento":  return json(res, 200, await registro.aggiungiMovimento(p));
            case "delMovimento": return json(res, 200, await registro.eliminaMovimento(p.id));
            default:           return json(res, 400, { ok: false, errore: "azione sconosciuta" });
          }
        } catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      return json(res, 405, { ok: false });
    }

    let urlPath = decodeURIComponent(req.url.split("?")[0]);
    if (urlPath === "/") urlPath = "/index.html";

    // Gli avatar 3D stanno in <progetto>/avatar/, fuori da mondo/: li serviamo
    // da lì così il visore può caricarli.
    let base = ROOT;
    if (urlPath.startsWith("/avatar/")) {
      base = path.join(ROOT, "..", "avatar");
      urlPath = urlPath.slice("/avatar".length);
    }

    // impedisci di uscire dalla cartella
    const filePath = path.normalize(path.join(base, urlPath));
    if (!filePath.startsWith(path.normalize(base))) { res.writeHead(403); return res.end("Vietato"); }

    if (!existsSync(filePath)) { res.writeHead(404); return res.end("Non trovato"); }
    const data = await readFile(filePath);
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream", "Cache-Control": "no-store" });
    res.end(data);
  } catch (e) {
    res.writeHead(500); res.end("Errore: " + e.message);
  }
});

function apriBrowser(url) {
  const cmd = process.platform === "win32" ? `start "" "${url}"`
            : process.platform === "darwin" ? `open "${url}"`
            : `xdg-open "${url}"`;
  exec(cmd, () => {});
}

function ascolta(port) {
  server.once("error", (err) => {
    if (err.code === "EADDRINUSE" && port < PORT_BASE + 10) ascolta(port + 1);
    else { console.error("Impossibile avviare il server:", err.message); process.exit(1); }
  });
  server.listen(port, "127.0.0.1", async () => {
    const url = `http://localhost:${port}/`;
    await cassaforte.init();
    await registro.init();
    console.log("\n===============================================");
    console.log("  L'Ecosistema è in funzione!");
    console.log("  Mondo:          " + url);
    console.log("  Quartier Gen.:  " + url + "gestione.html");
    console.log("  Cassaforte: " + (cassaforte.conPassphrase
      ? (cassaforte.sbloccata ? "aperta" : "chiusa — sbloccala dal Quartier Generale")
      : "attiva (senza passphrase)"));
    console.log("  (per fermare: chiudi questa finestra o Ctrl+C)");
    console.log("===============================================\n");

    // Accendi il ponte verso ruflo (scrive state.json in questa cartella)
    try {
      await import("./bridge/ruflo-bridge.mjs");
    } catch (e) {
      console.warn("Nota: il ponte ruflo non è partito (" + e.message + ").");
      console.warn("Il mondo funzionerà comunque in modalità demo.");
    }

    setTimeout(() => apriBrowser(url), 800);
  });
}

ascolta(PORT_BASE);
