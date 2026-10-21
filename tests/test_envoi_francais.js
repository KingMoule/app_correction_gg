// Test de pwa/envoi-francais.js (audit C2), lancé par tests/test_js.py : `node --test tests/test_envoi_francais.js`.
// Données fictives; `fetch` est simulé et ne sort jamais du processus.
'use strict';
const nodeTest = require("node:test");
const assert = require("node:assert/strict");
const { creerEnvoiFrancais } = require("../pwa/envoi-francais.js");

const reponse = (statut, corps = {}) => ({ ok: statut >= 200 && statut < 300, status: statut, json: async () => corps });

// Moteur simulé : `scenario` donne, appel après appel, une réponse ou une erreur réseau (« Load failed » comme Safari).
function moteurFictif(scenario) {
  const appels = [];
  const fetch = async (url, options) => {
    appels.push({ url, options, corps: JSON.parse(options.body) });
    const suite = scenario[Math.min(appels.length - 1, scenario.length - 1)];
    if (suite === "reseau") throw new TypeError("Load failed");
    return suite;
  };
  return { fetch, appels };
}

function creer(scenario, extra = {}) {
  const m = moteurFictif(scenario);
  const etats = [], reponses = [], refus = [];
  const envoi = creerEnvoiFrancais({
    url: "/api/francais/rapport/x", fetch: m.fetch, delai: 1, reessai: 10, entreEssais: 5,
    surEtat: (texte, erreur) => etats.push([texte, erreur]),
    surReponse: (d, adopter) => reponses.push([d, adopter]),
    surRefus: (statut, message) => refus.push([statut, message]),
    ...extra,
  });
  ouverts.push(envoi);
  return { ...m, envoi, etats, reponses, refus };
}
// Chaque test arrête les nouveaux essais automatiques de ses envois à la fin (sinon Node ne se termine pas).
const ouverts = [];
const test = (nom, f) => nodeTest(nom, async () => { try { await f(); } finally { ouverts.splice(0).forEach((e) => e.arreter()); } });
const attendre = (ms) => new Promise((r) => setTimeout(r, ms));
const OK = () => reponse(200, { revision: 2, nb_acceptees: 1, penalite: 0.5 });

test("coupure du Wi-Fi : la décision est gardée, renvoyée et confirmée (scénario C2 de l'audit)", async () => {
  const c = creer(["reseau", OK()]);
  const rejets = [];
  process.on("unhandledRejection", (e) => rejets.push(e));
  c.envoi.noter("12-18-abc", { decision: "acceptee" });
  await attendre(40); // 1er envoi (réseau coupé), puis nouvel essai automatique
  assert.equal(rejets.length, 0, "aucun rejet non géré");
  assert.equal(c.appels.length, 2);
  assert.deepEqual(c.appels[1].corps, { fautes: { "12-18-abc": { decision: "acceptee" } } });
  assert.deepEqual(c.etats.find(([t]) => t.startsWith("Non enregistré")), ["Non enregistré : nouvel essai…", true]);
  assert.deepEqual(c.etats.at(-1), ["Enregistré", false]);
  assert.equal(c.envoi.nonEnregistre(), false);
});

test("toutEnregistrer attend la confirmation et passe une brève coupure", async () => {
  const c = creer(["reseau", OK()]);
  c.envoi.noter("a", { decision: "refusee" });
  assert.equal(await c.envoi.toutEnregistrer(), true);
  assert.equal(c.appels.length, 2);
  assert.equal(c.envoi.nonEnregistre(), false);
});

test("moteur injoignable : toutEnregistrer renvoie false et la décision reste en attente", async () => {
  const c = creer(["reseau"]);
  c.envoi.noter("a", { decision: "acceptee" });
  assert.equal(await c.envoi.toutEnregistrer(), false);
  assert.equal(c.envoi.nonEnregistre(), true);
  assert.equal(c.etats.at(-1)[1], true, "l'indicateur « Non enregistré » reste visible");
  const avant = c.appels.length;
  await attendre(30); // le nouvel essai périodique continue
  assert.ok(c.appels.length > avant);
});

test("erreur 5xx du moteur : nouvel essai, rien n'est perdu", async () => {
  const c = creer([reponse(503), OK()]);
  c.envoi.noter("a", { decision: "acceptee" });
  assert.equal(await c.envoi.toutEnregistrer(), true);
  assert.equal(c.appels.length, 2);
});

test("un changement fait pendant l'échec n'est pas écrasé par le renvoi", async () => {
  let ouvrir;
  const porte = new Promise((r) => { ouvrir = r; });
  const appels = [];
  const fetch = async (url, o) => {
    appels.push(JSON.parse(o.body));
    if (appels.length === 1) { await porte; throw new TypeError("Load failed"); }
    return OK();
  };
  const envoi = creerEnvoiFrancais({ url: "/x", fetch, delai: 1, reessai: 10 });
  ouverts.push(envoi);
  envoi.noter("a", { decision: "acceptee", choix: "x" });
  await attendre(5);                        // 1er envoi parti, bloqué
  envoi.noter("a", { decision: "refusee" }); // l'utilisateur change d'avis pendant l'envoi
  ouvrir();
  await attendre(40);
  assert.deepEqual(appels.at(-1), { fautes: { a: { decision: "refusee", choix: "x" } } });
});

test("409 : le lot est abandonné, l'état est rechargé (surRefus) et toutEnregistrer renvoie false", async () => {
  const c = creer([reponse(409, { detail: "Une faute n'existe plus." })]);
  c.envoi.noter("a", { decision: "acceptee" });
  assert.equal(await c.envoi.toutEnregistrer(), false);
  assert.deepEqual(c.refus, [[409, "Une faute n'existe plus."]]);
  assert.equal(c.appels.length, 1, "pas de renvoi inutile");
  assert.equal(c.envoi.nonEnregistre(), false);
  assert.deepEqual(c.etats.at(-1), ["Une faute n'existe plus.", true]);
});

test("422 : message du moteur affiché, pas de renvoi", async () => {
  const c = creer([reponse(422, { detail: "Faute inconnue." })]);
  c.envoi.noter("a", { decision: "acceptee" });
  assert.equal(await c.envoi.toutEnregistrer(), false);
  assert.deepEqual(c.refus, [[422, "Faute inconnue."]]);
  assert.equal(c.appels.length, 1);
});

test("fermeture de la page : envoi keepalive de ce qui est en attente", async () => {
  const c = creer([OK()], { delai: 1000 });
  c.envoi.noter("a", { decision: "acceptee" });
  const ok = await c.envoi.envoyer(true);
  assert.equal(ok, true);
  assert.equal(c.appels[0].options.keepalive, true);
  assert.equal(c.appels[0].options.method, "PATCH");
});

test("rien en attente : toutEnregistrer répond tout de suite, sans appel", async () => {
  const c = creer([OK()]);
  assert.equal(await c.envoi.toutEnregistrer(), true);
  assert.equal(c.appels.length, 0);
});

test("la réponse du moteur n'est adoptée que s'il ne reste rien de plus récent en attente", async () => {
  const c = creer([OK()]);
  c.envoi.noter("a", { decision: "acceptee" });
  await c.envoi.toutEnregistrer();
  assert.equal(c.reponses[0][1], true);
});
