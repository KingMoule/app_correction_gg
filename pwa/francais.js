// Fautes de français sur le PDF : surlignage rouge, correction manuscrite effaçable,
// acceptation/refus de chaque faute, barème du cours. Dépend de lecteur.js (pages, base, ref, $).
// Panneau « Français » de l'inspecteur : fiche de la faute en tête, liste par catégories; une faute traitée reste visible, grisée.
'use strict';

const URL_FRANCAIS = `/api/francais/rapport/${base}`;
const URL_BAREME = `/api/francais/bareme/${encodeURIComponent(ref[0] || "")}`;
let fr = null;        // état renvoyé par le moteur : fautes (id stable), revision, decisions, choix, masquees, decalages, penalite, bareme
let selection = null; // id de la faute ouverte dans la fiche
let deplacement = false; // mode « Déplacer » actif pour la faute ouverte
let autreOuvert = false, focusAutre = false; // saisie d'une correction libre dans la fiche

const el = (tag, texte, classe) => {
  const e = document.createElement(tag);
  if (texte !== undefined) e.textContent = texte; // textContent : le texte du rapport n'est jamais interprété comme du HTML
  if (classe) e.className = classe;
  return e;
};
const correctionDe = (f) => fr.choix[f.id] ?? f.suggestions[0] ?? null;
const decisionDe = (f) => fr.decisions[f.id];
const nombre = (n) => String(Math.round(n * 100) / 100).replace(".", ",");
const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;
// Catégories LanguageTool (et « CLAUDE » pour la passe Claude), dans l'ordre d'affichage de la liste.
const CATEGORIES = [["GRAMMAR", "Grammaire"], ["TYPOS", "Orthographe"], ["CONFUSION_RULES", "Confusions"], ["STYLE", "Style"],
  ["PUNCTUATION", "Ponctuation"], ["CLAUDE", "Repérées par Claude"]];
const nomCategorie = (f) => (CATEGORIES.find(([c]) => c === f.categorie) ?? [null, "Autres"])[1];
const icone = (nom, classes) => UI.icone(nom, classes);

async function erreurFr(r) { const d = await r.json().catch(() => ({})); return d.detail || `Erreur ${r.status}`; }
function etatFr(texte, erreur) {
  const e = $("fr-etat");
  e.textContent = texte; e.hidden = !texte; e.classList.toggle("erreur", !!erreur);
}

async function chargerFrancais() {
  const r = await fetch(URL_FRANCAIS);
  if (!r.ok) return;
  fr = await r.json();
  fr.decalages ??= {};
  afficherTout();
}

// ----- sauvegarde des décisions (envoi-francais.js : un PATCH par lot de fautes changées, renvoyé tant que le moteur ne confirme pas) -----
function indicateurFr(texte, erreur) {
  window.etatSauvegardeFrancais(texte, erreur); // l'indicateur « Enregistré » de la barre (lecteur.js)
  if (erreur) etatFr(texte, true); // le panneau n'affiche que les problèmes
}
const envoiFr = creerEnvoiFrancais({
  url: URL_FRANCAIS,
  fetch: (...a) => fetch(...a),
  surEtat: (texte, erreur) => indicateurFr(texte, erreur),
  surReponse(d, adopter) {
    fr.revision = d.revision; fr.nb_acceptees = d.nb_acceptees; fr.penalite = d.penalite;
    // Rien de plus récent en attente : on reprend l'état du moteur (changements faits sur un autre appareil compris).
    if (adopter && ["decisions", "choix", "masquees", "decalages"].some((k) => JSON.stringify(fr[k]) !== JSON.stringify(d[k]))) {
      Object.assign(fr, { decisions: d.decisions, choix: d.choix, masquees: d.masquees, decalages: d.decalages ?? {} });
      afficherTout();
    } else resume();
  },
  async surRefus(statut, message) {
    // 409 : rapport réanalysé ou modifié ailleurs; 422 : envoi invalide. L'état du moteur est rechargé.
    await chargerFrancais();
    window.Inspecteur?.ouvrir("francais");
    const texte = (statut === 409 ? "Décisions rechargées : le rapport a changé (nouvelle analyse ou autre appareil). "
      : "Le moteur a refusé l'enregistrement. ") + message + " Vos derniers changements n'ont pas été gardés : vérifiez les fautes.";
    etatFr(texte, true); indicateurFr("Rechargé : vérifiez", true);
  },
});
const sauverDecisions = (id, champs) => envoiFr.noter(id, champs);
// Attend la confirmation du moteur : true = tout est enregistré (appelé par toutEnregistrer() de lecteur.js).
function viderDecisions() { return envoiFr.toutEnregistrer(); }
window.addEventListener("pagehide", () => envoiFr.envoyer(true));
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") envoiFr.envoyer(true); });
function decider(id, valeur) {
  if (valeur) fr.decisions[id] = valeur; else delete fr.decisions[id];
  sauverDecisions(id, { decision: valeur ?? null }); afficherTout();
}
function deplacer(id, dx, dy) {
  const nul = Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5;
  if (nul) delete fr.decalages[id]; else fr.decalages[id] = [Math.round(dx * 10) / 10, Math.round(dy * 10) / 10];
  sauverDecisions(id, { decalage: nul ? null : fr.decalages[id] }); afficherTout();
}
function choisirCorrection(id, texte) { fr.choix[id] = texte; sauverDecisions(id, { choix: texte }); afficherTout(); }
function masquer(id, masque) {
  fr.masquees = fr.masquees.filter((m) => m !== id);
  if (masque) fr.masquees.push(id);
  sauverDecisions(id, { masquee: !!masque }); afficherTout();
}

