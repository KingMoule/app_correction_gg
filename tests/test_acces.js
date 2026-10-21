// Test de pwa/acces.js (audit E6), lancé par tests/test_js.py : `node --test tests/test_acces.js`.
// Données fictives; `fetch` est simulé. Vérifie surtout que les modifications en attente survivent à un 401.
'use strict';
const test = require("node:test");
const assert = require("node:assert/strict");
const { creerFetchAcces } = require("../pwa/acces.js");
const { creerEnvoiFrancais } = require("../pwa/envoi-francais.js");

const ORIGINE = "http://192.168.1.23:8001";
const reponse = (statut, corps = {}) => ({ ok: statut >= 200 && statut < 300, status: statut, json: async () => corps });

// Moteur simulé : tout /api/ répond 401 tant que `connecte` est faux.
function moteur() {
  const m = { connecte: false, appels: [] };
  m.fetch = async (url, options) => {
    m.appels.push({ url, options });
    if (!m.connecte && String(url).startsWith("/api/") && !String(url).startsWith("/api/connexion")) return reponse(401);
    return reponse(200, { revision: 2 });
  };
  return m;
}

test("401 : la requête attend la saisie du code puis est rejouée", async () => {
  const m = moteur();
  let saisies = 0;
  const fetchAcces = creerFetchAcces(m.fetch, async () => { saisies++; m.connecte = true; }, ORIGINE);
  const r = await fetchAcces("/api/bibliotheque", { method: "GET" });
  assert.equal(r.status, 200);
  assert.equal(saisies, 1);
  assert.equal(m.appels.length, 2);
});

test("plusieurs requêtes en 401 : une seule saisie, toutes rejouées", async () => {
  const m = moteur();
  let saisies = 0, ouvrir;
  const porte = new Promise((r) => { ouvrir = r; });
  const fetchAcces = creerFetchAcces(m.fetch, async () => { saisies++; await porte; m.connecte = true; }, ORIGINE);
  const toutes = Promise.all([fetchAcces("/api/a"), fetchAcces("/api/b"), fetchAcces("/api/c")]);
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(saisies, 1);
  ouvrir();
  const rs = await toutes;
  assert.deepEqual(rs.map((r) => r.status), [200, 200, 200]);
  assert.equal(saisies, 1);
});

test("connexion, keepalive et adresses hors /api/ ne déclenchent pas la saisie", async () => {
  const appels = [];
  const fetch401 = async (url) => { appels.push(url); return reponse(401); };
  const fetchAcces = creerFetchAcces(fetch401, async () => assert.fail("pas de saisie"), ORIGINE);
  assert.equal((await fetchAcces("/api/connexion", { method: "POST" })).status, 401);
  assert.equal((await fetchAcces("/api/deconnexion", { method: "POST" })).status, 401);
  assert.equal((await fetchAcces("/api/francais/x", { method: "PATCH", keepalive: true })).status, 401);
  assert.equal((await fetchAcces("/manifest.webmanifest")).status, 401);
  assert.equal((await fetchAcces("https://autre.example/api/x")).status, 401);
  assert.equal(appels.length, 5);
});

test("la file d'envoi du français reprend après la saisie du code, sans perdre de décision", async () => {
  const m = moteur();
  const fetchAcces = creerFetchAcces(m.fetch, async () => {
    await new Promise((r) => setTimeout(r, 30)); // l'enseignant tape son code
    m.connecte = true;
  }, ORIGINE);
  const etats = [];
  const envoi = creerEnvoiFrancais({ url: "/api/francais/rapport/x", fetch: fetchAcces, delai: 1, reessai: 10, entreEssais: 5,
    surEtat: (texte) => etats.push(texte) });
  try {
    envoi.noter("f1", { decision: "acceptee" });
    envoi.noter("f2", { decision: "refusee" });
    assert.equal(await envoi.toutEnregistrer(), true);
    const envoyes = m.appels.filter((a) => a.options?.method === "PATCH").map((a) => JSON.parse(a.options.body).fautes);
    assert.deepEqual(envoyes.at(-1), { f1: { decision: "acceptee" }, f2: { decision: "refusee" } });
    assert.equal(envoi.nonEnregistre(), false);
  } finally {
    envoi.arreter();
  }
});
