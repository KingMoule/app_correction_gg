// Écran du plagiat : énoncé, comparaison locale, paires à confirmer, verdict de Claude.
const API = "/api/plagiat";
const $ = (id) => document.getElementById(id);
let courant = null; // clé de la paire affichée
let minuteur = null;
let suiviComparaison = null;
const BAS_MAX = 100; // lignes affichées sous le seuil (la bibliothèque grossit : on borne le DOM)

function texte(tag, contenu, classe) {
  const el = document.createElement(tag);
  el.textContent = contenu; // textContent : le texte des rapports n'est jamais interprété comme du HTML
  if (classe) el.className = classe;
  return el;
}

async function erreurApi(r) {
  const d = await r.json().catch(() => ({}));
  return typeof d.detail === "string" ? d.detail : `Erreur ${r.status}`;
}

const pct = (x) => `${Math.round(x * 100)} %`;
const STATUTS = {
  a_confirmer: "À confirmer", sous_seuil: "Sous le seuil", en_cours: "Claude analyse…",
  ecartee: "Écartée", analysee: "Analysée", erreur: "Erreur",
};
const VERDICTS = { copie: "Copie", paraphrase: "Paraphrase", coincidence: "Coïncidence" };
const CONFIANCES = { faible: "faible", moyenne: "moyenne", elevee: "élevée" };
const nomRapport = (r) => `${r.nom} · ${r.cours} gr. ${r.groupe} · ${r.lab}`;

// Pastille d'état d'une paire : bleu-vert = plagiat (avis rendu), neutre = écartée ou sous le seuil, ambre = à confirmer,
// étincelles = Claude (l'outil) au travail, rouge = erreur bloquante seulement.
function badge(p) {
  const v = p.resultat?.verdict;
  const classe = v ? "p-plagiat" : { sous_seuil: "p-neutre", ecartee: "p-neutre", en_cours: "p-claude", erreur: "p-erreur" }[p.statut] || "";
  const b = texte("span", "", `pastille ${classe}`);
  if (p.statut === "en_cours") b.append(UI.icone("sparkles"));
  b.append(document.createTextNode(v ? `Avis : ${VERDICTS[v].toLowerCase()}` : STATUTS[p.statut]));
  return b;
}

const metaPaire = (p) => (p.a.cours === p.b.cours && p.a.lab === p.b.lab
  ? `${p.a.lab} · ${p.a.groupe === p.b.groupe ? "même groupe" : "groupes différents"}`
  : `${p.a.cours} ${p.a.lab} ↔ ${p.b.cours} ${p.b.lab}`);

function ligne(p) {
  const el = texte("button", "", "pl-paire" + (p.statut === "ecartee" ? " ecartee" : "") + (p.cle === courant ? " on" : ""));
  el.type = "button";
  el.dataset.cle = p.cle;
  const l1 = texte("div", "", "l1"), l2 = texte("div", "", "l2");
  const noms = texte("span", `${p.a.nom} ↔ ${p.b.nom}`, "noms");
  noms.title = `${nomRapport(p.a)} / ${nomRapport(p.b)}`;
  l1.append(noms, texte("b", pct(p.score), "score"));
  l2.append(texte("span", metaPaire(p), "meta"), badge(p));
  el.append(l1, l2);
  el.onclick = () => ouvrir(p.cle);
  return el;
}

async function charger() {
  const r = await fetch(`${API}/paires`);
  const d = await r.json();
  $("seuil").value = Math.round(d.seuil * 100);
  const hauts = d.paires.filter((p) => p.statut !== "sous_seuil");
  const bas = d.paires.filter((p) => p.statut === "sous_seuil");
  $("pl-compte").textContent = hauts.length ? `${hauts.length} paire(s) ≥ ${Math.round(d.seuil * 100)} %` : "Paires à vérifier";
  $("paires").replaceChildren(...(hauts.length ? hauts.map(ligne) : [texte("p", d.paires.length
    ? "Aucune paire au-dessus du seuil." : "Aucune comparaison pour l'instant.", "aide pl-vide-liste")]));
  $("paires-basses").replaceChildren(...bas.slice(0, BAS_MAX).map(ligne));
  if (bas.length > BAS_MAX) {
    $("paires-basses").append(texte("p", `${bas.length - BAS_MAX} autre(s) paire(s) plus faibles non affichées (monter le seuil d'affichage pour les cacher toutes).`, "aide"));
  }
  $("sous-seuil").hidden = !bas.length;
  if (courant) await afficherDetail(courant);
  const attente = d.paires.some((p) => p.statut === "en_cours");
  clearTimeout(minuteur);
  if (attente) minuteur = setTimeout(charger, 3000);
}

