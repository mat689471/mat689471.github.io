/**
 * vault.mjs — La Cassaforte.
 *
 * Custodisce in locale le credenziali che servono agli agenti (chiavi API,
 * link di incasso, identificativi). Tre principi:
 *
 *  1) NON LASCIA MAI IL PC. I segreti vivono in dati/cassaforte.enc, che è
 *     escluso da git: non finiscono nel sito pubblico né in un repository.
 *  2) CIFRATI A RIPOSO. AES-256-GCM. La chiave deriva da una passphrase che
 *     scegli tu (scrypt, mai salvata) oppure, se non ne imposti una, da una
 *     master key locale in dati/.masterkey.
 *  3) GLI AGENTI NON LI VEDONO. Un agente non riceve mai il valore di una
 *     chiave: la usa per nome come variabile d'ambiente ($env:MESHY_API_KEY).
 *     Così il segreto non passa dalla conversazione e non finisce nei log.
 *
 * La passphrase è la protezione più forte: se la imposti, la cassaforte parte
 * chiusa a ogni avvio e va sbloccata. Senza passphrase i segreti restano
 * cifrati sul disco, ma chiunque usi il tuo account Windows può aprirli.
 */

import crypto from "node:crypto";
import { readFile, writeFile, mkdir, chmod } from "node:fs/promises";
import path from "node:path";

const ALG = "aes-256-gcm";
const VERSIONE = 1;

export class Cassaforte {
  constructor(dirDati) {
    this.file = path.join(dirDati, "cassaforte.enc");
    this.fileMaster = path.join(dirDati, ".masterkey");
    this.dir = dirDati;
    this.chiave = null;      // Buffer: chiave di cifratura in memoria
    this.segreti = null;     // { nome: {valore, tipo, note, creato, usato} }
    this.conPassphrase = false;
    this.sbloccata = false;
  }

  // ---- ciclo di vita ------------------------------------------------------
  async init() {
    await mkdir(this.dir, { recursive: true });
    let blob = null;
    try { blob = JSON.parse(await readFile(this.file, "utf8")); } catch { /* prima volta */ }

    if (!blob) {                       // cassaforte nuova, senza passphrase
      this.conPassphrase = false;
      this.chiave = await this.#masterKey();
      this.segreti = {};
      this.sbloccata = true;
      await this.#salva();
      return;
    }
    this.conPassphrase = !!blob.passphrase;
    if (this.conPassphrase) { this.sbloccata = false; return; }  // serve sbloccare? no: master key
    this.chiave = await this.#masterKey();
    try { this.segreti = this.#decifra(blob); this.sbloccata = true; }
    catch { this.segreti = null; this.sbloccata = false; }
  }

  /** Sblocca una cassaforte protetta da passphrase. */
  async sblocca(passphrase) {
    const blob = JSON.parse(await readFile(this.file, "utf8"));
    if (!blob.passphrase) return { ok: true, giaAperta: true };
    const chiave = await this.#daPassphrase(passphrase, Buffer.from(blob.salt, "base64"));
    try {
      const s = this.#decifra(blob, chiave);
      this.chiave = chiave; this.segreti = s; this.sbloccata = true;
      return { ok: true };
    } catch { return { ok: false, errore: "passphrase errata" }; }
  }

  /** Chiude la cassaforte: la chiave sparisce dalla memoria. */
  chiudi() {
    if (this.chiave) this.chiave.fill(0);
    this.chiave = null; this.segreti = null;
    this.sbloccata = !this.conPassphrase ? false : false;
  }

  /** Imposta (o rimuove) la passphrase, ricifrando tutto. */
  async impostaPassphrase(nuova) {
    this.#assertAperta();
    const segreti = this.segreti;
    if (nuova) {
      const salt = crypto.randomBytes(16);
      this.chiave = await this.#daPassphrase(nuova, salt);
      this.conPassphrase = true; this._salt = salt;
    } else {
      this.chiave = await this.#masterKey();
      this.conPassphrase = false; this._salt = null;
    }
    this.segreti = segreti;
    await this.#salva();
    return { ok: true, conPassphrase: this.conPassphrase };
  }

  // ---- segreti ------------------------------------------------------------
  async imposta(nome, valore, opz = {}) {
    this.#assertAperta();
    const n = normalizzaNome(nome);
    if (!n) return { ok: false, errore: "nome non valido" };
    if (!valore) return { ok: false, errore: "valore vuoto" };
    const prima = this.segreti[n];
    this.segreti[n] = {
      valore: String(valore),
      tipo: opz.tipo || (prima && prima.tipo) || "api",
      note: opz.note !== undefined ? opz.note : (prima ? prima.note : ""),
      creato: prima ? prima.creato : new Date().toISOString(),
      aggiornato: new Date().toISOString(),
      usato: prima ? prima.usato : null,
    };
    await this.#salva();
    return { ok: true, nome: n, avviso: rischioDi(n, valore) };
  }

  async rimuovi(nome) {
    this.#assertAperta();
    const n = normalizzaNome(nome);
    if (!this.segreti[n]) return { ok: false, errore: "non trovata" };
    delete this.segreti[n];
    await this.#salva();
    return { ok: true };
  }

  /** Elenco SICURO: valori mascherati, mai in chiaro. Per la pagina web. */
  elenco() {
    if (!this.sbloccata) return { sbloccata: false, conPassphrase: this.conPassphrase, chiavi: [] };
    const chiavi = Object.entries(this.segreti).map(([nome, s]) => ({
      nome, tipo: s.tipo, note: s.note || "",
      anteprima: maschera(s.valore),
      lunghezza: s.valore.length,
      creato: s.creato, aggiornato: s.aggiornato, usato: s.usato,
      avviso: rischioDi(nome, s.valore),
    })).sort((a, b) => a.nome.localeCompare(b.nome));
    return { sbloccata: true, conPassphrase: this.conPassphrase, chiavi };
  }

  /** Valore in chiaro: solo per uso interno (env degli agenti). */
  valore(nome) {
    if (!this.sbloccata) return null;
    const s = this.segreti[normalizzaNome(nome)];
    if (!s) return null;
    s.usato = new Date().toISOString();
    return s.valore;
  }

  /** Tutte le coppie nome→valore, per l'ambiente dei comandi. */
  ambiente() {
    if (!this.sbloccata) return {};
    const out = {};
    for (const [n, s] of Object.entries(this.segreti)) out[n] = s.valore;
    return out;
  }

  /** Solo i nomi: è ciò che gli agenti possono sapere. */
  nomi() { return this.sbloccata ? Object.keys(this.segreti) : []; }

  // ---- interni ------------------------------------------------------------
  #assertAperta() { if (!this.sbloccata) throw new Error("cassaforte chiusa"); }

  async #masterKey() {
    try {
      const b64 = await readFile(this.fileMaster, "utf8");
      return Buffer.from(b64.trim(), "base64");
    } catch {
      const k = crypto.randomBytes(32);
      await mkdir(this.dir, { recursive: true });
      await writeFile(this.fileMaster, k.toString("base64"), "utf8");
      try { await chmod(this.fileMaster, 0o600); } catch { /* non su Windows */ }
      return k;
    }
  }

