// Écran « Analyse par lot » : lance, suit et arrête l'analyse Claude de plusieurs rapports d'un lab.
(() => {
  if (!document.querySelector("link[href='outils.css']")) {
    const lien = document.createElement("link");
    lien.rel = "stylesheet"; lien.href = "outils.css";
    document.head.append(lien);
  }
  const el = (id) => document.getElementById(id);
  let minuteur = null;

  const noeud = (tag, contenu) => {
    const n = document.createElement(tag);
    n.textContent = contenu; // jamais de HTML : les noms viennent de la bibliothèque
    return n;
  };
  const erreur = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;
  const labChoisi = () => {
    const v = el("lot-lab").value;
    return v ? JSON.parse(v) : null;
  };
  const url = (l, debut = "/api/lot") => `${debut}/${[l.cours, l.groupe, l.lab].map(encodeURIComponent).join("/")}`;

  window.rafraichirLot = (arbre) => {
    const courant = el("lot-lab").value;
    const options = [];
    for (const c of arbre) {
      const labs = new Set(c.etudiants.flatMap((e) => e.labs));
      for (const lab of [...labs].sort()) {
        const o = noeud("option", `${c.cours} · groupe ${c.groupe} · ${lab}`);
        o.value = JSON.stringify({ cours: c.cours, groupe: c.groupe, lab });
        options.push(o);
      }
    }
    el("lot-lab").replaceChildren(...options);
    if (courant && options.some((o) => o.value === courant)) el("lot-lab").value = courant;
    apercu();
  };

  // Appelé par la bibliothèque (bouton « Analyser » d'un groupe) : présélectionne ce lab.
  window.choisirLot = (cours, groupe, lab) => {
    el("lot-lab").value = JSON.stringify({ cours, groupe, lab });
    apercu();
  };

  async function apercu() {
    const l = labChoisi();
    el("lot-apercu").textContent = "";
    if (!l) return;
    try {
      const r = await fetch(`${url(l, "/api/lot/apercu")}?refaire=${el("lot-refaire").checked}`);
      if (!r.ok) return;
      const d = await r.json();
      el("lot-apercu").textContent = `${d.a_analyser} rapport(s) à analyser sur ${d.total}.`;
    } catch { /* moteur injoignable : l'état général l'indique déjà */ }
  }

  const LIBELLES = { en_cours: "En cours", termine: "Terminé", arrete: "Arrêté", limite: "Limite d'usage atteinte", erreur: "Arrêté sur erreur" };
  const PASTILLES = { en_cours: "p-claude", termine: "p-fini", arrete: "p-neutre", limite: "", erreur: "p-erreur" };

  // Direction Atelier : les éléments existent déjà dans la page (mêmes id); on y ajoute boutons à icône et progression chiffrée.
  const icone = (e, nom, libelle) => { e.replaceChildren(UI.icone(nom), document.createTextNode(libelle)); };
  el("lot-lancer").className = "btn primaire";
  icone(el("lot-lancer"), "play", "Lancer le lot");
  el("lot-arreter").className = "btn";
  icone(el("lot-arreter"), "x", "Arrêter");
  el("lot-arreter").title = "S'arrête après le rapport en cours; les résultats déjà obtenus sont gardés";
  const prog = noeud("div", ""); prog.className = "progression lot-prog"; prog.hidden = true;
  const tete = noeud("div", ""); tete.className = "progression-tete";
  const libelleProg = noeud("span", ""), numProg = noeud("span", ""); numProg.className = "num";
  tete.append(libelleProg, numProg);
  const barre = el("lot-barre");
  barre.replaceWith(prog);
  prog.append(tete, barre);
  barre.setAttribute("aria-label", "Progression de l'analyse par lot");

  function afficher(e) {
    const actif = e.statut === "en_cours";
    el("lot-lancer").disabled = actif;
    el("lot-arreter").hidden = !actif;
    el("lot-barre").hidden = prog.hidden = !e.total;
    if (e.total) { el("lot-barre").max = e.total; el("lot-barre").value = e.fait; }
    const msg = el("lot-etat");
    if (!e.total) { msg.textContent = ""; msg.className = ""; el("lot-erreurs").replaceChildren(); return; }
    // Progression chiffrée « 6 / 10 », pastille d'état et rapport en cours
    libelleProg.replaceChildren();
    const p = noeud("span", ""); p.className = "pastille " + (PASTILLES[e.statut] ?? "");
    if (actif) p.append(UI.icone("sparkles"));
    p.append(document.createTextNode(LIBELLES[e.statut] ?? e.statut));
    libelleProg.append(p);
    if (actif && e.courant) libelleProg.append(noeud("span", ` ${e.courant}`));
    numProg.textContent = `${e.fait} / ${e.total}`;
    // Ce qui exige une action : bannière (limite d'usage, erreur); sinon simple phrase
    msg.replaceChildren();
    msg.className = e.statut === "limite" ? "banniere attention" : e.statut === "erreur" ? "banniere erreur" : "aide";
    if (e.statut === "limite" || e.statut === "erreur") {
      msg.setAttribute("role", "alert");
      msg.append(UI.icone(e.statut === "limite" ? "triangle-alert" : "circle-alert"), noeud("span", e.message || LIBELLES[e.statut]));
    } else msg.textContent = e.message || "";
    el("lot-erreurs").replaceChildren(...e.erreurs.map((x) => noeud("li", `${x.nom} : ${x.message}`)));
  }

  async function suivre() {
    clearTimeout(minuteur);
    try {
      const e = await (await fetch("/api/lot")).json();
      afficher(e);
      if (e.statut === "en_cours") minuteur = setTimeout(suivre, 2000);
      else if (e.total) apercu();
    } catch {
      el("lot-etat").textContent = "Moteur injoignable.";
      minuteur = setTimeout(suivre, 5000);
    }
  }

  el("lot-lab").onchange = apercu;
  el("lot-refaire").onchange = apercu;

  el("lot-lancer").onclick = async () => {
    const l = labChoisi();
    if (!l) return;
    const n = Math.max(1, Math.min(200, parseInt(el("lot-n").value, 10) || 10));
    const r = await fetch(url(l), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, refaire: el("lot-refaire").checked }),
    });
    if (!r.ok) { el("lot-etat").textContent = await erreur(r); return; }
    suivre();
  };

  el("lot-arreter").onclick = async () => {
    await fetch("/api/lot/arreter", { method: "POST" });
    suivre();
  };

  suivre(); // reprend l'affichage d'un lot déjà en cours après un rechargement de la page
})();