// Accepter ou refuser depuis la fiche ou la liste : la faute reste visible (grisée), la suivante à trancher s'ouvre, toast avec « Annuler ».
// Toucher la décision déjà prise la retire (retour à « à trancher »).
function suivanteATrancher(id) {
  const i = fr.fautes.findIndex((x) => x.id === id), n = fr.fautes.length;
  for (let k = 1; k < n; k++) { const x = fr.fautes[(i + k) % n]; if (!decisionDe(x)) return x; }
  return null;
}
function trancher(f, valeur) {
  const avant = decisionDe(f), nouvelle = avant === valeur ? undefined : valeur;
  decider(f.id, nouvelle);
  if (!nouvelle) return;
  const c = correctionDe(f);
  UI.toast(nouvelle === "acceptee" ? `Faute acceptée : ${f.texte}${c ? " → " + c : ""}` : `Faute refusée : ${f.texte}`, {
    action: { libelle: "Annuler", surClic: () => { decider(f.id, avant); ouvrirFiche(f.id, true); } },
  });
  const suite = suivanteATrancher(f.id);
  if (suite) ouvrirFiche(suite.id, true);
}

// ----- couche sur les pages -----
function coucheDe(pg) {
  if (!pg.couche) { pg.couche = el("div", undefined, "fautes"); pg.el.append(pg.couche); }
  return pg.couche;
}
function ajouterZone(z, classes) {
  const d = el("div", undefined, "zone" + classes);
  Object.assign(d.style, { left: z.x0 + "px", top: z.y0 + "px", width: z.x1 - z.x0 + "px", height: z.y1 - z.y0 + "px" });
  coucheDe(pages[z.page - 1]).append(d);
}
function afficherCouches() {
  for (const pg of pages) coucheDe(pg).replaceChildren();
  if (!fr) return;
  for (const f of fr.fautes) {
    const decision = decisionDe(f);
    if (decision === "refusee") { // refusée : aucune marque, sauf un pointillé si sa fiche est ouverte (pour la retrouver)
      if (f.id === selection) for (const z of f.zones) ajouterZone(z, " refusee-choisie");
      continue;
    }
    const correction = correctionDe(f), premiere = f.zones[0];
    for (const z of f.zones) ajouterZone(z, (decision === "acceptee" ? " acceptee" : "") + (f.id === selection ? " choisie" : ""));
    if (correction && premiere && !fr.masquees.includes(f.id)) {
      const c = el("span", correction, "correction" + (decision === "acceptee" ? " acceptee" : ""));
      const [dx, dy] = fr.decalages?.[f.id] ?? [0, 0];
      Object.assign(c.style, { left: premiere.x0 + dx + "px", top: premiere.y0 - 13 + dy + "px" });
      if (deplacement && f.id === selection) { c.classList.add("mobile"); brancherDeplacement(c, f, dx, dy); }
      coucheDe(pages[premiere.page - 1]).append(c);
    }
  }
}