const afficherPanneau = (vide) => { $("detail").hidden = vide; $("detail-vide").hidden = !vide; };

async function ouvrir(cle) {
  courant = cle;
  for (const b of document.querySelectorAll(".pl-paire")) b.classList.toggle("on", b.dataset.cle === cle);
  await afficherDetail(cle);
  if (matchMedia("(max-width: 900px)").matches) $("detail").scrollIntoView({ behavior: "smooth" }); // en portrait, le détail est sous la liste
}

async function afficherDetail(cle) {
  const r = await fetch(`${API}/paires/${cle}`);
  if (!r.ok) { courant = null; afficherPanneau(true); return; }
  const p = await r.json();
  afficherPanneau(false);
  $("detail-titre").textContent = `${p.a.nom} ↔ ${p.b.nom}`;
  $("detail-resume").textContent =
    `Score ${pct(p.score)} (${pct(p.couverture_a)} du rapport de ${p.a.nom}, ${pct(p.couverture_b)} de celui de ${p.b.nom}) · ` +
    `${p.nb_passages} passage(s) commun(s) · ${nomRapport(p.a)} / ${nomRapport(p.b)}`;

  const actions = $("detail-actions");
  actions.replaceChildren();
  if (p.statut !== "en_cours") {
    if (p.statut !== "ecartee") {
      const ecarter = texte("button", "Écarter la paire", "btn"); ecarter.type = "button";
      ecarter.onclick = async () => {
        await fetch(`${API}/paires/${p.cle}/ecarter`, { method: "POST" });
        await charger();
        UI.toast("Paire écartée");
      };
      actions.append(ecarter);
    }
    const envoyer = texte("button", "", "btn primaire"); envoyer.type = "button";
    envoyer.append(UI.icone("sparkles"), document.createTextNode(p.statut === "analysee" ? "Refaire l'analyse par Claude…" : "Demander l'avis de Claude…"));
    envoyer.onclick = () => confirmer(p);
    actions.append(envoyer);
  }

  const verdict = $("detail-verdict");
  verdict.replaceChildren();
  if (p.statut === "en_cours") verdict.append(texte("p", "Claude analyse cette paire…"));
  if (p.statut === "ecartee") verdict.append(texte("p", "Paire écartée."));
  if (p.statut === "erreur") {
    const e = texte("p", "", "erreur-claude");
    e.append(UI.icone("circle-alert"), document.createTextNode(`Claude n'a pas pu répondre : ${p.resultat.erreur}`));
    verdict.append(e);
  }
  if (p.statut === "analysee") {
    const r = p.resultat;
    const l1 = texte("div", "", "l1");
    l1.append(badge(p), texte("span", `confiance ${CONFIANCES[r.confiance] || r.confiance}`, "mu"));
    verdict.append(l1, texte("p", r.explication), texte("p", "Indice pour t'aider à trancher, pas un verdict.", "aide"));
  }

  // Passages appariés et numérotés : le même numéro des deux côtés
  const zone = $("detail-passages");
  zone.replaceChildren();
  for (const [i, ps] of p.passages.entries()) {
    const bloc = texte("div", "", "passage");
    const tete = texte("div", "", "passage-tete");
    tete.append(texte("span", String(i + 1), "num-pass"), texte("span", `Passage ${i + 1} sur ${p.passages.length} · ${ps.mots} mots`));
    const cotes = texte("div", "", "cotes");
    const cote = (nom, passage) => {
      const g = texte("div", ""), m = texte("mark", "");
      m.append(texte("sup", String(i + 1)), document.createTextNode(passage));
      g.append(texte("h4", nom), m);
      return g;
    };
    cotes.append(cote(p.a.nom, ps.texte_a), cote(p.b.nom, ps.texte_b));
    bloc.append(tete, cotes);
    zone.append(bloc);
  }
}

async function confirmer(p) {
  const ok = await Dialogue.confirmer({
    titre: "Envoyer les passages à Claude ?",
    texte: `Seuls les ${p.nb_passages} passage(s) communs partent, ` +
      "avec les noms, prénoms et DA de la classe remplacés par [NOM], [PRÉNOM] et [DA]. " +
      "Ni le rapport entier ni son nom de fichier ne partent.\n\n" +
      "L'analyse compte dans la limite d'usage de ton forfait.",
    ok: "Envoyer", annuler: "Annuler" });
  if (!ok) return;
  const r = await fetch(`${API}/paires/${p.cle}/confirmer`, { method: "POST" });
  if (!r.ok) { UI.toast(await erreurApi(r), { erreur: true }); return; }
  await charger();
}

