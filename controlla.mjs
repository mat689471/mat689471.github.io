/**
 * controlla.mjs — L'archivio contiene ancora tutto?
 *
 * Un file puo' sparire dal repository senza che nessuno se ne accorga: basta
 * cancellarlo per sbaglio durante una prova e il salvataggio successivo porta
 * via anche lui. Il programma continua a funzionare sul computer di chi l'ha
 * cancellato - il file c'e' ancora, e' solo uscito dall'archivio - e il buco
 * salta fuori solo quando qualcun altro scarica lo zip. E' successo davvero.
 *
 * Questo controllo confronta l'elenco dei file con MANIFESTO.txt e verifica
 * che il codice si legga ancora. Gira da solo a ogni pubblicazione (vedi
 * .github/workflows/controlla.yml) e si puo' lanciare a mano:
 *
 *     node controlla.mjs
 */

import { readFile, access } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";

const esegui = promisify(execFile);
const RADICE = path.dirname(new URL(import.meta.url).pathname);
const problemi = [];
const ok = [];

function esiste(p) { return access(path.join(RADICE, p)).then(() => true, () => false); }

/** L'ultima riga che dice qualcosa: Python mette la spiegazione in fondo,
 *  ma dopo c'e' una riga vuota, e prenderla renderebbe il messaggio muto. */
function ultimaRiga(e) {
  const righe = String(e.stderr || e.message || e).split("\n").map(r => r.trim()).filter(Boolean);
  return righe[righe.length - 1] || "motivo non riportato";
}

// ---- 1. tutti i file del manifesto sono al loro posto? --------------------
const manifesto = (await readFile(path.join(RADICE, "MANIFESTO.txt"), "utf8"))
  .split("\n").map(r => r.replace(/#.*/, "").trim()).filter(Boolean);

let mancanti = 0;
for (const f of manifesto) {
  if (await esiste(f)) continue;
  problemi.push(`MANCA: ${f}`);
  mancanti++;
}
ok.push(`${manifesto.length - mancanti}/${manifesto.length} file del manifesto presenti`);

// ---- 2. il codice si legge ancora? ----------------------------------------
const mjs = manifesto.filter(f => f.endsWith(".mjs"));
for (const f of mjs) {
  if (!(await esiste(f))) continue;
  try { await esegui("node", ["--check", path.join(RADICE, f)]); }
  catch (e) { problemi.push(`NON SI LEGGE: ${f} — ${String(e.stderr || e).split("\n")[0]}`); }
}
ok.push(`${mjs.length} file JavaScript leggibili`);

const py = manifesto.filter(f => f.endsWith(".py"));
for (const f of py) {
  if (!(await esiste(f))) continue;
  try { await esegui("python3", ["-c", `import ast,io;ast.parse(io.open(${JSON.stringify(path.join(RADICE, f))},encoding="utf-8").read())`]); }
  catch (e) { problemi.push(`NON SI LEGGE: ${f} — ${ultimaRiga(e)}`); }
}
ok.push(`${py.length} file Python leggibili`);

// ---- 3. le pagine web: gli script dentro l'HTML si leggono? ---------------
const html = manifesto.filter(f => f.endsWith(".html"));
for (const f of html) {
  if (!(await esiste(f))) continue;
  const testo = await readFile(path.join(RADICE, f), "utf8");
  const blocchi = [...testo.matchAll(
    /<script(?![^>]*type="(?:importmap|application\/json)")[^>]*>([\s\S]*?)<\/script>/g)];
  for (const [i, b] of blocchi.entries()) {
    try { new Function(b[1]); }
    catch (e) { problemi.push(`NON SI LEGGE: ${f} script #${i + 1} — ${e.message}`); }
  }
}
ok.push(`${html.length} pagine web con gli script leggibili`);

// ---- esito -----------------------------------------------------------------
console.log("");
for (const r of ok) console.log("  ✓ " + r);
if (problemi.length) {
  console.log("\n  ── problemi ──");
  for (const p of problemi) console.log("  ✕ " + p);
  console.log(`\n${problemi.length} problemi: l'archivio NON e' completo.\n`);
  process.exit(1);
}
console.log("\nTutto a posto: l'archivio e' completo e il codice si legge.\n");