// Glisser la correction (mode « Déplacer ») : le décalage est en points PDF, donc indépendant du zoom.
function brancherDeplacement(c, f, dx0, dy0) {
  let depart = null;
  // Le décalage est mémorisé et envoyé dès le glissement, sans attendre la fin du geste : sur iPad Safari,
  // pointerup / pointercancel peuvent ne pas arriver, et la correction revenait alors en place à la sortie du mode.
  const suivre = (e) => {
    const dx = dx0 + (e.clientX - depart.x) / zoom, dy = dy0 + (e.clientY - depart.y) / zoom;
    const premiere = f.zones[0];
    c.style.left = premiere.x0 + dx + "px"; c.style.top = premiere.y0 - 13 + dy + "px";
    fr.decalages[f.id] = [Math.round(dx * 10) / 10, Math.round(dy * 10) / 10];
    sauverDecisions(f.id, { decalage: fr.decalages[f.id] });
  };
  c.addEventListener("pointerdown", (e) => {
    e.preventDefault(); e.stopPropagation(); c.setPointerCapture(e.pointerId);
    depart = { x: e.clientX, y: e.clientY };
  });
  c.addEventListener("pointermove", (e) => { if (depart) suivre(e); });
  const fin = () => {
    if (!depart) return;
    depart = null;
    const d = fr.decalages[f.id];
    if (d) deplacer(f.id, d[0], d[1]); // petit décalage : retiré; sinon redessine
  };
  for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) c.addEventListener(type, fin);
}

// Faute au milieu de la zone visible du PDF. Les positions viennent du DOM (page de taille fixe,
// même si son canvas n'est pas encore rendu) et du zoom courant.
function centrerFaute(f) {
  const z = f.zones[0];
  if (!z) return;
  const f0 = fenetre.getBoundingClientRect(), p = pages[z.page - 1].el.getBoundingClientRect();
  const x = p.left - f0.left + fenetre.scrollLeft + ((z.x0 + z.x1) / 2) * zoom;
  const y = p.top - f0.top + fenetre.scrollTop + ((z.y0 + z.y1) / 2) * zoom;
  fenetre.scrollTo({ left: Math.max(0, x - fenetre.clientWidth / 2), top: Math.max(0, y - fenetre.clientHeight / 2) });
}
// Attend que la mise en page se stabilise (le panneau peut changer la largeur, donc le zoom).
const centrerApres = (f) => requestAnimationFrame(() => requestAnimationFrame(() => centrerFaute(f)));

window.recentrerSelection = () => { const f = fr?.fautes.find((x) => x.id === selection); if (f) centrerFaute(f); };

// Tap sur une faute : ouvre sa fiche (appelé par lecteur.js).
window.surToucher = (pg, p) => {
  if (!fr) return;
  const marge = 4;
  const f = fr.fautes.find((f) => f.zones.some((z) => z.page === pg.numero && p.x >= z.x0 - marge && p.x <= z.x1 + marge && p.y >= z.y0 - marge && p.y <= z.y1 + marge));
  if (f) ouvrirFiche(f.id);
};

// ----- lexique global : un mot d'orthographe refusé et ignoré aux prochaines analyses -----
const REGLES_ORTHOGRAPHE = ["FR_SPELLING_RULE", "MORFOLOGIK_RULE_FR_FR"];
async function ajouterAuLexique(f) {
  const r = await fetch("/api/francais/lexique", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mot: f.texte }),
  });
  if (!r.ok) { etatFr(await erreurFr(r), true); return; }
  etatFr(`« ${f.texte} » ajouté au lexique : ignoré aux prochaines analyses.`);
  decider(f.id, "refusee");
}

// ----- mode « Déplacer » (bouton du rail et bouton de la fiche) -----
function majDeplacer() {
  const b = $("o-deplacer");
  b.disabled = selection === null;
  b.classList.toggle("on", deplacement);
  b.setAttribute("aria-pressed", String(deplacement));
}
function basculerDeplacement() {
  if (selection === null) return;
  deplacement = !deplacement; envoiFr.envoyer(); afficherFiche(); afficherCouches();
}
$("o-deplacer").onclick = basculerDeplacement;

