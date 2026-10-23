// Lot de Claude d'un lab, monté dans la page du lab (onglet « Claude » et bouton « Analyser N · ≈ X % » de la barre d'onglets).
//   LotLab.monter({ cours, lab, panneau, rapide, surProgres }) -> { actualiser, suivre }
// `panneau` : contenu de l'onglet (taille du lot, « Refaire », estimation, progression, erreurs); `rapide` : le bouton une touche
// (ou « Claude · 3 / 7 » + « Arrêter » pendant le lot); `surProgres(etat)` : rappelé à chaque rapport traité et à la fin du lot.
// API : GET /api/lot/apercu/<cours>/<lab>, POST /api/lot/<cours>/<lab>, GET /api/lot, POST /api/lot/arreter.
// Le lot de la bibliothèque (lot.js, index.html#outils) est un écran à part, par groupe, qui disparaît avec la PR D.
(() => {
  for (const f of ["outils.css", "lot-lab.css"]) {
    if (!document.querySelector(`link[href='${f}']`)) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = f;
      document.head.append(l);
    }
  }
  const enc = encodeURIComponent;
  const el = (tag, classe, texte) => {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texte != null) n.textContent = texte; // jamais de HTML : les noms viennent de la bibliothèque
    return n;
  };
  const detail = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;
  const lire = (cle, defaut) => { try { return localStorage.getItem("lot:" + cle) ?? defaut; } catch { return defaut; } };
  const ecrire = (cle, v) => { try { localStorage.setItem("lot:" + cle, v); } catch { /* stockage indisponible */ } };

  const LIBELLES = { en_cours: "En cours", termine: "Terminé", arrete: "Arrêté", limite: "Limite d'usage atteinte", erreur: "Arrêté sur erreur" };
  const PASTILLES = { en_cours: "p-claude", termine: "p-fini", arrete: "p-neutre", limite: "", erreur: "p-erreur" };

  function monter({ cours, lab, panneau, rapide, surProgres }) {
    let info = null;  // { total, a_analyser, estimation } (aperçu du moteur)
    let etat = null;  // dernier GET /api/lot
    let minuteur = null, attenteN = null, jeton = 0, dernierFait = -1, tournait = false, cleRapide = null;

    // --- Panneau ---
    const intro = el("p", "lot-lab-intro");
    const champN = el("label", "champ lot-lab-n");
    const entree = el("input", "saisie");
    entree.type = "number"; entree.min = "1"; entree.max = "200"; entree.inputMode = "numeric";
    entree.value = lire("taille", "10");
    champN.append(el("span", "etiquette", "Rapports par lot"), entree);
    const refaire = el("input"); refaire.type = "checkbox";
    const champRefaire = el("label", "interrupteur");
    champRefaire.append(refaire, el("i"), el("span", "", "Refaire aussi les rapports déjà analysés"));
    const champs = el("div", "lot-lab-champs");
    champs.append(champN, champRefaire);
    const zoneEst = el("div", "lot-est"); zoneEst.hidden = true;
    const lancerP = el("button", "btn primaire"); lancerP.type = "button";
    const arreterP = el("button", "btn"); arreterP.type = "button";
    arreterP.title = "S'arrête après le rapport en cours; les résultats déjà obtenus sont gardés";
    const actions = el("div", "lot-lab-actions");
    actions.append(lancerP, arreterP);
    const prog = el("div", "progression lot-lab-prog"); prog.hidden = true;
    const tete = el("div", "progression-tete");
    const libProg = el("span"), numProg = el("span", "num");
    tete.append(libProg, numProg);
    const barre = document.createElement("progress");
    barre.setAttribute("aria-label", "Progression de l'analyse par lot");
    prog.append(tete, barre);
    const message = el("div"); message.setAttribute("aria-live", "polite");
    const erreurs = el("ul", "lot-lab-erreurs");
    panneau.replaceChildren(intro, champs, zoneEst, actions, prog, message, erreurs);

    const taille = () => Math.max(1, Math.min(200, parseInt(entree.value, 10) || 10));
    const avec = (b, icone, libelle) => { b.replaceChildren(UI.icone(icone), document.createTextNode(libelle)); return b; };

    // Estimation de ce lot (moteur/consommation.py) : on avertit près de la marge, sans jamais bloquer.
    function estimation(e) {
      zoneEst.replaceChildren();
      zoneEst.hidden = !e || !e.n;
      if (zoneEst.hidden) return;
      const ligne = el("div", "lot-est-ligne");
      const gros = el("span"); gros.append(el("b", "", `Ce lot ≈ ${Math.round(e.pct)} %`), document.createTextNode(" de la session"));
      ligne.append(gros, el("span", "mu", e.depasse
        ? `on atteindrait ≈ ${Math.round(e.apres)} % de la session`
        : `il resterait ≈ ${Math.round(100 - e.apres)} % · marge de ${Math.round(e.marge_pct)} % respectée`));
      const j = el("div", "lot-est-jauge" + (e.depasse ? " depasse" : ""));
      const deja = el("span", "deja"), lot = el("span", "lot"), repere = el("u");
      deja.style.width = `${Math.min(100, e.utilise)}%`;
      lot.style.left = `${Math.min(100, e.utilise)}%`; lot.style.width = `${Math.max(0, Math.min(100 - e.utilise, e.pct))}%`;
      repere.style.left = `${e.plafond_pct}%`;
      j.append(deja, lot, repere);
      const lg = el("div", "lot-est-legende");
      lg.append(el("span", "", `déjà utilisé ≈ ${Math.round(e.utilise)} %`), el("span", "", `repère à ${Math.round(e.plafond_pct)} %`));
      zoneEst.append(ligne, j, lg);
      if (!e.calibre || !e.mesure) {
        zoneEst.append(el("p", "aide", e.calibre ? "Coût par défaut pour certains appels (pas encore assez de mesures)."
          : "Estimation non calibrée : saisis ta lecture de /usage dans la page Consommation."));
      }
      if (e.depasse) {
        const b = el("div", "banniere attention"); b.setAttribute("role", "status");
        const corps = el("div", "corps");
        corps.append(el("b", "", `Dépasse la marge de ${Math.round(e.marge_pct)} %.`),
          document.createTextNode(` ${e.max_rapports ? `Seuls ${e.max_rapports} rapport(s) tiennent.` : "Aucun rapport ne tient."} Tu peux lancer quand même`));
        if (e.max_rapports) {
          corps.append(document.createTextNode(", ou "));
          const bt = el("button", "btn tertiaire", `ramener à ${e.max_rapports}`); bt.type = "button";
          bt.onclick = () => { entree.value = e.max_rapports; ecrire("taille", entree.value); apercu(); };
          corps.append(bt);
        }
        corps.append(document.createTextNode("."));
        b.append(UI.icone("triangle-alert"), corps);
        zoneEst.append(b);
      }
    }

    // --- Rendu : boutons, progression, messages ---
    function rendre() {
      const actif = etat?.statut === "en_cours";
      const mien = !!etat && etat.cours === cours && etat.lab === lab;
      const ailleurs = actif && !mien;
      const n = info ? Math.min(taille(), info.a_analyser) : 0;
      const e = info?.estimation;
      const pct = e?.pct > 0 ? ` · ≈ ${Math.max(1, Math.round(e.pct))} %` : "";
      const verbe = refaire.checked ? "Refaire" : "Analyser";
      const libelle = `${verbe} ${n}${pct}`;
      const alerte = !!e?.depasse;

      intro.textContent = info
        ? (info.a_analyser
          ? `${info.a_analyser} rapport(s) à analyser sur ${info.total} : fautes de français, indice d'IA et références, dans l'ordre de correction.`
          : `Les ${info.total} rapport(s) sont déjà analysés. Coche « Refaire » pour les reprendre.`)
        : "Lecture de l'aperçu…";

      // Panneau : un seul bouton plein (lancer, ou arrêter pendant le lot)
      lancerP.hidden = actif && mien;
      arreterP.hidden = !(actif && mien);
      avec(lancerP, alerte ? "triangle-alert" : "sparkles", n ? libelle : "Rien à analyser");
      lancerP.disabled = !n || ailleurs;
      avec(arreterP, "x", "Arrêter après le rapport en cours");
      champN.hidden = champRefaire.hidden = actif;

      // Bouton une touche de la barre d'onglets (reconstruit seulement quand il change : un toucher en cours ne tombe pas dans le vide)
      const cle = actif ? (mien ? `lot:${etat.fait}/${etat.total}` : `ailleurs:${etat.lab}`) : `${n}|${libelle}|${alerte}`;
      if (cle !== cleRapide) { cleRapide = cle; construireRapide(actif, mien, ailleurs, n, libelle, alerte); }
      suiteRendu(actif, mien, ailleurs);
    }

    function construireRapide(actif, mien, ailleurs, n, libelle, alerte) {
      rapide.replaceChildren();
      if (actif && mien) {
        const p = el("span", "pastille p-claude lot-lab-pastille");
        p.append(UI.icone("sparkles"), document.createTextNode(`Claude · ${etat.fait} / ${etat.total}`));
        const stop = el("button", "btn"); stop.type = "button";
        avec(stop, "x", "Arrêter");
        stop.onclick = arreter;
        rapide.append(p, stop);
      } else if (ailleurs) {
        const b = el("button", "btn"); b.type = "button"; b.disabled = true;
        avec(b, "sparkles", "Analyser");
        b.title = `Un lot tourne déjà (${etat.lab} · ${etat.cours}).`;
        rapide.append(b);
      } else if (n) {
        const b = el("button", "btn"); b.type = "button";
        avec(b, alerte ? "triangle-alert" : "sparkles", libelle);
        b.title = alerte ? "Dépasse la marge de la session : détail dans l'onglet Claude (le lot se lance quand même)."
          : "Analyse les prochains rapports (français, indice d'IA, références)";
        b.onclick = lancer;
        rapide.append(b);
      }
    }

    function suiteRendu(actif, mien, ailleurs) {
      // Progression et messages (seulement ceux de ce lab)
      const montre = mien && etat.total > 0;
      prog.hidden = !montre;
      message.replaceChildren(); message.className = "";
      erreurs.replaceChildren();
      if (ailleurs) {
        message.className = "banniere";
        message.setAttribute("role", "status");
        const corps = el("div", "corps", `Un lot tourne déjà sur ${etat.lab} · ${etat.cours} (${etat.fait} / ${etat.total}). Un seul lot à la fois : attends qu'il se termine, ou arrête-le depuis son lab.`);
        const voir = el("a", "btn", "Voir ce lab");
        voir.href = `suivi.html?${new URLSearchParams({ cours: etat.cours, lab: etat.lab })}#claude`;
        message.append(UI.icone("info"), corps, voir);
      }
      if (!montre) return;
      barre.max = etat.total; barre.value = etat.fait;
      libProg.replaceChildren();
      const p = el("span", "pastille " + (PASTILLES[etat.statut] ?? ""));
      if (actif) p.append(UI.icone("sparkles"));
      p.append(document.createTextNode(LIBELLES[etat.statut] ?? etat.statut));
      libProg.append(p);
      if (actif && etat.courant) libProg.append(el("span", "", ` ${etat.courant}`));
      numProg.textContent = `${etat.fait} / ${etat.total}`;
      if (etat.statut === "limite" || etat.statut === "erreur") {
        message.className = "banniere " + (etat.statut === "limite" ? "attention" : "erreur");
        message.setAttribute("role", "alert");
        message.append(UI.icone(etat.statut === "limite" ? "triangle-alert" : "circle-alert"), el("div", "corps", etat.message || LIBELLES[etat.statut]));
      } else if (etat.message) {
        message.className = "aide"; message.textContent = etat.message;
      }
      erreurs.replaceChildren(...etat.erreurs.map((x) => el("li", "", `${x.nom} : ${x.message}`)));
    }

    // --- Moteur ---
    async function apercu() {
      const mien = ++jeton;
      try {
        const r = await fetch(`/api/lot/apercu/${enc(cours)}/${enc(lab)}?refaire=${refaire.checked}&n=${taille()}`);
        if (!r.ok || mien !== jeton) return;
        info = await r.json();
        estimation(info.estimation);
        rendre();
      } catch { /* moteur injoignable : l'état général de la barre latérale l'indique déjà */ }
    }

    async function suivre() {
      clearTimeout(minuteur);
      try { etat = await (await fetch("/api/lot")).json(); } catch { minuteur = setTimeout(suivre, 5000); return; }
      const actif = etat.statut === "en_cours";
      rendre();
      if (actif) {
        if (etat.cours === cours && etat.lab === lab && etat.fait !== dernierFait) { dernierFait = etat.fait; surProgres?.(etat); }
        minuteur = setTimeout(suivre, 2000);
      } else if (tournait) {
        surProgres?.(etat); // fin du lot (terminé, arrêté, limite ou erreur) : le suivi se recharge
        apercu();
      }
      tournait = actif;
    }

    async function lancer() {
      if (!info || !info.a_analyser) return;
      const n = Math.min(taille(), info.a_analyser);
      const r = await fetch(`/api/lot/${enc(cours)}/${enc(lab)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n, refaire: refaire.checked }) });
      if (!r.ok) { UI.toast(await detail(r), { erreur: true }); suivre(); apercu(); return; }
      etat = await r.json();
      dernierFait = -1; tournait = true;
      rendre();
      UI.toast(`Lot lancé : ${etat.total} rapport(s)`, { action: { libelle: "Arrêter", surClic: arreter }, duree: 8000 });
      suivre();
    }

    async function arreter() {
      await fetch("/api/lot/arreter", { method: "POST" });
      suivre();
    }

    lancerP.onclick = lancer;
    arreterP.onclick = arreter;
    refaire.onchange = apercu;
    entree.oninput = () => { ecrire("taille", String(taille())); clearTimeout(attenteN); attenteN = setTimeout(apercu, 350); };

    rendre();
    apercu();
    suivre(); // reprend l'affichage d'un lot déjà en cours après un rechargement de la page
    return { actualiser: apercu, suivre };
  }

  window.LotLab = { monter };
})();
