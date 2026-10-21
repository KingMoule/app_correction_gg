// File d'envoi des décisions de français (audit C1 et C2), sans dépendance au DOM (testée avec Node :
// tests/test_envoi_francais.js). Une décision n'est « enregistrée » que quand le moteur l'a confirmée :
// tant qu'elle ne l'est pas, elle reste en attente, est renvoyée (nouvel essai toutes les 4 s, envoi
// `keepalive` à la fermeture de la page) et l'indicateur « Non enregistré » reste visible.
//
// Un envoi = un PATCH des seules fautes changées { fautes: { <id>: { decision?, choix?, masquee?, decalage? } } },
// donc deux appareils qui décident sur des fautes différentes ne s'écrasent pas.
'use strict';

function creerEnvoiFrancais(o) {
  const delai = o.delai ?? 300, reessai = o.reessai ?? 4000, entreEssais = o.entreEssais ?? 1000;
  const regler = o.setTimeout ?? setTimeout, annuler = o.clearTimeout ?? clearTimeout;
  const dormir = (ms) => new Promise((r) => regler(r, ms));
  let attente = {};   // id de faute -> changements pas encore confirmés par le moteur
  let enCours = null; // envoi en cours (promesse)
  let minuterie = null;
  let refus = false;  // le moteur a refusé un lot (409 / 422) : l'état a été rechargé, des changements sont perdus

  const vide = () => Object.keys(attente).length === 0;
  const etat = (texte, erreur) => o.surEtat?.(texte, !!erreur);
  const detail = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;

  // Remet un lot non confirmé en attente, sans écraser ce qui a changé depuis son départ.
  function rendre(lot) {
    for (const [id, ch] of Object.entries(lot)) attente[id] = { ...ch, ...attente[id] };
  }

  function planifier(ms) {
    annuler(minuterie);
    minuterie = regler(() => { minuterie = null; envoyer(); }, ms);
  }

  async function tenter(lot, arret) {
    let r, d;
    try {
      r = await o.fetch(o.url, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fautes: lot }), keepalive: arret === true,
      });
      if (r.ok) d = await r.json();
    } catch {
      r = null;
    }
    if (r?.ok) {
      o.surReponse?.(d, vide()); // vide : rien de plus récent en attente, on peut adopter l'état du moteur
      if (vide()) etat("Enregistré"); else planifier(delai);
      return true;
    }
    if (r && (r.status === 409 || r.status === 422)) {
      // Le moteur refuse ce lot, et le renvoyer ne servirait à rien : 409 = le rapport a été réanalysé (une
      // faute n'existe plus), 422 = envoi invalide. On abandonne le lot et le lecteur recharge l'état du moteur.
      const message = await detail(r);
      attente = {}; refus = true;
      etat(message, true);
      try { await o.surRefus?.(r.status, message); } catch { /* le rechargement échouera de lui-même plus tard */ }
      return false;
    }
    // Réseau coupé, moteur injoignable ou erreur 5xx passagère : le lot reste en attente et sera renvoyé.
    rendre(lot);
    etat("Non enregistré : nouvel essai…", true);
    planifier(reessai);
    return false;
  }

  // Envoie ce qui est en attente. true = tout est confirmé par le moteur.
  async function envoyer(arret) {
    annuler(minuterie); minuterie = null;
    while (enCours && !arret) await enCours;
    if (vide()) return true;
    const lot = attente; attente = {};
    etat("Enregistrement…");
    const p = tenter(lot, arret).finally(() => { if (enCours === p) enCours = null; });
    enCours = p;
    return p;
  }

  return {
    // Note un changement de faute (champs fusionnés avec ceux déjà en attente) et planifie l'envoi.
    noter(id, champs) {
      attente[id] = { ...attente[id], ...champs };
      etat("Modifié…");
      planifier(delai);
    },
    envoyer,
    // Attend que tout soit confirmé (quelques essais pour passer une brève coupure). false = pas enregistré.
    async toutEnregistrer() {
      refus = false;
      for (let i = 0; i < 3; i++) {
        const ok = await envoyer();
        if (refus) return false;
        if (ok && vide() && !enCours) return true;
        if (i < 2) await dormir(entreEssais);
      }
      return false;
    },
    nonEnregistre: () => !vide() || !!enCours,
    arreter() { annuler(minuterie); minuterie = null; }, // coupe les nouveaux essais (tests)
  };
}

if (typeof module !== "undefined") module.exports = { creerEnvoiFrancais };