// ----- fiche d'une faute -----
// centrer : amène la faute au milieu du PDF (depuis la liste, ou au passage à la suivante).
function ouvrirFiche(id, centrer) {
  if (id !== selection) { deplacement = false; autreOuvert = false; }
  selection = id;
  window.Inspecteur?.ouvrir("francais", { minimum: "moyen" });
  afficherFiche(); afficherCouches(); afficherListe(true);
  const f = fr?.fautes.find((x) => x.id === id);
  if (centrer && f) centrerApres(f);
}
function fermerFiche() { selection = null; deplacement = false; autreOuvert = false; afficherFiche(); afficherCouches(); afficherListe(); }
function afficherFiche() {
  const d = $("detail"), f = fr?.fautes.find((x) => x.id === selection);
  majDeplacer();
  if (!fr?.analyse) { d.hidden = true; return; }
  d.hidden = false;
  d.classList.toggle("vide-fiche", !f);
  if (!f) {
    const reste = fr.fautes.filter((x) => !decisionDe(x)).length;
    d.replaceChildren(el("span", !fr.fautes.length ? "Aucune faute détectée." : reste ? "Touchez une faute dans la liste ou sur le PDF." : "Toutes les fautes sont traitées."));
    return;
  }
  const courante = correctionDe(f), decision = decisionDe(f);
  const i = fr.fautes.indexOf(f), n = fr.fautes.length;
  const aller = (delta) => () => { const x = fr.fautes[(i + delta + n) % n]; ouvrirFiche(x.id, true); };
  const tete = el("div", undefined, "fiche-tete");
  const btnIco = (nom, libelle, surClic) => {
    const b = el("button", undefined, "btn-ico"); b.type = "button";
    b.setAttribute("aria-label", libelle); b.title = libelle; b.append(icone(nom)); b.onclick = surClic; return b;
  };
  const nav = el("span", undefined, "groupe");
  nav.append(btnIco("chevron-up", "Faute précédente", aller(-1)), btnIco("chevron-down", "Faute suivante", aller(1)), btnIco("x", "Fermer la fiche", fermerFiche));
  tete.append(el("span", `${i + 1} sur ${n} · p. ${f.zones[0]?.page ?? "?"}`), nav);

  const mot = el("div", undefined, "fiche-mot");
  mot.append(el("del", f.texte));
  if (courante) { const fl = icone("arrow-right"); fl.classList.add("fleche"); mot.append(fl, el("span", courante, "hw")); }
  else mot.append(el("span", "aucune correction proposée", "hw sans"));
  const msg = el("p", f.message, "fiche-msg");
  if (f.source === "claude") {
    const p = el("span", undefined, "pastille p-claude"); p.append(icone("sparkles"), "Repérée par Claude");
    msg.append(p);
  }

  const sugg = el("div", undefined, "sug");
  const choix = [...f.suggestions];
  if (courante && !choix.includes(courante)) choix.push(courante); // correction libre déjà saisie
  const puce = (texte, actif, surClic) => {
    const b = el("button", texte, "puce"); b.type = "button"; b.setAttribute("aria-pressed", String(actif)); b.onclick = surClic; return b;
  };
  for (const s of choix) sugg.append(puce(s, s === courante, () => choisirCorrection(f.id, s)));
  const autre = puce("Autre…", false, () => { autreOuvert = !autreOuvert; focusAutre = autreOuvert; afficherFiche(); });
  autre.setAttribute("aria-expanded", String(autreOuvert));
  sugg.append(autre);
  if (autreOuvert) {
    const rangee = el("div", undefined, "autre");
    const champ = el("input", undefined, "saisie"); champ.type = "text"; champ.maxLength = 60; champ.placeholder = "Votre correction";
    champ.setAttribute("aria-label", "Correction libre");
    const ok = el("button", "OK", "btn"); ok.type = "button";
    const valider = () => { const t = champ.value.trim(); if (!t) return; autreOuvert = false; choisirCorrection(f.id, t); };
    ok.onclick = valider;
    champ.onkeydown = (e) => { if (e.key === "Enter") valider(); };
    rangee.append(champ, ok); sugg.append(rangee);
    if (focusAutre) setTimeout(() => champ.focus(), 0);
    focusAutre = false;
  }

  const boutons = el("div", undefined, "decision");
  const refuser = el("button", undefined, "btn"), accepter = el("button", undefined, "btn primaire");
  for (const [b, valeur, nom, libelle] of [[refuser, "refusee", "x", "Refuser"], [accepter, "acceptee", "check", "Accepter"]]) {
    const prise = decision === valeur;
    b.type = "button"; b.setAttribute("aria-pressed", String(prise));
    b.title = prise ? "Toucher pour revenir à « à trancher »" : "";
    b.append(icone(nom), prise ? (valeur === "acceptee" ? "Acceptée" : "Refusée") : libelle);
    b.onclick = () => trancher(f, valeur);
    boutons.append(b);
  }

  const outils = el("div", undefined, "fiche-outils");
  const outil = (libelle, surClic, pressed, complet) => {
    const b = el("button", libelle, "btn tertiaire"); b.type = "button"; b.onclick = surClic;
    if (complet) b.setAttribute("aria-label", complet);
    if (pressed !== undefined) b.setAttribute("aria-pressed", String(pressed));
    outils.append(b);
  };
  const cache = fr.masquees.includes(f.id);
  outil(cache ? "Remettre" : "Effacer", () => masquer(f.id, !cache), undefined, cache ? "Remettre la correction écrite" : "Effacer la correction écrite");
  outil(deplacement ? "Fin du déplacement" : "Déplacer", basculerDeplacement, deplacement, deplacement ? "Fin du déplacement de la correction" : "Déplacer la correction");
  if (fr.decalages?.[f.id]) outil("Remettre en place", () => deplacer(f.id, 0, 0));
  if (REGLES_ORTHOGRAPHE.includes(f.regle) && !/\s/.test(f.texte)) outil("Ajouter au lexique", () => ajouterAuLexique(f));
  d.replaceChildren(tete, mot, msg, sugg, boutons, outils);
}

