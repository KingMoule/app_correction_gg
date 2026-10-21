// Fautes de français sur le PDF : surlignage rouge, correction manuscrite effaçable,
// acceptation/refus de chaque faute, barème du cours. Dépend de lecteur.js (pages, base, ref, $).
'use strict';

const URL_FRANCAIS = `/api/francais/rapport/${base}`;
const URL_BAREME = `/api/francais/bareme/${encodeURIComponent(ref[0] || "")}`;
let fr = null;        // état renvoyé par le moteur : fautes (id stable), revision, decisions, choix, masquees, decalages, penalite, bareme
let selection = null; // id de la faute ouverte dans la fiche
let deplacement = false; // mode « Déplacer » actif pour la faute ouverte

const el = (tag, texte, classe) => {
  const e = document.createElement(tag);
  if (texte !== undefined) e.textContent = texte; // textContent : le texte du rapport n'est jamais interprété comme du HTML
  if (classe) e.className = classe;
  return e;
};
const correctionDe = (f) => fr.choix[f.id] ?? f.suggestions[0] ?? null;
const decisionDe = (f) => fr.decisions[f.id];
const nombre = (n) => String(Math.round(n * 100) / 100).replace(".", ",");

async function erreurFr(r) { const d = await r.json().catch(() => ({})); return d.detail || `Erreur ${r.status}`; }
function etatFr(texte, erreur) { $("fr-etat").textContent = texte; $("fr-etat").classList.toggle("erreur", !!erreur); }

async function chargerFrancais() {
  const r = await fetch(URL_FRANCAIS);
  if (!r.ok) return;
  fr = await r.json();
  fr.decalages ??= {};
  afficherTout();
}

