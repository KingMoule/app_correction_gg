// Écran du plagiat : énoncé, comparaison locale, paires à confirmer, verdict de Claude.
const API = "/api/plagiat";
const $ = (id) => document.getElementById(id);
let courant = null; // clé de la paire affichée
let minuteur = null;

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

function badge(p) {
  const v = p.resultat?.verdict;
  const b = texte("span", v ? VERDICTS[v] : STATUTS[p.statut], `badge ${v || (p.statut === "erreur" ? "erreur" : "")}`);
  return b;
}

function ligne(p) {
  const el = texte("div", "", "paire");
  el.append(texte("span", pct(p.score), "score"));
  const noms = texte("div", "", "noms");
  noms.append(texte("div", nomRapport(p.a)), texte("div", nomRapport(p.b)));
  el.append(noms, badge(p));
  const voir = texte("button", "Voir");
  voir.onclick = () => ouvrir(p.cle);
  el.append(voir);
  return el;
}

async function charger() {
  const r = await fetch(`${API}/paires`);
  const d = await r.json();
  $("seuil").value = Math.round(d.seuil * 100);
  const hauts = d.paires.filter((p) => p.statut !== "sous_seuil");
  const bas = d.paires.filter((p) => p.statut === "sous_seuil");
  $("paires").replaceChildren(...(hauts.length ? hauts.map(ligne) : [texte("p", d.paires.length
    ? "Aucune paire au-dessus du seuil." : "Aucune comparaison pour l'instant.")]));
  $("paires-basses").replaceChildren(...bas.map(ligne));
  $("sous-seuil").hidden = !bas.length;
  if (courant) await afficherDetail(courant);
  const attente = d.paires.some((p) => p.statut === "en_cours");
  clearTimeout(minuteur);
  if (attente) minuteur = setTimeout(charger, 3000);
}

async function ouvrir(cle) {
  courant = cle;
  await afficherDetail(cle);
  $("detail").scrollIntoView({ behavior: "smooth" });
}

async function afficherDetail(cle) {
  const r = await fetch(`${API}/paires/${cle}`);
  if (!r.ok) { courant = null; $("detail").hidden = true; return; }
  const p = await r.json();
  $("detail").hidden = false;
  $("detail-titre").textContent = `${p.a.nom} et ${p.b.nom}`;
  $("detail-resume").textContent =
    `Score ${pct(p.score)} (${pct(p.couverture_a)} du rapport de ${p.a.nom}, ${pct(p.couverture_b)} de celui de ${p.b.nom}) · ` +
    `${p.nb_passages} passage(s) commun(s) · ${nomRapport(p.a)} / ${nomRapport(p.b)}`;

  const actions = $("detail-actions");
  actions.replaceChildren();
  if (p.statut !== "en_cours") {
    const envoyer = texte("button", p.statut === "analysee" ? "Refaire l'analyse par Claude" : "Confirmer et envoyer à Claude");
    envoyer.onclick = () => confirmer(p);
    actions.append(envoyer);
    if (p.statut !== "ecartee") {
      const ecarter = texte("button", "Écarter");
      ecarter.onclick = async () => { await fetch(`${API}/paires/${p.cle}/ecarter`, { method: "POST" }); await charger(); };
      actions.append(ecarter);
    }
  }

  const verdict = $("detail-verdict");
  verdict.replaceChildren();
  if (p.statut === "en_cours") verdict.append(texte("p", "Claude analyse cette paire…"));
  if (p.statut === "ecartee") verdict.append(texte("p", "Paire écartée."));
  if (p.statut === "erreur") verdict.append(texte("p", `Claude n'a pas pu répondre : ${p.resultat.erreur}`, "erreur"));
  if (p.statut === "analysee") {
    const r = p.resultat;
    verdict.append(badge(p), texte("span", ` confiance ${CONFIANCES[r.confiance] || r.confiance}`),
      texte("p", r.explication),
      texte("p", "Indice pour t'aider à trancher, pas un verdict.", "aide"));
  }

  const zone = $("detail-passages");
  zone.replaceChildren();
  for (const [i, ps] of p.passages.entries()) {
    const bloc = texte("div", "", "passage");
    bloc.append(texte("strong", `Passage ${i + 1} · ${ps.mots} mots`));
    const cotes = texte("div", "", "cotes");
    const ga = texte("div", ""), gb = texte("div", "");
    ga.append(texte("h4", p.a.nom), texte("span", ps.texte_a));
    gb.append(texte("h4", p.b.nom), texte("span", ps.texte_b));
    cotes.append(ga, gb);
    bloc.append(cotes);
    zone.append(bloc);
  }
}

async function confirmer(p) {
  const ok = confirm(
    `Envoyer cette paire à Claude ?\n\nSeuls les ${p.nb_passages} passage(s) communs partent, sans nom d'étudiant. ` +
    "L'analyse compte dans la limite d'usage de ton forfait.");
  if (!ok) return;
  const r = await fetch(`${API}/paires/${p.cle}/confirmer`, { method: "POST" });
  if (!r.ok) { alert(await erreurApi(r)); return; }
  await charger();
}

$("comparer").onclick = async () => {
  const pour = Number($("seuil").value);
  await fetch(`${API}/reglages`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ seuil: Math.min(100, Math.max(0, pour)) / 100 }),
  });
  $("etat-comparaison").textContent = "Comparaison en cours…";
  courant = null;
  $("detail").hidden = true;
  const r = await fetch(`${API}/comparer`, { method: "POST" });
  if (!r.ok) { $("etat-comparaison").textContent = await erreurApi(r); return; }
  const d = await r.json();
  const suspectes = d.paires.filter((p) => p.statut === "a_confirmer").length;
  $("etat-comparaison").textContent =
    `${d.rapports} rapport(s) comparés, ${suspectes} paire(s) au-dessus du seuil.` +
    (d.illisibles.length ? ` Illisibles : ${d.illisibles.join(", ")}.` : "");
  await charger();
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
  if (r.ok) $("enonce-fichier").value = "";
};

async function charger_cours() {
  const arbre = await (await fetch("/api/bibliotheque")).json();
  const cours = [...new Set(arbre.map((c) => c.cours))];
  $("enonce-cours").replaceChildren(...cours.map((c) => { const o = texte("option", c); o.value = c; return o; }));
}

charger_cours().catch(() => {});
charger().catch(() => {});
