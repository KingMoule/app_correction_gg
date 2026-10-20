// Fautes de français sur le PDF : surlignage rouge, correction manuscrite effaçable,
// acceptation/refus de chaque faute, barème du cours. Dépend de lecteur.js (pages, base, ref, $).
'use strict';

const URL_FRANCAIS = `/api/francais/rapport/${base}`;
const URL_BAREME = `/api/francais/bareme/${encodeURIComponent(ref[0] || "")}`;
let fr = null;        // état renvoyé par le moteur : fautes, decisions, choix, masquees, penalite, bareme
let selection = null; // id de la faute ouverte dans la fiche

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
  afficherTout();
}

// ----- sauvegarde des décisions -----
let minuterieFr = null;
async function envoyerDecisions() {
  minuterieFr = null;
  const r = await fetch(URL_FRANCAIS, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decisions: fr.decisions, choix: fr.choix, masquees: fr.masquees }),
  });
  if (!r.ok) { etatFr(await erreurFr(r), true); return; }
  const d = await r.json();
  fr.nb_acceptees = d.nb_acceptees; fr.penalite = d.penalite;
  resume();
}
function sauverDecisions() { clearTimeout(minuterieFr); minuterieFr = setTimeout(envoyerDecisions, 300); }
async function viderDecisions() { if (minuterieFr) { clearTimeout(minuterieFr); await envoyerDecisions(); } }
function decider(id, valeur) {
  if (valeur) fr.decisions[id] = valeur; else delete fr.decisions[id];
  sauverDecisions(); afficherTout();
}
function choisirCorrection(id, texte) { fr.choix[id] = texte; sauverDecisions(); afficherTout(); }
function masquer(id, masque) {
  fr.masquees = fr.masquees.filter((m) => m !== id);
  if (masque) fr.masquees.push(id);
  sauverDecisions(); afficherTout();
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
      Object.assign(c.style, { left: premiere.x0 + "px", top: premiere.y0 - 13 + "px" });
      coucheDe(pages[premiere.page - 1]).append(c);
    }
  }
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
function ouvrirFiche(id) { selection = id; afficherFiche(); afficherCouches(); }
function fermerFiche() { selection = null; $("detail").hidden = true; afficherCouches(); }
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
    const b = el("button", libelle, decisionDe(f) === valeur ? "on" : "");
    b.onclick = () => decider(f.id, valeur);
    rangee.append(b);
  }
  const cache = fr.masquees.includes(f.id);
  const bascule = el("button", cache ? "Remettre la correction écrite" : "Effacer la correction écrite");
  bascule.onclick = () => masquer(f.id, !cache);
  const fermer = el("button", "Fermer");
  fermer.onclick = fermerFiche;
  rangee.append(bascule, fermer);
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
      const z = f.zones[0];
      if (z) pages[z.page - 1].el.scrollIntoView({ block: "start" });
    };
    const ok = el("button", "✓", decisionDe(f) === "acceptee" ? "on" : "");
    ok.onclick = () => decider(f.id, decisionDe(f) === "acceptee" ? undefined : "acceptee");
    const non = el("button", "✗", refusee ? "on" : "");
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
    const r = await fetch(URL_FRANCAIS + "/analyser", { method: "POST" });
    if (!r.ok) { etatFr(await erreurFr(r), true); return; }
    fr = await r.json(); selection = null; $("detail").hidden = true; afficherTout();
  } catch { etatFr("Moteur injoignable.", true); }
  finally { $("fr-analyser").disabled = false; }
};
$("fr-tout-accepter").onclick = () => {
  for (const f of fr.fautes) if (!decisionDe(f)) fr.decisions[f.id] = "acceptee";
  sauverDecisions(); afficherTout();
};
async function sauverBareme() {
  await viderDecisions(); // le rechargement qui suit ne doit pas écraser des décisions pas encore envoyées
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
