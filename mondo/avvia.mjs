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

const server = http.createServer(async (req, res) => {
  try {
    // API: la casella del mondo invia qui gli obiettivi per l'agente.
    if (req.method === "POST" && req.url.split("?")[0] === "/api/objective") {
      let body = "";
      req.on("data", (c) => { body += c; if (body.length > 100000) req.destroy(); });
      req.on("end", async () => {
        try {
          const { text } = JSON.parse(body || "{}");
          const clean = String(text || "").slice(0, 500).trim();
          if (!clean) { res.writeHead(400, { "Content-Type": "application/json" }); return res.end('{"ok":false,"err":"vuoto"}'); }
          await writeFile(path.join(ROOT, "objective.json"), JSON.stringify({ id: Date.now(), text: clean }, null, 2), "utf8");
          console.log(`\n[mondo] nuovo obiettivo: ${clean}`);
          res.writeHead(200, { "Content-Type": "application/json" }); res.end('{"ok":true}');
        } catch (e) { res.writeHead(500, { "Content-Type": "application/json" }); res.end('{"ok":false}'); }
      });
      return;
    }

    let urlPath = decodeURIComponent(req.url.split("?")[0]);
    if (urlPath === "/") urlPath = "/index.html";
    // impedisci di uscire dalla cartella
    const filePath = path.normalize(path.join(ROOT, urlPath));
    if (!filePath.startsWith(ROOT)) { res.writeHead(403); return res.end("Vietato"); }

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
    console.log("\n===============================================");
    console.log("  L'Ecosistema è in funzione!");
    console.log("  Aprilo qui:  " + url);
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