// ----- panneau Français -----
function resume() {
  const analyse = !!fr?.analyse;
  $("fr-vide").hidden = !fr || analyse; $("fr-synthese").hidden = !analyse;
  $("fr-compact").hidden = !analyse;
  $("francais").classList.toggle("non-analyse", !analyse);
  if (!analyse) { $("fr-tout-accepter").hidden = true; $("n-francais").hidden = true; return; }
  const acceptees = Object.values(fr.decisions).filter((v) => v === "acceptee").length;
  const refusees = Object.values(fr.decisions).filter((v) => v === "refusee").length;
  const reste = fr.fautes.length - acceptees - refusees;
  const b = fr.bareme;
  const penalite = fr.penalite ? `−${nombre(fr.penalite)} pt` : "0 pt";
  $("fr-pen").textContent = penalite;
  $("fr-plaf").textContent = b.plafond == null ? "sans plafond" : `/ plafond ${nombre(b.plafond)}`;
  $("fr-comptes").textContent = `${pluriel(acceptees, "acceptée")} · ${pluriel(refusees, "refusée")} · ${reste} à trancher`;
  $("fr-compact").textContent = `${penalite}${b.plafond == null ? "" : " / plafond " + nombre(b.plafond)} · ${reste} à trancher`;
  $("fr-bareme-resume").textContent = `${nombre(b.points_par_faute)} par faute, ${b.plafond == null ? "sans plafond" : "plafond " + nombre(b.plafond)}`;
  $("fr-tout-accepter").hidden = !reste;
  $("fr-tout-accepter").textContent = `Accepter les ${reste} fautes à trancher`.replace("les 1 fautes", "la faute");
  $("n-francais").textContent = fr.fautes.length; $("n-francais").hidden = false;
}
function afficherListe(versSelection) {
  const zone = $("fr-liste"), defilement = zone.scrollTop;
  zone.replaceChildren();
  if (!fr) return;
  let ligneChoisie = null;
  const groupes = new Map(); // nom de catégorie -> fautes, dans l'ordre de CATEGORIES puis « Autres »
  for (const [, nom] of [...CATEGORIES, [null, "Autres"]]) groupes.set(nom, []);
  for (const f of fr.fautes) groupes.get(nomCategorie(f)).push(f);
  for (const [nom, fautes] of groupes) {
    if (!fautes.length) continue;
    zone.append(el("div", `${nom} · ${fautes.length}`, "cat"));
    for (const f of fautes) {
      const decision = decisionDe(f);
      const ligne = el("button", undefined, "fl " + (decision === "acceptee" ? "fait" : decision === "refusee" ? "fait refusee" : "a-trancher") + (f.id === selection ? " sel" : ""));
      ligne.type = "button";
      if (f.id === selection) { ligne.setAttribute("aria-current", "true"); ligneChoisie = ligne; }
      const etat = icone(decision === "acceptee" ? "circle-check" : decision === "refusee" ? "x" : "circle-dot"); etat.classList.add("etat");
      const c = correctionDe(f);
      ligne.append(etat, el("span", `« ${f.texte} »${c ? " → " + c : ""}`, "t"));
      if (f.source === "claude") { const s = icone("sparkles", "s"); s.classList.add("claude"); ligne.title = "Repérée par Claude"; ligne.append(s); }
      ligne.append(el("span", `p. ${f.zones[0]?.page ?? "?"}`, "p"));
      ligne.onclick = () => ouvrirFiche(f.id, true);
      zone.append(ligne);
    }
  }
  zone.scrollTop = defilement; // les décisions rebâtissent la liste : on reste où on était
  if (versSelection && ligneChoisie) ligneChoisie.scrollIntoView({ block: "nearest" });
}
function afficherTout() {
  $("fr-points").value = fr?.bareme.points_par_faute ?? "";
  $("fr-plafond").value = fr?.bareme.plafond ?? "";
  if (fr?.analyse && fr.claude && !fr.claude.ok) etatFr(`Passe Claude non faite (LanguageTool seulement) : ${fr.claude.erreur?.message ?? "erreur"} Relancer l'analyse plus tard.`, true);
  else if (fr?.analyse) etatFr(fr.claude?.ajoutees ? `Claude : ${pluriel(fr.claude.ajoutees, "faute")} ajoutée${fr.claude.ajoutees > 1 ? "s" : ""}.` : "");
  else etatFr("");
  resume(); afficherListe(); afficherCouches(); afficherFiche();
}