  #daPassphrase(pass, salt) {
    // N=2^15 rende costoso provare le passphrase a tentativi. Serve alzare
    // maxmem: il limite predefinito di Node (32 MB) è troppo stretto per
    // questi parametri e la derivazione fallirebbe.
    return new Promise((res, rej) =>
      crypto.scrypt(String(pass), salt, 32, { N: 2 ** 15, r: 8, p: 1, maxmem: 96 * 1024 * 1024 },
        (e, k) => e ? rej(e) : res(k)));
  }

  #decifra(blob, chiave = this.chiave) {
    const iv = Buffer.from(blob.iv, "base64");
    const tag = Buffer.from(blob.tag, "base64");
    const d = crypto.createDecipheriv(ALG, chiave, iv);
    d.setAuthTag(tag);
    const chiaro = Buffer.concat([d.update(Buffer.from(blob.dati, "base64")), d.final()]);
    return JSON.parse(chiaro.toString("utf8"));
  }

  async #salva() {
    const iv = crypto.randomBytes(12);
    const c = crypto.createCipheriv(ALG, this.chiave, iv);
    const dati = Buffer.concat([c.update(JSON.stringify(this.segreti), "utf8"), c.final()]);
    const blob = {
      versione: VERSIONE,
      passphrase: this.conPassphrase,
      salt: this._salt ? this._salt.toString("base64") : null,
      iv: iv.toString("base64"),
      tag: c.getAuthTag().toString("base64"),
      dati: dati.toString("base64"),
      _avviso: "File cifrato della Cassaforte. Non condividerlo e non metterlo in un repository.",
    };
    await writeFile(this.file, JSON.stringify(blob, null, 2), "utf8");
    try { await chmod(this.file, 0o600); } catch { /* non su Windows */ }
  }
}

// ---- utilità ---------------------------------------------------------------
export function normalizzaNome(n) {
  return String(n || "").trim().toUpperCase().replace(/[^A-Z0-9_]/g, "_").replace(/^_+|_+$/g, "").slice(0, 64);
}

export function maschera(v) {
  const s = String(v);
  if (s.length <= 8) return "•".repeat(s.length);
  return s.slice(0, 4) + "•".repeat(Math.min(12, s.length - 8)) + s.slice(-4);
}

/**
 * Segnala le credenziali che è meglio NON tenere qui.
 * Una chiave segreta "live" di Stripe può rimborsare, prelevare e leggere
 * tutti i tuoi clienti: per incassare non serve, e per le statistiche
 * basta una chiave con permessi di sola lettura.
 */
export function rischioDi(nome, valore) {
  const v = String(valore || "");
  if (/^sk_live_/.test(v)) return {
    livello: "alto",
    testo: "Questa è la chiave segreta LIVE di Stripe: può spostare denaro ed emettere rimborsi. Per incassare non serve, e per le statistiche basta una chiave ristretta (rk_live_) di sola lettura.",
  };
  if (/^sk_test_/.test(v)) return { livello: "basso", testo: "Chiave Stripe di test: non muove denaro reale." };
  if (/^rk_live_/.test(v)) return { livello: "ok", testo: "Chiave Stripe ristretta: è la scelta giusta per leggere le statistiche." };
  if (/PAYPAL.*SECRET|SECRET.*PAYPAL/i.test(nome)) return {
    livello: "medio",
    testo: "Segreto PayPal: dà accesso all'API del tuo conto. Usa credenziali con i soli permessi che ti servono.",
  };
  if (/^(https?:\/\/)/i.test(v)) return { livello: "nessuno", testo: "È un link, non una credenziale." };
  return null;
}
