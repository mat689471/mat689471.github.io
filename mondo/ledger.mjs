/**
 * ledger.mjs — Progetti e contabilità.
 *
 * Ogni progetto creato nell'ecosistema ha una sua scheda: incassi, costi,
 * margine, e il registro dei movimenti. I dati stanno in dati/progetti.json,
 * escluso da git: sono affari tuoi, non finiscono nel sito pubblico.
 *
 * I movimenti possono arrivare da tre parti:
 *   - a mano, dalla pagina;
 *   - dagli agenti, quando registrano un costo (es. crediti Meshy consumati);
 *   - da Stripe/PayPal, quando colleghi una chiave di sola lettura.
 *
 * Gli importi sono in centesimi (interi) per evitare gli errori di
 * arrotondamento dei decimali in virgola mobile.
 */

import { readFile, writeFile, mkdir, rename } from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const VUOTO = { versione: 1, progetti: [], movimenti: [] };

export class Registro {
  constructor(dirDati) {
    this.dir = dirDati;
    this.file = path.join(dirDati, "progetti.json");
    this.dati = structuredClone(VUOTO);
  }

  async init() {
    await mkdir(this.dir, { recursive: true });
    try {
      const d = JSON.parse(await readFile(this.file, "utf8"));
      this.dati = { ...structuredClone(VUOTO), ...d };
    } catch { await this.#salva(); }
  }

  async #salva() {
    const tmp = this.file + ".tmp";
    await writeFile(tmp, JSON.stringify(this.dati, null, 2), "utf8");
    await rename(tmp, this.file);
  }

  // ---- progetti -----------------------------------------------------------
  async creaProgetto(p) {
    const nome = String(p.nome || "").trim();
    if (!nome) return { ok: false, errore: "serve un nome" };
    const prog = {
      id: crypto.randomUUID().slice(0, 8),
      nome,
      descrizione: String(p.descrizione || "").slice(0, 500),
      cliente: String(p.cliente || "").slice(0, 120),
      stato: p.stato || "in corso",           // in corso | consegnato | sospeso
      valuta: (p.valuta || "EUR").toUpperCase().slice(0, 3),
      linkPagamento: String(p.linkPagamento || "").slice(0, 500),
      creato: new Date().toISOString(),
    };
    this.dati.progetti.push(prog);
    await this.#salva();
    return { ok: true, progetto: prog };
  }

  async aggiornaProgetto(id, campi) {
    const p = this.dati.progetti.find(x => x.id === id);
    if (!p) return { ok: false, errore: "progetto non trovato" };
    for (const k of ["nome", "descrizione", "cliente", "stato", "valuta", "linkPagamento"]) {
      if (campi[k] !== undefined) p[k] = String(campi[k]).slice(0, 500);
    }
    await this.#salva();
    return { ok: true, progetto: p };
  }

  async eliminaProgetto(id) {
    const n = this.dati.progetti.length;
    this.dati.progetti = this.dati.progetti.filter(x => x.id !== id);
    this.dati.movimenti = this.dati.movimenti.filter(m => m.progetto !== id);
    if (this.dati.progetti.length === n) return { ok: false, errore: "non trovato" };
    await this.#salva();
    return { ok: true };
  }

  // ---- movimenti ----------------------------------------------------------
  async aggiungiMovimento(m) {
    const importo = Math.round(Number(m.importo) * 100);
    if (!Number.isFinite(importo) || importo === 0) return { ok: false, errore: "importo non valido" };
    if (m.progetto && !this.dati.progetti.some(p => p.id === m.progetto))
      return { ok: false, errore: "progetto non trovato" };
    const mov = {
      id: crypto.randomUUID().slice(0, 8),
      progetto: m.progetto || null,
      tipo: m.tipo === "uscita" ? "uscita" : "entrata",
      centesimi: Math.abs(importo),
      valuta: (m.valuta || "EUR").toUpperCase().slice(0, 3),
      fonte: m.fonte || "manuale",            // manuale | stripe | paypal | agente
      descrizione: String(m.descrizione || "").slice(0, 300),
      data: m.data || new Date().toISOString().slice(0, 10),
      creato: new Date().toISOString(),
    };
    this.dati.movimenti.push(mov);
    await this.#salva();
    return { ok: true, movimento: mov };
  }

  async eliminaMovimento(id) {
    const n = this.dati.movimenti.length;
    this.dati.movimenti = this.dati.movimenti.filter(m => m.id !== id);
    if (this.dati.movimenti.length === n) return { ok: false, errore: "non trovato" };
    await this.#salva();
    return { ok: true };
  }

  // ---- lettura + statistiche ---------------------------------------------
  /** Tutto il necessario per la pagina: progetti con totali e serie mensile. */
  vista() {
    const perProgetto = new Map();
    for (const p of this.dati.progetti) {
      perProgetto.set(p.id, { entrate: 0, uscite: 0, movimenti: 0, ultimo: null });
    }
    let entrate = 0, uscite = 0;
    const mesi = new Map();

    for (const m of this.dati.movimenti) {
      const segno = m.tipo === "entrata";
      if (segno) entrate += m.centesimi; else uscite += m.centesimi;

      const agg = perProgetto.get(m.progetto);
      if (agg) {
        if (segno) agg.entrate += m.centesimi; else agg.uscite += m.centesimi;
        agg.movimenti++;
        if (!agg.ultimo || m.data > agg.ultimo) agg.ultimo = m.data;
      }
      const mese = String(m.data).slice(0, 7);
      if (!mesi.has(mese)) mesi.set(mese, { mese, entrate: 0, uscite: 0 });
      const r = mesi.get(mese);
      if (segno) r.entrate += m.centesimi; else r.uscite += m.centesimi;
    }

    const progetti = this.dati.progetti.map(p => {
      const a = perProgetto.get(p.id);
      return { ...p, entrate: a.entrate, uscite: a.uscite, netto: a.entrate - a.uscite,
               movimenti: a.movimenti, ultimoMovimento: a.ultimo };
    }).sort((a, b) => b.netto - a.netto);

    return {
      progetti,
      movimenti: [...this.dati.movimenti].sort((a, b) => (b.data + b.creato).localeCompare(a.data + a.creato)).slice(0, 300),
      totali: { entrate, uscite, netto: entrate - uscite, progetti: progetti.length,
                attivi: progetti.filter(p => p.stato === "in corso").length },
      serieMensile: [...mesi.values()].sort((a, b) => a.mese.localeCompare(b.mese)).slice(-12),
    };
  }
}
