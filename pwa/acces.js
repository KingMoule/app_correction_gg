// Code d'accès (audit E6). Chargé en premier dans chaque écran.
//
// Toute réponse 401 d'une requête /api/ affiche l'écran de saisie du code PAR-DESSUS l'écran courant, attend la
// connexion, puis REJOUE la même requête. L'écran n'est jamais quitté : le lecteur, ses traits en attente, la
// file d'envoi du français (envoi-francais.js) et les formulaires gardent leur état et reprennent d'eux-mêmes.
// Exceptions : /api/connexion et /api/deconnexion, et les envois `keepalive` (fermeture de la page, rien à attendre :
// l'appelant les réessaiera). Un lien ouvert directement (téléchargement) est redirigé par le moteur vers
// /acces.html?suite=..., qui y revient après la saisie.
'use strict';

function creerFetchAcces(fetchBrut, demanderCode, origine) {
  const sansCode = new Set(["/api/connexion", "/api/deconnexion"]);
  const estApi = (entree) => {
    try {
      const u = new URL(typeof entree === "string" ? entree : entree.url, origine + "/");
      return u.origin === origine && u.pathname.startsWith("/api/") && !sansCode.has(u.pathname);
    } catch { return false; }
  };
  let enCours = null; // une seule saisie à la fois, même si dix requêtes reçoivent un 401
  const saisie = () => (enCours ??= Promise.resolve(demanderCode()).finally(() => { enCours = null; }));
  return async function fetchAcces(entree, options) {
    for (;;) {
      const r = await fetchBrut(entree, options);
      if (r.status !== 401 || options?.keepalive || !estApi(entree)) return r;
      await saisie();
    }
  };
}

// Écran de saisie. `options.page` = vrai sur acces.html (plein écran, retour à l'écran demandé ensuite).
function creerEcranCode(doc, fetchBrut, options = {}) {
  let voile = null;
  const el = (tag, classe, texte) => { const e = doc.createElement(tag); if (classe) e.className = classe; if (texte) e.textContent = texte; return e; };

  function construire(fin) {
    voile = el("div", "acces-voile");
    voile.setAttribute("role", "dialog"); voile.setAttribute("aria-modal", "true"); voile.setAttribute("aria-labelledby", "acces-titre");
    const carte = el("form", "acces-carte");
    const titre = el("h1", "", "Code d'accès"); titre.id = "acces-titre";
    const aide = el("p", "aide", options.page
      ? "Saisis le code pour ouvrir l'app. Cet appareil s'en souviendra."
      : "Saisis le code pour continuer. Tes modifications en attente sont conservées.");
    const etiquette = el("label", "", "Code"); etiquette.htmlFor = "acces-code";
    const champ = el("input"); champ.id = "acces-code"; champ.type = "password"; champ.autocomplete = "current-password";
    champ.setAttribute("autocapitalize", "none"); champ.setAttribute("autocorrect", "off"); champ.spellcheck = false; champ.required = true;
    const bouton = el("button", "acces-bouton", "Entrer"); bouton.type = "submit";
    const message = el("p", "acces-message"); message.setAttribute("aria-live", "polite");
    carte.append(titre, aide, etiquette, champ, bouton, message);
    voile.append(carte);
    let minuterie = null;
    function bloquer(secondes) {
      clearInterval(minuterie);
      let reste = secondes;
      bouton.disabled = reste > 0;
      if (reste <= 0) return;
      minuterie = setInterval(() => {
        reste -= 1;
        message.textContent = `Trop d'essais. Réessaie dans ${reste} s.`;
        if (reste <= 0) { clearInterval(minuterie); bouton.disabled = false; message.textContent = ""; }
      }, 1000);
    }
    carte.onsubmit = async (e) => {
      e.preventDefault();
      bouton.disabled = true; message.textContent = "";
      let r, d = {};
      try {
        r = await fetchBrut("/api/connexion", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: champ.value }) });
        d = await r.json().catch(() => ({}));
      } catch {
        message.textContent = "Moteur injoignable : l'ordi est-il allumé et sur le même Wi-Fi ?";
        bouton.disabled = false; return;
      }
      if (r.ok) { champ.value = ""; clearInterval(minuterie); fin(); return; }
      message.textContent = d.detail || `Erreur ${r.status}`;
      champ.select();
      if (d.attente) bloquer(d.attente); else bouton.disabled = false;
    };
    doc.body.append(voile);
    champ.focus();
  }

  // Affiche l'écran et rend une promesse résolue après la connexion.
  return function demanderCode() {
    return new Promise((resoudre) => {
      if (voile) return; // déjà affiché : la promesse partagée de creerFetchAcces suffit
      construire(() => { voile.remove(); voile = null; resoudre(); options.surConnexion?.(); });
    });
  };
}

if (typeof module !== "undefined") module.exports = { creerFetchAcces, creerEcranCode };

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const lien = document.createElement("link");
  lien.rel = "stylesheet"; lien.href = "/acces.css";
  document.head.append(lien);
  const fetchBrut = window.fetch.bind(window);
  if (document.documentElement.dataset.pageAcces === "1") {
    // acces.html : saisie plein écran, puis retour à l'écran demandé (chemin interne seulement).
    const suite = new URLSearchParams(location.search).get("suite") || "/";
    const sure = suite.startsWith("/") && !suite.startsWith("//") && !suite.startsWith("/\\") ? suite : "/";
    document.addEventListener("DOMContentLoaded", () => {
      creerEcranCode(document, fetchBrut, { page: true, surConnexion: () => location.replace(sure) })();
    });
  } else {
    const ecran = creerEcranCode(document, fetchBrut);
    window.fetch = creerFetchAcces(fetchBrut, () => new Promise((res) => {
      const afficher = () => ecran().then(res);
      if (document.body) afficher(); else document.addEventListener("DOMContentLoaded", afficher);
    }), location.origin);
    document.addEventListener("DOMContentLoaded", async () => {
      const bouton = document.getElementById("deconnexion");
      if (!bouton) return;
      try { // pas de code en mode --local : rien à quitter
        const etat = await (await fetchBrut("/api/connexion")).json();
        bouton.hidden = !etat.requis;
      } catch { /* moteur injoignable : le bouton reste visible */ }
      bouton.onclick = async () => {
        await fetchBrut("/api/deconnexion", { method: "POST" });
        location.reload(); // la première requête reçoit un 401 et affiche l'écran de saisie
      };
    });
  }
}
