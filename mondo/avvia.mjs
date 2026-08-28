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
import { Account } from "./account.mjs";
import { Pagamenti } from "./pagamenti.mjs";
import { Negozio } from "./negozio.mjs";
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
  // I lavori consegnati dagli agenti: senza il tipo giusto il browser non
  // riproduce un audio e non mostra un video, li fa scaricare e basta.
  ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
  ".pdf": "application/pdf",
  ".txt": "text/plain; charset=utf-8", ".md": "text/plain; charset=utf-8",
  ".csv": "text/csv; charset=utf-8",
};

const JSONH = { "Content-Type": "application/json" };
const INBOX = path.join(ROOT, "inbox.json");
const DATI = path.join(ROOT, "..", "dati");   // cassaforte + contabilità (fuori da git)

const cassaforte = new Cassaforte(DATI);
const registro = new Registro(DATI);
const strumenti = new Strumenti(path.join(ROOT, ".."));
const account = new Account(DATI);
// La funzione, non i valori: le chiavi restano in Cassaforte fino alla chiamata.
const pagamenti = new Pagamenti((nome) => cassaforte.valore(nome));
const negozio = new Negozio(DATI, (nome) => cassaforte.valore(nome));

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
            // Un incarico serio si scrive per esteso: 2000 caratteri tagliavano
            // a meta' le richieste vere, e il taglio non si vedeva.
            voce.text = String(p.text || "").slice(0, 20000).trim();
            if (!voce.text) { res.writeHead(400, JSONH); return res.end('{"ok":false,"err":"vuoto"}'); }
          } else if (type === "fullaccess" || type === "agente_personale" || type === "posta_libera") {
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

    // ---- NEGOZIO: Etsy e stampa su richiesta ------------------------------
    if (apiPath === "/negozio/entra") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      try {
        res.writeHead(302, { Location: negozio.urlAccesso() });
        return res.end();
      } catch (e) { return paginaEsito(res, false, e.message); }
    }
    if (apiPath === "/negozio/callback") {
      const q = new URL(req.url, "http://x").searchParams;
      if (q.get("error")) return paginaEsito(res, false, spiegaRifiuto(q));
      try {
        const r = await negozio.completa(q.get("code"), q.get("state"));
        console.log(`\n[mondo] negozio Etsy collegato: ${r.negozio}`);
        return paginaEsito(res, true, "Negozio «" + r.negozio + "» collegato");
      } catch (e) { return paginaEsito(res, false, e.message); }
    }
    if (apiPath === "/api/negozio" || apiPath === "/api/negozio/foto") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      if (apiPath === "/api/negozio/foto" && req.method === "GET") {
        const q = new URL(req.url, "http://x").searchParams;
        try {
          return json(res, 200, { ok: true, foto: await negozio.fotografia({
            giorni: Math.min(90, Math.max(1, Number(q.get("giorni")) || 30)),
            forza: q.get("forza") === "1",
          }) });
        } catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      if (req.method === "GET") return json(res, 200, negozio.vista());
      if (req.method === "POST") {
        const p = await leggiCorpo(req);
        try {
          switch (p.azione) {
            case "configura": return json(res, 200, await negozio.configura(p.keystring, p.secret));
            case "esci":      return json(res, 200, await negozio.esci());
            default:          return json(res, 400, { ok: false, errore: "azione sconosciuta" });
          }
        } catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      return json(res, 405, { ok: false });
    }

    // ---- OFFERTE: prodotti, abbonamenti e link creati dagli agenti --------
    if (apiPath === "/api/offerte") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      if (req.method === "GET") return json(res, 200, { ok: true, fornitori: pagamenti.quali() });
      if (req.method === "POST") {
        const p = await leggiCorpo(req);
        try { return json(res, 200, await pagamenti.crea(p)); }
        catch (e) { return json(res, 400, { ok: false, errore: e.message }); }
      }
      return json(res, 405, { ok: false });
    }

    // ---- ACCOUNT DI POSTA: «Accedi con Google / Outlook» ------------------
    // Qui passano permessi di accesso alla posta: solo dal PC stesso.
    if (apiPath === "/oauth/avvia") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      try {
        const p = new URL(req.url, "http://x").searchParams.get("fornitore");
        res.writeHead(302, { Location: account.urlAccesso(p) });
        return res.end();
      } catch (e) { return paginaEsito(res, false, e.message); }
    }

    // Dove il fornitore ci rimanda dopo che hai scelto l'account.
    if (apiPath === "/oauth/callback") {
      const q = new URL(req.url, "http://x").searchParams;
      if (q.get("error")) return paginaEsito(res, false, spiegaRifiuto(q));
      try {
        const r = await account.completa(q.get("code"), q.get("state"));
        console.log(`\n[mondo] account collegato: ${r.email} (${r.fornitore})`);
        return paginaEsito(res, true, r.email);
      } catch (e) { return paginaEsito(res, false, e.message); }
    }

    if (apiPath === "/api/account" || apiPath === "/api/account/manda") {
      if (!daLocale(req)) return json(res, 403, { ok: false, errore: "solo da questo computer" });
      if (apiPath === "/api/account" && req.method === "GET") return json(res, 200, account.vista());
      if (req.method === "POST") {
        const p = await leggiCorpo(req);
        try {
          if (apiPath === "/api/account/manda") return json(res, 200, await account.manda(p));
          switch (p.azione) {
            case "configura": return json(res, 200, await account.configura(p.fornitore, p.clientId, p.clientSecret));
            case "esci":      return json(res, 200, await account.esci());
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
    // I lavori finiti dagli agenti: la Vetrina li mostra da qui. Sola lettura,
    // e solo da questa cartella — il controllo sotto impedisce di risalire.
    if (urlPath.startsWith("/lavori/")) {
      base = path.join(ROOT, "..", "lavori");
      urlPath = urlPath.slice("/lavori".length);
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

/**
 * Quando il fornitore rifiuta manda un codice, non una spiegazione:
 * 'access_denied' da solo non dice a nessuno cosa fare. Qui diventa
 * l'istruzione vera, perche' e' il momento in cui uno e' bloccato.
 */
function spiegaRifiuto(q) {
  const e = q.get("error") || "";
  const d = q.get("error_description") || "";
  if (e === "access_denied")
    return "Google o Microsoft ha rifiutato l'accesso.\n\n"
         + "Quasi sempre e' perche' il progetto e' «in test» e il tuo indirizzo non e' "
         + "fra gli utenti di prova. Nella console del fornitore: Schermata consenso "
         + "OAuth → Utenti di prova → aggiungi il tuo indirizzo, poi riprova.\n\n"
         + "L'altra possibilita' e' che tu abbia premuto «Annulla» sulla schermata di consenso.";
  if (e === "redirect_uri_mismatch")
    return "L'indirizzo di ritorno non coincide con quello registrato nella console del fornitore.";
  if (e === "invalid_client")
    return "ID client o segreto sbagliati: ricontrollali nella console del fornitore.";
  if (/scope/i.test(e + d))
    return "Sono stati concessi meno permessi del necessario: riprova accettando tutte le richieste.";
  return [e, d].filter(Boolean).join(" — ") || "il fornitore non ha detto perche'";
}

/** La scheda che si apre al ritorno dal fornitore: dice com'e' andata. */
function paginaEsito(res, ok, testo) {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  res.writeHead(ok ? 200 : 400, { "Content-Type": "text/html; charset=utf-8" });
  res.end(`<!doctype html><meta charset="utf-8"><title>${ok ? "Collegato" : "Non riuscito"}</title>
<style>body{font-family:system-ui,sans-serif;background:#0a1020;color:#e9edf8;display:grid;
place-items:center;height:100vh;margin:0;text-align:center;padding:24px}
.c{max-width:460px}h1{font-size:22px;margin:0 0 10px}p{color:#8a96b3;line-height:1.6;margin:0 0 8px}
b{color:${ok ? "#4ce0a5" : "#ff9f6b"}}</style>
<div class="c"><h1>${ok ? "✓ Account collegato" : "Non e' andata"}</h1>
<p style="white-space:pre-line"><b>${esc(testo)}</b></p>
<p>${ok ? "Puoi chiudere questa scheda e tornare al Quartier Generale."
        : "Chiudi questa scheda e riprova dal Quartier Generale."}</p></div>`);
}

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
    // L'indirizzo di ritorno deve combaciare con quello registrato sulla
    // console del fornitore, e contiene la porta: si sa solo adesso.
    await account.init(`http://localhost:${port}/oauth/callback`);
    await negozio.init(`http://localhost:${port}/negozio/callback`);
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