// ----- sauvegarde des décisions (envoi-francais.js : un PATCH par lot de fautes changées, renvoyé tant que le moteur ne confirme pas) -----
function indicateurFr(texte, erreur) {
  const e = $("fr-sauvegarde");
  e.textContent = "Français : " + texte;
  e.classList.toggle("erreur", !!erreur);
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
    $("francais").hidden = false;
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

// ----- couche sur les pages -----
function coucheDe(pg) {
  if (!pg.couche) { pg.couche = el("div", undefined, "fautes"); pg.el.append(pg.couche); }
  return pg.couche;
}
function afficherCouches() {
  for (const pg of pages) coucheDe(pg).replaceChildren();
  if (!fr) return;
  for (const f of fr.fautes) {
    if (decisionDe(f) === "refusee") continue;
    const correction = correctionDe(f), premiere = f.zones[0];
    for (const z of f.zones) {
      const d = el("div", undefined, "zone" + (decisionDe(f) === "acceptee" ? " acceptee" : "") + (f.id === selection ? " choisie" : ""));
      Object.assign(d.style, { left: z.x0 + "px", top: z.y0 + "px", width: z.x1 - z.x0 + "px", height: z.y1 - z.y0 + "px" });
      coucheDe(pages[z.page - 1]).append(d);
    }
    if (correction && premiere && !fr.masquees.includes(f.id)) {
      const c = el("span", correction, "correction");
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

// ----- fiche d'une faute -----
function ouvrirFiche(id) { if (id !== selection) deplacement = false; selection = id; $("francais").hidden = false; afficherFiche(); afficherCouches(); }
function fermerFiche() { selection = null; deplacement = false; $("detail").hidden = true; afficherCouches(); }
function afficherFiche() {
  const f = fr?.fautes.find((x) => x.id === selection);
  if (!f) { $("detail").hidden = true; return; }
  const d = $("detail"), courante = correctionDe(f);
  d.replaceChildren(el("div", `« ${f.texte} » : ${f.message}${f.source === "claude" ? " (repérée par Claude)" : ""}`));
  const sugg = el("div", undefined, "rangee");
  for (const s of f.suggestions) {
    const b = el("button", s, s === courante ? "on" : "");
    b.onclick = () => choisirCorrection(f.id, s);
    sugg.append(b);
  }
  if (!f.suggestions.length) sugg.append(el("span", "Aucune suggestion"));
  const rangee = el("div", undefined, "rangee");
  for (const [valeur, libelle] of [["acceptee", "✓ Accepter"], ["refusee", "✗ Refuser"], [undefined, "À trancher"]]) {
    const b = el("button", libelle, (valeur === "acceptee" ? "ok " : valeur === "refusee" ? "non " : "") + (decisionDe(f) === valeur ? "on" : ""));
    b.onclick = () => decider(f.id, valeur);
    rangee.append(b);
  }
  const cache = fr.masquees.includes(f.id);
  const bascule = el("button", cache ? "Remettre la correction écrite" : "Effacer la correction écrite");
  bascule.onclick = () => masquer(f.id, !cache);
  const fermer = el("button", "Fermer");
  fermer.onclick = fermerFiche;
  const dep = el("button", deplacement ? "Fin du déplacement" : "Déplacer la correction", deplacement ? "on" : "");
  dep.onclick = () => { deplacement = !deplacement; envoiFr.envoyer(); afficherFiche(); afficherCouches(); };
  rangee.append(bascule, dep);
  if (fr.decalages?.[f.id]) {
    const remise = el("button", "Remettre en place");
    remise.onclick = () => deplacer(f.id, 0, 0);
    rangee.append(remise);
  }
  rangee.append(fermer);
  if (REGLES_ORTHOGRAPHE.includes(f.regle) && !/\s/.test(f.texte)) {
    const lex = el("button", "Ajouter au lexique");
    lex.onclick = () => ajouterAuLexique(f);
    rangee.append(lex);
  }
  d.append(sugg, rangee);
  d.hidden = false;
}

// ----- panneau Français -----
function resume() {
  if (!fr?.analyse) { $("fr-resume").textContent = ""; return; }
  const acceptees = Object.values(fr.decisions).filter((v) => v === "acceptee").length;
  const refusees = Object.values(fr.decisions).filter((v) => v === "refusee").length;
  const reste = fr.fautes.length - acceptees - refusees;
  const b = fr.bareme;
  $("fr-resume").textContent =
    `${fr.fautes.length} fautes : ${acceptees} acceptées, ${refusees} refusées, ${reste} à trancher. ` +
    `Pénalité : ${nombre(fr.penalite)} point(s) (${nombre(b.points_par_faute)} par faute` +
    (b.plafond == null ? ", sans plafond)" : `, plafond ${nombre(b.plafond)})`);
}
function afficherListe() {
  const zone = $("fr-liste");
  zone.replaceChildren();
  if (!fr) return;
  for (const f of fr.fautes) {
    const refusee = decisionDe(f) === "refusee";
    const ligne = el("div", undefined, "fr-ligne" + (refusee ? " refusee" : ""));
    const texte = el("div", undefined, "texte");
    texte.append(el("span", `p. ${f.zones[0]?.page ?? "?"} · ${f.source === "claude" ? "[Claude] " : ""}« ${f.texte} »${correctionDe(f) ? " → " + correctionDe(f) : ""}`), el("small", f.message));
    texte.onclick = () => {
      ouvrirFiche(f.id);
      // Attend que la mise en page se stabilise (le panneau peut changer la largeur, donc le zoom).
      requestAnimationFrame(() => requestAnimationFrame(() => centrerFaute(f)));
    };
    const ok = el("button", "✓", "ok" + (decisionDe(f) === "acceptee" ? " on" : ""));
    ok.onclick = () => decider(f.id, decisionDe(f) === "acceptee" ? undefined : "acceptee");
    const non = el("button", "✗", "non" + (refusee ? " on" : ""));
    non.onclick = () => decider(f.id, refusee ? undefined : "refusee");
    ligne.append(texte, ok, non);
    zone.append(ligne);
  }
}
function afficherTout() {
  $("fr-analyser").textContent = fr?.analyse ? "Relancer l'analyse" : "Analyser le français";
  $("fr-tout-accepter").hidden = !fr?.analyse;
  $("fr-points").value = fr?.bareme.points_par_faute ?? "";
  $("fr-plafond").value = fr?.bareme.plafond ?? "";
  if (fr?.analyse && fr.claude && !fr.claude.ok) etatFr(`Passe Claude non faite (LanguageTool seulement) : ${fr.claude.erreur?.message ?? "erreur"} Relancer l'analyse plus tard.`, true);
  else if (fr?.analyse) etatFr(fr.claude ? `Claude : ${fr.claude.ajoutees} faute(s) ajoutée(s).` : (fr.fautes.length ? "" : "Aucune faute détectée."));
  else etatFr("Rapport pas encore analysé.");
  resume(); afficherListe(); afficherCouches();
  if (selection !== null) afficherFiche();
}

$("francais-bouton").onclick = () => { $("francais").hidden = !$("francais").hidden; };
if (params.get("panneau") === "francais") $("francais").hidden = false; // ouvert depuis le bouton « Français » de la bibliothèque
$("fr-analyser").onclick = async () => {
  $("fr-analyser").disabled = true; etatFr("Analyse en cours…");
  try {
    if (!(await viderDecisions())) { $("fr-analyser").disabled = false; return; } // l'analyse remplace l'état affiché
    const r = await fetch(URL_FRANCAIS + "/analyser", { method: "POST" });
    if (!r.ok) { etatFr(await erreurFr(r), true); return; }
    fr = await r.json(); fr.decalages ??= {}; selection = null; deplacement = false; $("detail").hidden = true; afficherTout();
  } catch { etatFr("Moteur injoignable.", true); }
  finally { $("fr-analyser").disabled = false; }
};
$("fr-tout-accepter").onclick = () => {
  for (const f of fr.fautes) if (!decisionDe(f)) { fr.decisions[f.id] = "acceptee"; sauverDecisions(f.id, { decision: "acceptee" }); }
  afficherTout();
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