const ETAPES = {
  lecture: "Lecture des PDF", indexation: "Recherche des passages communs",
  paires: "Comparaison des paires", ecriture: "Enregistrement",
};

function texteComparaison(d) {
  if (d.etat === "en_cours") {
    const pas = d.total ? ` ${d.fait} / ${d.total}` : "";
    return `Comparaison en cours : ${ETAPES[d.etape] || d.etape}${pas}. Tu peux changer d'écran, elle continue.`;
  }
  if (d.etat === "termine") {
    return `${d.rapports} rapport(s) comparés, ${d.paires} paire(s) gardées en ${d.duree} s.` +
      (d.illisibles?.length ? ` Illisibles : ${d.illisibles.join(", ")}.` : "");
  }
  if (d.etat === "erreur") return `La comparaison a échoué : ${d.erreur}`;
  return "";
}

// Suit la comparaison en arrière-plan (une relance côté moteur arrête la précédente).
async function suivreComparaison() {
  clearTimeout(suiviComparaison);
  let d;
  try {
    d = await (await fetch(`${API}/comparer/etat`)).json();
  } catch (e) {
    suiviComparaison = setTimeout(suivreComparaison, 2000); // moteur injoignable un instant : on réessaie
    return;
  }
  $("etat-comparaison").textContent = texteComparaison(d);
  const prog = d.etat === "en_cours";
  $("pl-prog").hidden = !prog;
  if (prog) {
    $("pl-prog-texte").textContent = `Comparaison : ${ETAPES[d.etape] || d.etape}`;
    $("pl-prog-num").textContent = d.total ? `${d.fait} / ${d.total}` : "";
    $("pl-prog-barre").max = d.total || 1; $("pl-prog-barre").value = d.fait || 0;
  }
  if (d.etat === "en_cours") {
    suiviComparaison = setTimeout(suivreComparaison, 700);
  } else if (d.etat === "termine") {
    await charger();
  }
}

$("comparer").onclick = async () => {
  const pour = Number($("seuil").value);
  await fetch(`${API}/reglages`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seuil: Math.min(100, Math.max(0, pour)) / 100 }),
  });
  courant = null;
  afficherPanneau(true);
  const r = await fetch(`${API}/comparer`, { method: "POST" });
  if (!r.ok) { $("etat-comparaison").textContent = await erreurApi(r); return; }
  $("etat-comparaison").textContent = "Comparaison lancée…";
  await suivreComparaison();
};

$("seuil").onchange = async () => {
  await fetch(`${API}/reglages`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seuil: Math.min(100, Math.max(0, Number($("seuil").value))) / 100 }),
  });
  await charger();
};

$("enonce-envoyer").onclick = async () => {
  const fichier = $("enonce-fichier").files[0];
  const lab = $("enonce-lab").value.trim();
  if (!$("enonce-cours").value || !lab || !fichier) {
    $("enonce-etat").textContent = "Choisir le cours, indiquer le lab et sélectionner le PDF de l'énoncé.";
    return;
  }
  const form = new FormData();
  form.append("pdf", fichier);
  const r = await fetch(`${API}/enonces/${encodeURIComponent($("enonce-cours").value)}/${encodeURIComponent(lab)}`, { method: "POST", body: form });
  $("enonce-etat").textContent = r.ok
    ? "Énoncé enregistré : relancer la comparaison pour l'appliquer."
    : await erreurApi(r);
  if (r.ok) UI.toast("Énoncé enregistré");
  if (r.ok) $("enonce-fichier").value = "";
};

async function charger_cours() {
  const arbre = await (await fetch("/api/bibliotheque")).json();
  const cours = [...new Set(arbre.map((c) => c.cours))];
  $("enonce-cours").replaceChildren(...cours.map((c) => { const o = texte("option", c); o.value = c; return o; }));
  // Arrivée depuis la bibliothèque : cours et lab déjà choisis pour l'énoncé
  const q = new URLSearchParams(location.search);
  if (cours.includes(q.get("cours"))) $("enonce-cours").value = q.get("cours");
  if (q.get("lab")) $("enonce-lab").value = q.get("lab");
  if (q.get("cours") || q.get("lab")) $("enonce-bloc").open = true;
}

$("ic-pl-avert").append(UI.icone("info"));
$("ic-pl-vide").append(UI.icone("scan-search"));
$("ic-pl-enonce").append(UI.icone("file-text"));
charger_cours().catch(() => {});
charger().catch(() => {});
suivreComparaison().catch(() => {}); // reprend l'affichage d'une comparaison déjà en cours
