// Inspecteur du lecteur : onglets Français / Indice IA / Plagiat / Références (references.js), ouverture et fermeture, feuille à 3 hauteurs en portrait.
// Les onglets Indice IA et Plagiat n'affichent que ce que les API donnent déjà (/api/indices-ia, /api/plagiat) : un indice
// à revérifier, jamais un verdict. L'envoi d'une paire à Claude reste à l'écran Plagiat (confirmation de Guillaume).
// Dépend de lecteur.js ($, ref, base, params) et de ui.js (UI).
(() => {
  const PANNEAUX = { francais: "francais", ia: "vue-ia", plagiat: "vue-plagiat", references: "vue-references" };
  const FEUILLES = ["bas", "moyen", "haut"];
  const insp = $("inspecteur"), portrait = matchMedia("(max-aspect-ratio: 1/1)");
  const etat = { ouvert: true, onglet: "francais", feuille: "moyen" };
  try {
    const m = JSON.parse(localStorage.getItem("inspecteur-lecteur") || "{}");
    if (typeof m.ouvert === "boolean") etat.ouvert = m.ouvert;
    if (m.onglet in PANNEAUX) etat.onglet = m.onglet;
    if (FEUILLES.includes(m.feuille)) etat.feuille = m.feuille;
  } catch { /* stockage indisponible */ }
  if (params.get("panneau") === "francais") { etat.ouvert = true; etat.onglet = "francais"; } // « Français » de la bibliothèque
  if (params.get("panneau") === "references") { etat.ouvert = true; etat.onglet = "references"; } // « Références » du tableau de suivi
  const garder = () => { try { localStorage.setItem("inspecteur-lecteur", JSON.stringify(etat)); } catch { /* idem */ } };

  const h = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte !== undefined) e.textContent = texte; // textContent : le texte du rapport et de Claude n'est jamais du HTML
    return e;
  };
  const bouton = (libelle, classe, nomIcone, surClic) => {
    const b = h("button", "btn" + (classe ? " " + classe : ""));
    b.type = "button";
    if (nomIcone) b.append(UI.icone(nomIcone));
    b.append(libelle);
    b.onclick = surClic;
    return b;
  };
  const banniere = (texte, classe = "") => {
    const b = h("div", "banniere " + classe), c = h("div", "corps", texte);
    b.setAttribute("role", "status");
    b.append(UI.icone("info"), c);
    return b;
  };
  const erreurApi = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;

  // ----- hauteur de la feuille (portrait) : bas = onglets seuls, moyen, haut -----
  const hauteur = (nom) => (nom === "bas" ? 64 : nom === "moyen" ? 360 : Math.round(Math.min(innerHeight * 0.7, 760)));
  function appliquer() {
    insp.hidden = !etat.ouvert;
    $("panneau-bouton").setAttribute("aria-pressed", String(etat.ouvert));
    for (const o of Object.keys(PANNEAUX)) {
      const actif = o === etat.onglet;
      $("onglet-" + o).setAttribute("aria-selected", String(actif));
      $("onglet-" + o).tabIndex = actif ? 0 : -1;
      $(PANNEAUX[o]).hidden = !actif;
    }
    insp.style.height = portrait.matches ? hauteur(etat.feuille) + "px" : "";
  }
  portrait.addEventListener("change", appliquer);
  window.addEventListener("resize", () => { if (portrait.matches && !insp.classList.contains("glisse")) appliquer(); });

  const poignee = $("poignee");
  let depart = null;
  poignee.addEventListener("pointerdown", (e) => {
    poignee.setPointerCapture(e.pointerId);
    depart = { y: e.clientY, h: insp.offsetHeight, bouge: false };
  });
  poignee.addEventListener("pointermove", (e) => {
    if (!depart) return;
    const dy = depart.y - e.clientY;
    if (Math.abs(dy) > 6) depart.bouge = true;
    if (!depart.bouge) return;
    insp.classList.add("glisse");
    insp.style.height = Math.max(hauteur("bas"), Math.min(innerHeight * 0.8, depart.h + dy)) + "px";
  });
  const fin = () => {
    if (!depart) return;
    const d = depart; depart = null;
    insp.classList.remove("glisse");
    if (d.bouge) { // cran le plus proche
      const h0 = insp.offsetHeight;
      etat.feuille = FEUILLES.reduce((m, f) => (Math.abs(hauteur(f) - h0) < Math.abs(hauteur(m) - h0) ? f : m));
    } else etat.feuille = FEUILLES[(FEUILLES.indexOf(etat.feuille) + 1) % FEUILLES.length]; // un toucher : cran suivant
    appliquer(); garder();
    setTimeout(() => window.recentrerSelection?.(), 260); // la zone du PDF a changé de hauteur : la faute ouverte doit rester visible
  };
  poignee.addEventListener("pointerup", fin); poignee.addEventListener("pointercancel", fin);
  poignee.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); etat.feuille = FEUILLES[(FEUILLES.indexOf(etat.feuille) + 1) % FEUILLES.length]; appliquer(); garder(); } });

  // ----- onglets -----
  function choisir(onglet) {
    etat.onglet = onglet;
    appliquer(); garder();
    if (onglet === "ia") chargerIA();
    if (onglet === "plagiat") chargerPlagiat();
    if (onglet === "references") window.Refs?.charger(); // references.js, chargé après ce fichier
  }
  for (const o of Object.keys(PANNEAUX)) $("onglet-" + o).onclick = () => choisir(o);
  $("onglets").addEventListener("keydown", (e) => { // flèches gauche / droite entre onglets
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const noms = Object.keys(PANNEAUX), i = noms.indexOf(etat.onglet);
    choisir(noms[(i + (e.key === "ArrowRight" ? 1 : -1) + noms.length) % noms.length]);
    $("onglet-" + etat.onglet).focus();
  });
  $("panneau-bouton").onclick = () => { etat.ouvert = !etat.ouvert; appliquer(); garder(); };

  // Utilisé par francais.js : ouvre l'inspecteur sur un onglet; `minimum` relève la feuille en portrait.
  window.InspecteurUI = { h, bouton, banniere, erreurApi }; // partagé avec references.js
  window.Inspecteur = {
    onglet: () => etat.onglet,
    ouvrir(onglet, options = {}) {
      etat.ouvert = true;
      if (onglet && onglet !== etat.onglet) { choisir(onglet); }
      if (options.minimum && FEUILLES.indexOf(etat.feuille) < FEUILLES.indexOf(options.minimum)) etat.feuille = options.minimum;
      appliquer(); garder();
    },
  };

  // ----- Indice IA -----
  const FORCES = { faible: "Indice faible", moderee: "Indice modéré", marquee: "Indice marqué" };
  const ia = { donnees: undefined, texte: null, message: "", occupe: false, demande: false };
  async function chargerIA() {
    if (ia.demande || ref.some((v) => !v)) return;
    ia.demande = true;
    try {
      const [r, t] = await Promise.all([fetch(`/api/indices-ia/resultat/${base}`), fetch(`/api/indices-ia/texte/${base}`)]);
      ia.donnees = r.ok ? await r.json() : null;
      // Texte chargé d'avance : la copie doit se faire dans le geste du toucher (iPad).
      if (t.ok) ia.texte = (await t.json()).texte; else ia.message = await erreurApi(t);
    } catch {
      ia.demande = false; ia.message = "Moteur injoignable.";
    }
    majBadgeIA(); rendreIA();
  }
  function majBadgeIA() {
    const f = ia.donnees?.force;
    const marque = f === "moderee" || f === "marquee"; // un point violet seulement quand l'indice mérite un coup d'œil
    $("n-ia").hidden = !marque;
    if (marque) { $("n-ia").title = FORCES[f]; $("n-ia").setAttribute("aria-label", FORCES[f]); }
    window.forceIA = f ?? null;
  }
  async function analyserIA() {
    ia.occupe = true; ia.message = "Analyse en cours (peut prendre une minute)…"; rendreIA();
    try {
      const r = await fetch(`/api/indices-ia/analyser/${base}`, { method: "POST" });
      if (!r.ok) ia.message = await erreurApi(r);
      else { ia.donnees = await r.json(); ia.message = ""; majBadgeIA(); }
    } catch { ia.message = "Moteur injoignable."; }
    ia.occupe = false; rendreIA();
  }
  async function copier(texte) {
    try { await navigator.clipboard.writeText(texte); return true; } catch {
      const zone = document.createElement("textarea");
      zone.value = texte; document.body.append(zone); zone.select();
      const ok = document.execCommand?.("copy");
      zone.remove();
      return !!ok;
    }
  }
  // Aucun envoi automatique : le texte va dans le presse-papiers, Guillaume le colle lui-même dans Pangram.
  function pangram() {
    if (!ia.texte) { ia.message = "Texte du rapport pas encore chargé."; rendreIA(); return; }
    const copie = copier(ia.texte); // lancée dans le geste, avant d'ouvrir l'onglet
    window.open("https://www.pangram.com", "_blank", "noopener");
    copie.then((ok) => { ia.message = ok ? "Texte copié : colle-le dans Pangram." : "Copie refusée par le navigateur."; rendreIA(); });
  }
  function rendreIA() {
    const racine = $("vue-ia"), d = ia.donnees;
    racine.replaceChildren(banniere("Un indice à revérifier, jamais un verdict. Analyse de style faite par Claude.", ""));
    if (ia.donnees === undefined && !ia.message) { racine.append(h("p", "vue-texte", "Chargement…")); return; }
    if (d) {
      const p = h("span", "pastille p-ia"); p.append(UI.icone("scan-search"), FORCES[d.force] ?? FORCES.faible);
      racine.append(p, h("p", "vue-texte", d.resume));
      for (const s of d.signaux) {
        const b = h("div", "signal");
        b.append(h("div", undefined, s.observation), h("blockquote", undefined, `« ${s.extrait} »`));
        if (!s.verifie) b.append(h("div", "non-verifie", "Extrait introuvable mot pour mot dans le rapport : à vérifier."));
        racine.append(b);
      }
      if (d.contre_indices.length) {
        racine.append(h("h3", "vue-titre", "Contre-indices"));
        const ul = h("ul"); for (const c of d.contre_indices) ul.append(h("li", undefined, c));
        racine.append(ul);
      }
      if (d.avertissement) racine.append(h("p", "mu", d.avertissement));
    } else racine.append(h("p", "vue-texte", "Ce rapport n'a pas encore été analysé."));
    if (ia.message) racine.append(h("p", "vue-texte", ia.message));
    const actions = h("div", "vue-actions");
    const analyser = bouton(d ? "Refaire l'analyse" : "Analyser le style", d ? "" : "primaire", "sparkles", analyserIA);
    analyser.disabled = ia.occupe;
    actions.append(analyser, bouton("Copier pour Pangram", "", "copy", pangram));
    racine.append(actions);
  }

  // ----- Plagiat : les paires de ce rapport, avec leurs passages communs -----
  const STATUTS = { a_confirmer: "À confirmer", en_cours: "Claude analyse…", ecartee: "Écartée", analysee: "Analysée", erreur: "Erreur" };
  const VERDICTS = { copie: "Copie", paraphrase: "Paraphrase", coincidence: "Coïncidence" };
  const CONFIANCES = { faible: "faible", moyenne: "moyenne", elevee: "élevée" };
  const pl = { paires: undefined, ouvertes: new Map(), message: "", demande: false };
  const pct = (x) => `${Math.round(x * 100)} %`;
  const moi = (r) => r.cours === ref[0] && r.groupe === ref[1] && r.lab === ref[2] && r.etudiant === ref[3];
  async function chargerPlagiat(force) {
    if ((pl.demande && !force) || ref.some((v) => !v)) return;
    pl.demande = true;
    try {
      const r = await fetch("/api/plagiat/paires");
      if (!r.ok) throw new Error(r.status);
      const d = await r.json();
      pl.paires = d.paires.filter((p) => (moi(p.a) || moi(p.b)) && p.statut !== "sous_seuil");
      pl.message = "";
    } catch { pl.paires = pl.paires ?? []; pl.message = "Moteur injoignable : comparaisons non chargées."; pl.demande = false; }
    $("n-plagiat").hidden = !pl.paires.length; $("n-plagiat").textContent = pl.paires.length;
    rendrePlagiat();
  }
  async function voirPassages(p) {
    if (pl.ouvertes.has(p.cle)) { pl.ouvertes.delete(p.cle); rendrePlagiat(); return; }
    try {
      const r = await fetch(`/api/plagiat/paires/${encodeURIComponent(p.cle)}`);
      if (!r.ok) throw new Error(await erreurApi(r));
      pl.ouvertes.set(p.cle, await r.json());
    } catch (e) { pl.message = e.message || "Passages indisponibles."; }
    rendrePlagiat();
  }
  function rendrePlagiat() {
    const racine = $("vue-plagiat");
    racine.replaceChildren(banniere("Un indice pour t'aider à trancher, pas un verdict. Seuls les passages communs comptent : l'énoncé du lab est ignoré.", ""));
    if (pl.paires === undefined && !pl.message) { racine.append(h("p", "vue-texte", "Chargement…")); return; }
    if (pl.message) racine.append(h("p", "vue-texte", pl.message));
    if (pl.paires && !pl.paires.length) racine.append(h("p", "vue-texte", "Aucune paire à signaler pour ce rapport. Si la comparaison n'a pas été lancée, elle se lance depuis l'écran Plagiat."));
    for (const p of pl.paires ?? []) {
      const autre = moi(p.a) ? p.b : p.a, mon = moi(p.a) ? "a" : "b";
      const carte = h("div", "paire-l"), tete = h("div", "tete");
      const verdict = p.resultat?.verdict;
      const pastille = h("span", "pastille p-plagiat", verdict ? VERDICTS[verdict] : STATUTS[p.statut] ?? p.statut);
      tete.append(h("b", undefined, autre.nom || autre.etudiant), pastille);
      carte.append(tete, h("div", "mu", `${UI.titreCours(autre.cours)} gr. ${autre.groupe} · ${autre.lab} · score ${pct(p.score)} · ${p.nb_passages} passage(s) commun(s)`));
      if (p.statut === "erreur") carte.append(h("p", "vue-texte erreur", `Claude n'a pas pu répondre : ${p.resultat?.erreur ?? "erreur"}`));
      if (p.statut === "analysee") carte.append(h("p", "vue-texte", `Claude : confiance ${CONFIANCES[p.resultat.confiance] ?? p.resultat.confiance}. ${p.resultat.explication}`));
      const detail = pl.ouvertes.get(p.cle);
      carte.append(bouton(detail ? "Masquer les passages" : "Voir les passages", "", detail ? "chevron-up" : "chevron-down", () => voirPassages(p)));
      if (detail) {
        detail.passages.forEach((ps, i) => {
          const b = h("div", "pass"), sup = h("sup", undefined, `${i + 1}`);
          b.append(sup, h("mark", undefined, ps["texte_" + mon]), h("span", "cote", `${ps.mots} mots · aussi chez ${autre.nom || autre.etudiant}`));
          carte.append(b);
        });
      }
      racine.append(carte);
    }
    const lien = h("a", "btn", "Ouvrir l'écran Plagiat"); lien.href = "plagiat.html";
    const bas = h("div", "vue-actions"); bas.append(lien);
    racine.append(bas);
  }

  appliquer();
  if (etat.onglet === "ia") chargerIA();
  if (etat.onglet === "plagiat") chargerPlagiat();
  rendreIA(); rendrePlagiat();
  if (!ref.some((v) => !v)) setTimeout(() => { if (!pl.demande) chargerPlagiat(); }, 800); // pastille « Plagiat n » sans ouvrir l'onglet
})();