// État résumé pour la fenêtre « Terminé… » (navigation-lecteur.js).
window.etatFrancais = () => {
  if (!fr?.analyse) return null;
  const acceptees = Object.values(fr.decisions).filter((v) => v === "acceptee").length;
  const refusees = Object.values(fr.decisions).filter((v) => v === "refusee").length;
  return { penalite: fr.penalite, plafond: fr.bareme.plafond, acceptees, refusees, aTrancher: fr.fautes.length - acceptees - refusees };
};

async function lancerAnalyse() {
  const boutons = [$("fr-analyser"), $("fr-relancer")];
  for (const b of boutons) b.disabled = true;
  etatFr("Analyse en cours…");
  try {
    if (!(await viderDecisions())) return; // l'analyse remplace l'état affiché
    const r = await fetch(URL_FRANCAIS + "/analyser", { method: "POST" });
    if (!r.ok) { etatFr(await erreurFr(r), true); return; }
    fr = await r.json(); fr.decalages ??= {}; selection = null; deplacement = false; afficherTout();
  } catch { etatFr("Moteur injoignable.", true); }
  finally { for (const b of boutons) b.disabled = false; }
}
$("fr-analyser").onclick = lancerAnalyse;
$("fr-relancer").onclick = lancerAnalyse;
$("fr-tout-accepter").onclick = () => {
  const ids = fr.fautes.filter((f) => !decisionDe(f)).map((f) => f.id);
  for (const id of ids) { fr.decisions[id] = "acceptee"; sauverDecisions(id, { decision: "acceptee" }); }
  afficherTout();
  UI.toast(`${pluriel(ids.length, "faute")} acceptée${ids.length > 1 ? "s" : ""}`, {
    action: { libelle: "Annuler", surClic: () => { for (const id of ids) { delete fr.decisions[id]; sauverDecisions(id, { decision: null }); } afficherTout(); } },
  });
};
async function sauverBareme() {
  if (!(await viderDecisions())) return; // le rechargement qui suit ne doit pas écraser des décisions pas encore confirmées
  const plafond = $("fr-plafond").value;
  const r = await fetch(URL_BAREME, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points_par_faute: +$("fr-points").value || 0, plafond: plafond === "" ? null : +plafond }),
  });
  if (!r.ok) { etatFr(await erreurFr(r), true); return; }
  await chargerFrancais();
}
$("fr-points").onchange = sauverBareme; $("fr-plafond").onchange = sauverBareme;

// Les pages sont créées par lecteur.js après le chargement du PDF : on attend qu'elles existent.
if (!ref.some((v) => !v)) (function attendre() { if (pages.length) chargerFrancais(); else setTimeout(attendre, 200); })();
