/**
 * strumenti.mjs — Cosa hanno in mano gli agenti: competenze (Skill) e MCP.
 *
 * Le Skill non si accendono: l'ecosistema le trova da solo sul disco, esatta-
 * mente dove le cerca Claude Code. Qui servono solo per mostrarle.
 *
 * I server MCP invece vanno accesi, e finora l'unico modo era modificare a mano
 * mcp.json. Questo modulo lo legge e lo riscrive conservando i commenti, così
 * gli interruttori del Quartier Generale fanno lo stesso lavoro senza che tu
 * debba aprire un file di configurazione.
 */

import { readFile, writeFile, readdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";

/** Server pronti da accendere con un clic. Solo pacchetti che esistono davvero. */
export const CATALOGO = [
  {
    id: "ruflo",
    titolo: "ruflo",
    cosa: "Sciame, memoria condivisa e coordinamento fra agenti.",
    nota: "La prima accensione scarica il pacchetto: può metterci un minuto.",
    comando: "npx", argomenti: ["-y", "ruflo@latest", "mcp", "start"],
  },
  {
    id: "memoria",
    titolo: "Memoria persistente",
    cosa: "Un taccuino che gli agenti si passano e che sopravvive alla chiusura.",
    comando: "npx", argomenti: ["-y", "@modelcontextprotocol/server-memory"],
  },
  {
    id: "ragionamento",
    titolo: "Ragionamento a passi",
    cosa: "Aiuta un agente a spezzare un problema difficile invece di tirare a indovinare.",
    comando: "npx", argomenti: ["-y", "@modelcontextprotocol/server-sequential-thinking"],
  },
  {
    id: "file",
    titolo: "File del progetto",
    cosa: "Leggere e scrivere file, ma solo dentro la cartella che indichi tu.",
    nota: "La cartella consentita e' solo questa del progetto. Attenzione: gli strumenti MCP non passano dalla richiesta di autorizzazione del mondo, quindi un agente potrebbe scrivere o cancellare qui dentro senza chiedertelo.",
    rischio: true,
    comando: "npx", argomenti: ["-y", "@modelcontextprotocol/server-filesystem", "%PROGETTO%"],
  },
];

export class Strumenti {
  constructor(radice) {
    this.radice = radice;                          // cartella del progetto
    this.file = path.join(radice, "mcp.json");
  }

  // ---- mcp.json --------------------------------------------------------
  async config() {
    try { return JSON.parse(await readFile(this.file, "utf8")); }
    catch { return { server: {} }; }
  }

  /** Riscrive mcp.json lasciando intatto tutto quello che non tocchiamo. */
  async salva(cfg) {
    await writeFile(this.file, JSON.stringify(cfg, null, 2) + "\n", "utf8");
  }

  /** I server configurati, più quelli del catalogo non ancora aggiunti. */
  async server() {
    const cfg = await this.config();
    const configurati = Object.entries(cfg.server || {}).map(([id, s]) => ({
      id,
      titolo: (CATALOGO.find(c => c.id === id) || {}).titolo || id,
      cosa: s._nota || (CATALOGO.find(c => c.id === id) || {}).cosa || "",
      nota: (CATALOGO.find(c => c.id === id) || {}).nota || "",
      rischio: !!(CATALOGO.find(c => c.id === id) || {}).rischio,
      attivo: !!s.attivo,
      comando: [s.comando, ...(s.argomenti || [])].join(" "),
      configurato: true,
    }));
    const noti = new Set(configurati.map(s => s.id));
    const disponibili = CATALOGO.filter(c => !noti.has(c.id)).map(c => ({
      id: c.id, titolo: c.titolo, cosa: c.cosa, nota: c.nota || "", rischio: !!c.rischio,
      attivo: false, comando: [c.comando, ...c.argomenti].join(" "),
      configurato: false,
    }));
    return [...configurati, ...disponibili];
  }

  /** Accende o spegne un server; se non c'è ancora, lo prende dal catalogo. */
  async accendi(id, attivo) {
    const cfg = await this.config();
    cfg.server = cfg.server || {};
    if (!cfg.server[id]) {
      const c = CATALOGO.find(x => x.id === id);
      if (!c) throw new Error("server sconosciuto: " + id);
      cfg.server[id] = {
        _nota: c.cosa,
        attivo: false,
        comando: c.comando,
        // %PROGETTO% diventa la cartella vera solo ora che la conosciamo
        argomenti: c.argomenti.map(a => a === "%PROGETTO%" ? this.radice : a),
      };
    }
    cfg.server[id].attivo = !!attivo;
    await this.salva(cfg);
    return { ok: true, id, attivo: !!attivo };
  }

  /** Un server tuo, non del catalogo. */
  async aggiungi({ id, comando, argomenti, nota }) {
    id = String(id || "").trim().replace(/[^a-zA-Z0-9_-]/g, "");
    if (!id) throw new Error("serve un nome");
    if (!String(comando || "").trim()) throw new Error("serve un comando");
    const cfg = await this.config();
    cfg.server = cfg.server || {};
    cfg.server[id] = {
      _nota: String(nota || "").slice(0, 300),
      attivo: true,
      comando: String(comando).trim(),
      argomenti: Array.isArray(argomenti) ? argomenti.map(String)
               : String(argomenti || "").split(/\s+/).filter(Boolean),
    };
    await this.salva(cfg);
    return { ok: true, id };
  }

  async rimuovi(id) {
    const cfg = await this.config();
    if (cfg.server) delete cfg.server[id];
    await this.salva(cfg);
    return { ok: true };
  }

  // ---- competenze (Skill) ----------------------------------------------
  /**
   * Le stesse cartelle che guarda competenze.py, che a sua volta guarda dove
   * guarda Claude Code. Se le due liste divergono, un agente vedrebbe nel
   * mondo competenze che non ha davvero.
   */
  async competenze() {
    const home = homedir();
    const schemi = [
      [[path.join(home, ".claude", "skills")], "personale"],
      [[path.join(this.radice, ".claude", "skills")], "progetto"],
      [[path.join(home, ".claude", "plugins")], "plugin"],
    ];
    const out = [], viste = new Set();

    for (const [[radice], fonte] of schemi) {
      if (!existsSync(radice)) continue;
      // le skill dei plugin stanno più in profondità: scendiamo fino a 3 livelli
      const profondita = fonte === "plugin" ? 5 : 1;
      for (const dir of await this.#cartelleSkill(radice, profondita)) {
        const f = path.join(dir, "SKILL.md");
        if (!existsSync(f) || viste.has(f)) continue;
        viste.add(f);
        try {
          const testa = await this.#intestazione(f);
          out.push({
            nome: testa.name || path.basename(dir),
            descrizione: testa.description || "",
            fonte,
          });
        } catch { /* una skill illeggibile non deve far cadere l'elenco */ }
      }
    }
    out.sort((a, b) => a.nome.localeCompare(b.nome));
    return out;
  }

  /**
   * Ogni cartella che contiene un SKILL.md, scendendo al massimo di N livelli.
   * Una passeggiata ricorsiva e' piu' chiara di tanti schemi con gli asterischi,
   * e regge anche se un plugin annida le sue skill un po' piu' in fondo.
   */
  async #cartelleSkill(radice, profondita) {
    const trovate = [];
    const scendi = async (dir, giu) => {
      let voci;
      try { voci = await readdir(dir, { withFileTypes: true }); }
      catch { return; }                       // cartella non leggibile: la saltiamo
      if (voci.some(v => v.isFile() && v.name === "SKILL.md")) trovate.push(dir);
      if (giu <= 0) return;
      for (const v of voci) if (v.isDirectory()) await scendi(path.join(dir, v.name), giu - 1);
    };
    await scendi(radice, profondita);
    return trovate;
  }

  /** Legge nome e descrizione dall'intestazione YAML fra le due righe '---'. */
  async #intestazione(file) {
    const testo = await readFile(file, "utf8");
    const righe = testo.split(/\r?\n/);
    const campi = {};
    if (righe[0]?.trim() !== "---") return campi;
    let chiave = null;
    for (const r of righe.slice(1)) {
      if (r.trim() === "---") break;
      if (/^[ \t]/.test(r) && chiave) { campi[chiave] += " " + r.trim(); continue; }
      const i = r.indexOf(":");
      if (i > 0) { chiave = r.slice(0, i).trim(); campi[chiave] = r.slice(i + 1).trim().replace(/^["']|["']$/g, ""); }
    }
    return campi;
  }
}
