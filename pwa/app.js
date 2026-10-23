// Point d'entrée de la PWA : accueil, page Labs, import. La navigation et l'état du moteur sont dans coque.js.

// --- Bibliothèque et import ---
const API = "/api/bibliotheque";
const $ = (id) => document.getElementById(id);
const enc = encodeURIComponent;
let arbre = [];
let sessionEtat = { courante: null, sessions: [] }; // GET /api/bibliotheque/sessions : l'accueil et Labs montrent la session en cours
let attente = [];
let suivis = new Map(); // « cours|lab » -> réponse de /api/suivi (comptes, rapports, export), chargée après la bibliothèque
let pairesAConfirmer = 0;

function texte(tag, contenu, classe) {
  const el = document.createElement(tag);
  el.textContent = contenu; // textContent : les noms de fichiers ne sont jamais interprétés comme du HTML
  if (classe) el.className = classe;
  return el;
}

const icone = (nom, classes) => UI.icone(nom, classes);
const pastille = (libelle, classe = "") => texte("span", libelle, ("pastille " + classe).trim());
const pluriel = (n, un, plusieurs) => `${n} ${n > 1 ? plusieurs : un}`;

function bouton(libelle, { icone: nom, classe = "", titre, surClic } = {}) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = ("btn " + classe).trim();
  if (nom) b.append(icone(nom));
  b.append(libelle);
  if (titre) b.title = titre;
  if (surClic) b.onclick = surClic;
  return b;
}

function lien(libelle, href, { icone: nom, classe = "", titre } = {}) {
  const a = document.createElement("a");
  a.className = ("btn " + classe).trim();
  if (nom) a.append(icone(nom));
  a.append(libelle);
  a.href = href;
  if (titre) a.title = titre;
  return a;
}

async function erreurApi(r) {
  const d = await r.json().catch(() => ({}));
  return d.detail || `Erreur ${r.status}`;
}

// --- Aides communes ---
let enonces = [];
const stockage = {
  lire(cle, defaut) { try { return localStorage.getItem(cle) ?? defaut; } catch { return defaut; } },
  ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch { /* sans stockage : tout reste replié */ } },
};

// Session en cours par défaut; les sessions passées restent consultables sous Labs (lecture seule, hors lot et « À faire »).
const courant = () => arbre.filter((c) => !sessionEtat.courante || c.session === sessionEtat.courante);
const passees = () => arbre.filter((c) => sessionEtat.courante && c.session !== sessionEtat.courante);
const nomCours = (cle) => UI.titreCours(cle);

function labFini(c, lab) {
  const avec = c.etudiants.filter((e) => e.labs.includes(lab));
  return c.labs_archives.includes(lab) || (avec.length > 0 && avec.every((e) => e.termines.includes(lab)));
}

// Un lab = un cours + un nom de lab, tous groupes confondus.
function resumeLabs(classes = courant()) {
  const parLab = new Map();
  for (const c of classes) {
    for (const lab of new Set(c.etudiants.flatMap((e) => e.labs))) {
      const cle = `${c.cours}|${lab}`;
      const u = parLab.get(cle) ?? { cours: c.cours, lab, classes: [], total: 0, faits: 0, fini: true };
      u.classes.push(c);
      u.total += c.etudiants.filter((e) => e.labs.includes(lab)).length;
      u.faits += c.etudiants.filter((e) => e.termines.includes(lab)).length;
      u.fini = u.fini && labFini(c, lab);
      parLab.set(cle, u);
    }
  }
  return [...parLab.values()].sort((a, b) => a.cours.localeCompare(b.cours, "fr") || a.lab.localeCompare(b.lab, "fr", { numeric: true }));
}

// Équipe d'un rapport : retirer ou ajouter un coéquipier (étudiants du cours), enregistré tout de suite.
function editerEquipe(cours, groupe, lab, etudiant, equipe, apres) {
  const zone = texte("div", "", "equipe-edition");
  const rendre = (membres) => {
    zone.replaceChildren(texte("strong", "Équipe"));
    if (!membres.length) zone.append(texte("p", "Aucun coéquipier.", "aide"));
    for (const m of membres) {
      const l = texte("div", "", "membre");
      l.append(texte("span", `${m.prenom} ${m.nom} (groupe ${m.groupe})`));
      l.append(bouton("Retirer", { icone: "x", classe: "tertiaire", surClic: () => enregistrer(membres.filter((x) => x !== m)) }));
      zone.append(l);
    }
    const choix = document.createElement("select");
    choix.className = "saisie";
    choix.setAttribute("aria-label", "Ajouter un coéquipier");
    choix.append(texte("option", "Ajouter un coéquipier…"));
    const deja = new Set(membres.map((m) => `${m.groupe}/${m.id}`));
    for (const g of arbre.filter((x) => x.cours === cours)) {
      for (const x of g.etudiants.filter((y) => !y.retire && !deja.has(`${g.groupe}/${y.id}`) && !(g.groupe === groupe && y.id === etudiant))) {
        const o = texte("option", `${x.nom}, ${x.prenom} (groupe ${g.groupe})`);
        o.value = JSON.stringify({ id: x.id, groupe: g.groupe, nom: x.nom, prenom: x.prenom });
        choix.append(o);
      }
    }
    choix.onchange = () => { if (choix.value) enregistrer([...membres, JSON.parse(choix.value)]); };
    zone.append(choix);
  };
  const enregistrer = async (membres) => {
    const r = await fetch(`${API}/equipe/${[cours, groupe, lab, etudiant].map(encodeURIComponent).join("/")}`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ equipe: membres.map((m) => ({ groupe: m.groupe, id: m.id })) }) });
    if (!r.ok) { alert(await erreurApi(r)); return; }
    rendre((await r.json()).equipe);
    await apres?.();
  };
  rendre(equipe);
  return zone;
}

// Ouvre ou ferme le panneau d'équipe sous une ligne.
function basculerEquipe(ligne, creer) {
  if (ligne.nextElementSibling?.classList.contains("equipe-edition")) ligne.nextElementSibling.remove();
  else ligne.after(creer());
}

function etatVideBibliotheque() {
  const v = texte("div", "", "vide carte");
  v.append(icone("library"), texte("h2", "Ta bibliothèque est vide"),
    texte("p", "Commence par la liste de classe exportée d'Omnivox ou de LÉA, puis importe les PDF d'un lab."),
    bouton("Importer une liste de classe", { icone: "upload", classe: "primaire", surClic: () => aller("importer") }));
  return v;
}

async function charger() {
  arbre = await (await fetch(API)).json();
  enonces = await (await fetch("/api/plagiat/enonces")).json().catch(() => []);
  sessionEtat = (await fetchJson(`${API}/sessions`)) ?? sessionEtat;
  rendreLabs();
  rendreAccueil();
  rendreEnoncesManquants();
  const cours = [...new Set([...courant(), ...passees()].map((c) => c.cours))]; // la session en cours d'abord
  const choisi = $("choix-cours").value;
  $("choix-cours").replaceChildren(...cours.map((c) => { const o = texte("option", nomCours(c)); o.value = c; return o; }));
  if (cours.includes(choisi)) $("choix-cours").value = choisi;
  rendreChoixSession();
  $("choix-cours").onchange = remplirGroupes;
  remplirGroupes();
  rendreClassesChargees();
  window.rafraichirLot?.(arbre); // l'écran « Analyse par lot » de #outils (retiré par la PR D)
  window.Coque?.labs(courant());
  await chargerAttente();
  rendreEtapes();
  chargerSuivis(); // sans attendre : l'accueil se complète (À faire, export) quand les réponses arrivent
}

// Une requête de suivi par lab pas archivé (comptes, rapports, export), plus le plagiat, Claude et « Reprendre ».
// Échec silencieux : l'accueil s'en passe. L'aperçu du lot conseillé de chaque lab arrive en dernier.
let chargementSuivis = 0;
async function chargerSuivis() {
  const tour = ++chargementSuivis;
  const labs = resumeLabs().filter((u) => !u.classes.every((c) => c.labs_archives.includes(u.lab)));
  const [reponses, paires, conso, rep] = await Promise.all([
    Promise.all(labs.map(async (u) => [cleLab(u), await fetchJson(`/api/suivi/${enc(u.cours)}/${enc(u.lab)}`)])),
    fetchJson("/api/plagiat/paires"),
    fetchJson("/api/consommation"),
    fetchJson("/api/reprendre"),
  ]);
  if (tour !== chargementSuivis) return; // un rechargement plus récent est passé devant
  suivis = new Map(reponses.filter((x) => x[1]?.rapports));
  pairesAConfirmer = (paires?.paires ?? []).filter((p) => p.statut === "a_confirmer").length;
  consoEtat = conso;
  const d = rep?.dernier;
  reprise = d ? { url: `lecteur.html?${new URLSearchParams({ cours: d.cours, groupe: d.groupe, lab: d.lab, etudiant: d.etudiant, nom: `${d.prenom} ${d.nom}` })}`,
    nom: `${d.prenom} ${d.nom}`, cours: d.cours, groupe: d.groupe, lab: d.lab } : repriseLocale();
  apercus = new Map();
  rendreAccueil();
  rendreLabs();
  const taille = conso?.lot_conseille ?? 10;
  await Promise.all(labs.filter((u) => !u.fini && suivis.has(cleLab(u))).map(async (u) => {
    const restants = suivis.get(cleLab(u)).rapports.filter((r) => !r.analyse).length;
    if (!restants) return;
    const n = Math.min(taille, restants);
    const a = await fetchJson(`/api/lot/apercu/${enc(u.cours)}/${enc(u.lab)}?n=${n}`);
    if (a && tour === chargementSuivis && a.a_analyser > 0) {
      apercus.set(cleLab(u), { n: Math.min(n, a.a_analyser), pct: a.estimation?.pct ?? 0, depasse: !!a.estimation?.depasse, a_analyser: a.a_analyser });
    }
  }));
  if (tour === chargementSuivis) rendreAccueil();
}

function remplirGroupes() {
  const tous = texte("option", "Tous les groupes");
  tous.value = "";
  const groupes = arbre.filter((c) => c.cours === $("choix-cours").value).map((c) => {
    const o = texte("option", `Groupe ${c.groupe}`);
    o.value = c.groupe;
    return o;
  });
  $("choix-groupe").replaceChildren(tous, ...groupes);
  const seg = $("seg-groupe");
  seg.replaceChildren(...[...$("choix-groupe").options].map((o, i) => {
    const b = texte("button", i === 0 ? "Tous" : o.value);
    b.type = "button";
    b.dataset.valeur = o.value;
    b.className = i === 0 ? "on" : "";
    b.setAttribute("aria-pressed", String(i === 0));
    return b;
  }));
  $("aide-groupe").hidden = false;
  majLabsConnus();
}

UI.segmente($("seg-groupe"), (b) => { $("choix-groupe").value = b.dataset.valeur; });

// Labs déjà connus du cours choisi, proposés dans le champ « Lab » (on peut toujours en écrire un nouveau).
function majLabsConnus() {
  const labs = new Set(arbre.filter((c) => c.cours === $("choix-cours").value).flatMap((c) => c.etudiants.flatMap((e) => e.labs)));
  $("labs-connus").replaceChildren(...[...labs].sort().map((l) => { const o = document.createElement("option"); o.value = l; return o; }));
}

// --- À trancher ---
const RAISONS_LONGUES = {
  ambigu: "Plusieurs étudiants possibles",
  aucune_correspondance: "Aucun nom reconnu",
  deja_importe: "Rapport déjà importé pour ce lab (le remplacer ?)",
  da_inconnu: "N° de DA absent des listes de classe, aucun nom reconnu",
};

async function chargerAttente() {
  attente = await (await fetch(`${API}/attente`)).json();
  const liste = attente;
  $("section-attente").hidden = !liste.length;
  $("badge-attente").hidden = !liste.length;
  $("badge-attente").textContent = liste.length;
  const zone = $("attente");
  zone.replaceChildren();
  for (const item of liste) {
    const classes = arbre.filter((c) => c.cours === item.cours && (!item.groupe || c.groupe === item.groupe));
    const ligne = texte("div", "", "attente-item");
    const tete = texte("div", "", "attente-tete");
    tete.append(icone("file-text"), texte("b", item.fichier, "nom"), pastille(RAISONS_LONGUES[item.raison] ?? item.raison));
    const contexte = texte("p", `${nomCours(item.cours)} · ${item.lab}${item.da ? ` · DA ${item.da}` : ""}`, "aide");
    const choix = document.createElement("select");
    choix.className = "saisie";
    choix.setAttribute("aria-label", `Étudiant pour ${item.fichier}`);
    const vide = texte("option", "Choisir un étudiant…");
    vide.value = "";
    choix.append(vide);
    const proposes = item.candidats.length ? item.candidats
      : classes.flatMap((c) => c.etudiants.map((e) => ({ ...e, groupe: c.groupe })));
    for (const e of proposes) {
      const o = texte("option", `${e.nom}, ${e.prenom} (groupe ${e.groupe})`);
      o.value = JSON.stringify([e.id, e.groupe]);
      choix.append(o);
    }
    const ok = bouton("Ranger", { icone: "check", classe: "primaire", surClic: () => {
      const [etudiant, groupe] = choix.value ? JSON.parse(choix.value) : [];
      const existe = etudiant && arbre.some((c) => c.cours === item.cours && c.groupe === groupe
        && c.etudiants.some((e) => e.id === etudiant && e.labs.includes(item.lab)));
      if (existe && !confirm("Cet étudiant a déjà un rapport pour ce lab. Remplacer ? Les corrections de l'ancien rapport "
        + "(annotations, fautes, statut, note) seront mises de côté dans le dossier _remplaces (récupérable) "
        + "et le nouveau rapport repartira à neuf.")) return;
      trancher(item.id, choix.value ? JSON.parse(choix.value) : "", existe);
    } });
    const non = bouton("Écarter", { icone: "archive", classe: "danger", surClic: () => {
      if (confirm("Écarter ce fichier ? Il sera mis de côté dans le dossier _ecartes (récupérable).")) trancher(item.id, null);
    } });
    const actions = texte("div", "", "attente-actions");
    actions.append(choix, ok, non);
    ligne.append(tete, contexte, actions);
    zone.append(ligne);
  }
}

async function trancher(id, choix, remplacer = false) {
  if (choix === "") return;
  const [etudiant, groupe] = choix ?? [null, null];
  const r = await fetch(`${API}/attente/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ etudiant, groupe, remplacer }),
  });
  if (r.ok) UI.toast(choix ? "Rapport rangé" : "Fichier écarté (dossier _ecartes)");
  else alert(await erreurApi(r));
  await charger();
}

// --- Import de la liste de classe ---
async function importerClasse(fichier) {
  if (!fichier) return;
  const form = new FormData();
  form.append("fichier", fichier);
  const session = $("session-classe").value.trim().toUpperCase();
  if (!/^[AH]\d{4}$/.test(session)) { alert("Indique la session de cette liste : A (automne) ou H (hiver) et l'année, par exemple A2026."); return; }
  form.append("session", session);
  const r = await fetch(`${API}/classes`, { method: "POST", body: form });
  if (!r.ok) alert(await erreurApi(r));
  else afficherRecapClasse(await r.json());
  await charger();
}
UI.depot($("depot-classe"), (fichiers) => importerClasse(fichiers[0]));

function rendreClassesChargees() {
  const zone = $("classes-chargees");
  zone.replaceChildren();
  for (const c of arbre) {
    const actifs = c.etudiants.filter((e) => !e.retire).length;
    const retires = c.etudiants.length - actifs;
    const li = document.createElement("li");
    li.append(icone("circle-check"), texte("b", nomCours(c.cours)), texte("span", `groupe ${c.groupe} · ${pluriel(actifs, "étudiant", "étudiants")}`));
    if (retires) li.append(texte("span", pluriel(retires, "retiré", "retirés"), "mu"));
    zone.append(li);
  }
  zone.hidden = !arbre.length;
}

function afficherRecapClasse(classe) {
  const m = classe.recap;
  const zone = $("resultat-classe");
  const conflits = m.conflits.length;
  const ban = texte("div", "", "banniere " + (conflits ? "attention" : "ok"));
  ban.setAttribute("role", "status");
  const corps = texte("div", "", "corps");
  corps.append(texte("b", `Liste ${nomCours(classe.cours)} groupe ${classe.groupe} : ${pluriel(m.ajoutes.length, "ajouté", "ajoutés")}, ${m.inchanges + m.mis_a_jour.length} inchangé(s), ${m.retires.length} retiré(s), ${conflits} à trancher`));
  const liste = document.createElement("ul");
  const ligne = (titre, noms) => { if (noms.length) liste.append(texte("li", `${titre} : ${noms.join(", ")}`)); };
  ligne("Ajoutés", m.ajoutes);
  ligne("Retirés de la liste (rapports gardés)", m.retires);
  ligne("Revenus", m.reactives);
  ligne("Mis à jour (nom ou DA)", m.mis_a_jour);
  for (const c of m.conflits) liste.append(texte("li", `À trancher, ${c.nom} : ${c.raison}`));
  if (liste.children.length) corps.append(liste);
  ban.append(icone(conflits ? "triangle-alert" : "circle-check"), corps);
  zone.replaceChildren(ban);
}

// --- Import des rapports PDF ---
let aImporter = []; // fichiers choisis, pas encore envoyés

const taille = (o) => (o < 1024 * 1024 ? `${Math.max(1, Math.round(o / 1024))} Ko` : `${(o / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`);

function rendreFichiersChoisis() {
  const liste = $("fichiers-liste");
  liste.replaceChildren();
  liste.hidden = !aImporter.length;
  aImporter.forEach((f, i) => {
    const li = document.createElement("li");
    const retirer = document.createElement("button");
    retirer.type = "button";
    retirer.className = "btn-ico";
    retirer.setAttribute("aria-label", `Retirer ${f.name}`);
    retirer.append(icone("x"));
    retirer.onclick = () => { aImporter.splice(i, 1); rendreFichiersChoisis(); };
    li.append(icone("file-text"), texte("span", f.name, "nom"), texte("span", taille(f.size), "taille"), retirer);
    liste.append(li);
  });
  $("barre-import").hidden = !aImporter.length;
  $("barre-resume").replaceChildren(texte("b", pluriel(aImporter.length, "fichier", "fichiers")), " prêt(s) à importer");
  $("importer-libelle").textContent = `Importer ${pluriel(aImporter.length, "rapport", "rapports")}`;
}

UI.depot($("depot-pdf"), (fichiers) => {
  const connus = new Set(aImporter.map((f) => `${f.name}|${f.size}`));
  for (const f of fichiers) if (!connus.has(`${f.name}|${f.size}`)) aImporter.push(f);
  $("resultat-import").replaceChildren();
  rendreFichiersChoisis();
});

$("annuler-import").onclick = () => { aImporter = []; rendreFichiersChoisis(); };

function messageImport(classe, titre, detail) {
  const ban = texte("div", "", "banniere " + classe);
  ban.setAttribute("role", classe === "erreur" ? "alert" : "status");
  const corps = texte("div", "", "corps");
  corps.append(texte("b", titre));
  if (detail) corps.append(" ", detail);
  ban.append(icone(classe === "erreur" ? "circle-alert" : classe === "ok" ? "circle-check" : "info"), corps);
  $("resultat-import").replaceChildren(ban);
}

$("importer").onclick = async () => {
  const cours = $("choix-cours").value;
  if (!cours || !$("lab").value.trim() || !aImporter.length) {
    messageImport("erreur", "Il manque une information.", "Choisir le cours, indiquer le lab et sélectionner des PDF.");
    return;
  }
  const form = new FormData();
  form.append("cours", cours);
  form.append("groupe", $("choix-groupe").value);
  form.append("lab", $("lab").value.trim());
  for (const f of aImporter) form.append("fichiers", f);
  $("importer").disabled = true;
  messageImport("", "Import en cours…");
  try {
    const r = await fetch(`${API}/import`, { method: "POST", body: form });
    if (!r.ok) { messageImport("erreur", "Import impossible.", await erreurApi(r)); return; }
    const d = await r.json();
    aImporter = [];
    rendreFichiersChoisis();
    afficherRecap(d);
    if (d.ranges.length) UI.toast(`${pluriel(d.ranges.length, "rapport importé", "rapports importés")} dans ${d.lab}`);
    await charger();
  } finally {
    $("importer").disabled = false;
  }
};

const RAISONS = {
  ambigu: "plusieurs étudiants possibles",
  aucune_correspondance: "aucun nom reconnu",
  da_inconnu: "DA absent des listes",
  deja_importe: "déjà importé pour ce lab",
};

// Résultat de l'import, une ligne par fichier : rangé (avec équipe modifiable), à trancher (avec la raison), refusé.
function afficherRecap(d) {
  const zone = $("resultat-import");
  const n = d.ranges.length + d.en_attente.length + d.refuses.length;
  const parties = [pluriel(d.ranges.length, "rangé", "rangés"), `${d.en_attente.length} à trancher`, pluriel(d.refuses.length, "refusé", "refusés")];
  const ban = texte("div", "", "banniere " + (d.refuses.length || d.en_attente.length ? "attention" : "ok"));
  ban.setAttribute("role", "status");
  const corps = texte("div", "", "corps");
  corps.append(texte("b", `${pluriel(n, "fichier", "fichiers")} : ${parties.join(" · ")}`));
  const groupes = Object.entries(d.par_groupe).map(([g, k]) => `groupe ${g} : ${k}`);
  if (groupes.length) corps.append(" ", `Rangés par ${groupes.join(", ")}.`);
  if (d.en_attente.length) corps.append(" ", "Les fichiers à trancher sont plus bas.");
  ban.append(icone(d.refuses.length || d.en_attente.length ? "triangle-alert" : "circle-check"), corps);

  const liste = texte("ul", "", "depot-liste resultat");
  const ligne = (nom, centre, etat) => {
    const li = document.createElement("li");
    li.append(icone("file-text"), texte("span", nom, "nom"));
    if (centre) li.append(centre);
    li.append(etat);
    liste.append(li);
    return li;
  };
  for (const x of d.ranges) {
    const centre = texte("span", `${x.etudiant.prenom} ${x.etudiant.nom}`, "etu");
    // Équipe détectée sur la page titre, à vérifier : modifiable pour chaque rapport rangé.
    centre.append(texte("small", x.equipe.length ? ` · équipe : ${x.equipe.map((c) => `${c.prenom} ${c.nom}`).join(", ")}` : " · seul(e)", "mu"));
    const etat = texte("span", "", "etat");
    const li = ligne(x.fichier, centre, etat);
    etat.append(pastille(`Rangé · groupe ${x.groupe}`, "p-fini"),
      bouton("Équipe", { icone: "users", classe: "tertiaire", titre: "Vérifier ou modifier l'équipe détectée",
        surClic: () => basculerEquipe(li, () => editerEquipe(d.cours, x.groupe, d.lab, x.etudiant.id, x.equipe, charger)) }));
  }
  for (const x of d.en_attente) ligne(x.fichier, null, pastille(`À trancher · ${RAISONS[x.raison] ?? x.raison}`));
  for (const x of d.refuses) ligne(x.fichier, null, pastille(`Refusé · ${x.raison}`, "p-erreur"));
  zone.replaceChildren(ban, liste);
}

// Étapes de l'import : liste de classe faite ou non, fichiers à trancher en attente.
function rendreEtapes() {
  const e1 = $("etape-1"), e3 = $("etape-3");
  const faite = arbre.length > 0;
  e1.classList.toggle("fait", faite);
  e1.classList.toggle("on", !faite);
  $("etape-2").classList.toggle("on", faite);
  e1.querySelector(".no").replaceChildren(faite ? icone("check") : "1");
  e3.classList.toggle("on", attente.length > 0);
  e3.lastChild.textContent = attente.length ? `À trancher (${attente.length})` : "À trancher";
}

// --- Navigation entre les vues et accueil ---
const VUES = ["accueil", "biblio", "importer", "outils"];

function aller(vue) {
  if (!VUES.includes(vue)) vue = "accueil";
  for (const v of VUES) $("v-" + v).hidden = v !== vue;
  window.Coque?.marquer(vue);
  if (location.hash !== "#" + vue) history.replaceState(null, "", "#" + vue);
  scrollTo(0, 0);
}
document.querySelectorAll("[data-go]").forEach((b) => { b.onclick = () => aller(b.dataset.go); });
window.onhashchange = () => aller(location.hash.slice(1));

// --- Titres, états et liens d'un lab ---
const titreLab = (lab) => window.Coque?.titreLab?.(lab) ?? lab;
const lienLab = (cours, lab) => `suivi.html?${new URLSearchParams({ cours, lab })}`;
const cleLab = (u) => `${u.cours}|${u.lab}`;
const aEnonce = (cours, lab) => enonces.some((x) => x.cours === cours && x.lab === lab);
const dateCourte = (iso) => new Date(iso).toLocaleDateString("fr-CA", { day: "numeric", month: "short" });
const nbMot = (n, un, plusieurs) => {
  const f = document.createDocumentFragment();
  f.append(texte("b", String(n)), ` ${n > 1 ? plusieurs : un}`);
  return f;
};
const fetchJson = (url) => fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null);

// Cellule État : barre à deux segments (terminés / analysés pas terminés) et les chiffres en mots.
// `suivi` = réponse de /api/suivi du lab (absente tant qu'elle n'est pas arrivée : on se rabat sur l'arbre).
function etatLab(u, suivi, deuxLignes) {
  const zone = texte("div", "", "etat-lab");
  const c = suivi?.compte;
  const recus = c ? c.recus : u.total;
  const termines = c ? c.termines : u.faits;
  const analysesSeules = suivi ? suivi.rapports.filter((r) => r.analyse && !r.termine).length : 0;
  const part = (n) => (recus ? `${((100 * n) / recus).toFixed(1)}%` : "0");
  const barre = texte("div", "", "barre2");
  barre.setAttribute("role", "img");
  barre.setAttribute("aria-label", `${termines} terminés et ${analysesSeules} analysés sur ${recus} reçus`);
  for (const [classe, n] of [["t", termines], ["a", analysesSeules]]) {
    const i = document.createElement("i");
    i.className = classe;
    i.style.width = part(n);
    barre.append(i);
  }
  const chiffres = texte("span", "", "chiffres");
  if (c) {
    chiffres.append(nbMot(termines, "terminé", "terminés"), " · ", nbMot(c.analyses, "analysé", "analysés"),
      deuxLignes ? document.createElement("br") : " / ", nbMot(recus, "reçu", "reçus"));
    if (c.non_remis) chiffres.append(" · ", `${pluriel(c.non_remis, "non remis", "non remis")}`);
  } else {
    chiffres.append(nbMot(termines, "terminé", "terminés"), " / ", nbMot(recus, "reçu", "reçus"));
  }
  zone.append(barre, chiffres);
  return zone;
}

// Dernier export LÉA d'un lab (connu seulement quand son suivi est chargé).
function celluleExport(u, suivi) {
  const zone = texte("div", "", "col-export");
  const x = suivi?.export;
  if (!x) { zone.append(texte("span", "—", "mu")); return zone; }
  if (x.statut === "perime") zone.append(pastille("Export à refaire"), texte("span", pluriel(x.modifies, "rapport modifié", "rapports modifiés"), "mu"));
  else if (x.statut === "a_jour") zone.append(pastille(`Exporté · ${dateCourte(x.date)}`, "p-fini"));
  else if (suivi.compte.termines) zone.append(pastille("Jamais exporté", "p-neutre"));
  else zone.append(texte("span", "—", "mu"));
  return zone;
}

function groupesDe(u) { return u.classes.map((c) => c.groupe).join(", "); }

// --- Page Labs : une carte par cours, une ligne par lab ---
function ligneLabPage(u) {
  const s = suivis.get(cleLab(u));
  const a = document.createElement("a");
  a.className = "p1-ligne";
  a.href = lienLab(u.cours, u.lab);
  a.setAttribute("aria-label", `Ouvrir ${titreLab(u.lab)} (${nomCours(u.cours)})`);
  const enonce = texte("span", "", "col-en");
  enonce.append(aEnonce(u.cours, u.lab) ? pastille("Énoncé", "p-fini") : pastille("Énoncé manquant"));
  const exp = texte("span", "", "col-ex");
  exp.append(celluleExport(u, s));
  a.append(texte("b", titreLab(u.lab), "lab-t"), etatLab(u, s, false), enonce, exp, icone("chevron-right", "chev"));
  return a;
}

function menuCours(bouton, cours) {
  UI.menu(bouton, [
    { libelle: "Barème du français…", icone: "spell-check", surClic: () => reglerBareme(cours) },
    { libelle: "Style des références…", icone: "library", surClic: () => reglerStyle(cours) },
    { separateur: true },
    { libelle: "Réimporter la liste de classe", icone: "file-up", surClic: () => { aller("importer"); $("carte-classe").scrollIntoView?.({ behavior: "smooth" }); } },
  ]);
}

const nombreFr = (v) => (v == null ? "" : String(v).replace(".", ","));
const lireNombre = (t) => { const v = t.trim().replace(",", "."); return v === "" ? null : Number(v); };

async function reglerBareme(cours) {
  const b = await fetchJson(`/api/francais/bareme/${enc(cours)}`);
  if (!b) { UI.toast("Barème introuvable : le moteur répond-il ?", { erreur: true }); return; }
  const f = await Dialogue.formulaire({
    titre: `Barème du français · ${nomCours(cours)}`, texte: "Vaut pour tout le cours : chaque faute acceptée retire ces points.",
    champs: [
      { cle: "points", etiquette: "Points par faute", valeur: nombreFr(b.points_par_faute), inputmode: "decimal" },
      { cle: "plafond", etiquette: "Plafond de la pénalité", valeur: nombreFr(b.plafond), inputmode: "decimal", aide: "Laisser vide : aucun plafond." },
    ],
  });
  if (!f) return;
  const points = lireNombre(f.points), plafond = lireNombre(f.plafond);
  if (points == null || Number.isNaN(points) || points < 0 || Number.isNaN(plafond) || (plafond != null && plafond < 0)) {
    UI.toast("Barème refusé : des nombres positifs seulement.", { erreur: true });
    return;
  }
  const r = await fetch(`/api/francais/bareme/${enc(cours)}`, { method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ points_par_faute: points, plafond }) });
  if (r.ok) UI.toast(`Barème de ${nomCours(cours)} enregistré`);
  else UI.toast(await erreurApi(r), { erreur: true });
}

async function reglerStyle(cours) {
  const s = await fetchJson(`/api/references/style/${enc(cours)}`);
  if (!s) { UI.toast("Style introuvable : le moteur répond-il ?", { erreur: true }); return; }
  const f = await Dialogue.formulaire({
    titre: `Style des références · ${nomCours(cours)}`, texte: "Vaut pour tout le cours : la forme des références est vérifiée selon ce style.",
    champs: [{ cle: "style", etiquette: "Style", valeur: s.style, options: Object.entries(s.styles).map(([valeur, libelle]) => ({ valeur, libelle })) }],
  });
  if (!f) return;
  const r = await fetch(`/api/references/style/${enc(cours)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style: f.style }) });
  if (r.ok) UI.toast(`Style de ${nomCours(cours)} : ${s.styles[f.style] ?? f.style}`);
  else UI.toast(await erreurApi(r), { erreur: true });
}

function ajouterLab(cours) {
  aller("importer");
  $("choix-cours").value = cours;
  remplirGroupes();
  $("lab").focus();
}

function carteCours(cours, classes, tous, passee) {
  const labs = tous.filter((u) => u.cours === cours);
  const carte = texte("section", "", "carte p1-cours");
  const tete = texte("div", "", "tc");
  const actifs = classes.reduce((n, c) => n + c.etudiants.filter((e) => !e.retire).length, 0);
  tete.append(texte("b", nomCours(cours)), texte("span", `gr. ${classes.map((c) => c.groupe).join(", ")} · ${pluriel(actifs, "inscrit", "inscrits")}`, "mu"),
    texte("span", "", "esp"));
  if (!passee) {
    const plus = document.createElement("button");
    plus.type = "button";
    plus.className = "btn-ico";
    plus.setAttribute("aria-label", `Réglages du cours ${nomCours(cours)} (barème, style des références, réimporter la liste)`);
    plus.append(icone("ellipsis"));
    menuCours(plus, cours);
    tete.append(bouton("Ajouter un lab", { icone: "upload", classe: "tertiaire", surClic: () => ajouterLab(cours) }), plus);
  }
  carte.append(tete);
  const enCours = labs.filter((u) => !u.fini), finis = labs.filter((u) => u.fini);
  if (!labs.length) carte.append(texte("p", "Aucun lab : « Ajouter un lab » importe les rapports d'un lab.", "p1-vide"));
  carte.append(...enCours.map(ligneLabPage));
  if (finis.length) {
    const d = document.createElement("details");
    d.className = "p1-finis";
    d.open = stockage.lire("finis:" + cours, "0") === "1";
    d.ontoggle = () => stockage.ecrire("finis:" + cours, d.open ? "1" : "0");
    const sm = document.createElement("summary");
    sm.append(icone("chevron-right", "chevron"), texte("span", `${pluriel(finis.length, "lab terminé", "labs terminés")} ou archivé${finis.length > 1 ? "s" : ""}`));
    d.append(sm, ...finis.map(ligneLabPage));
    carte.append(d);
  }
  return carte;
}

function rendreLabs() {
  const zone = $("labs-cours");
  zone.replaceChildren();
  const actuelles = courant(), anciennes = passees();
  const tous = resumeLabs(actuelles);
  const inscrits = actuelles.reduce((n, c) => n + c.etudiants.filter((e) => !e.retire).length, 0);
  const nCours = new Set(actuelles.map((c) => c.cours)).size;
  const session = sessionEtat.sessions.find((x) => x.courante);
  $("session-courante").textContent = session?.libelle ?? "Session";
  $("biblio-sous").textContent = arbre.length
    ? `${session ? `${session.libelle} · ` : ""}${pluriel(nCours, "cours", "cours")} · ${pluriel(tous.length, "lab", "labs")} · ${pluriel(inscrits, "inscrit", "inscrits")}`
    : "Aucune classe importée.";
  if (!arbre.length) { zone.append(etatVideBibliotheque()); return; }
  if (!actuelles.length) zone.append(texte("p", "Aucune liste de classe dans cette session : importe-en une (l'import propose la session en cours).", "p1-vide"));
  for (const [cours, classes] of Map.groupBy(actuelles, (c) => c.cours)) zone.append(carteCours(cours, classes, tous, false));
  if (!anciennes.length) return;
  // Sessions passées : repliées, consultables (page du lab, énoncé, export), hors lot et « À faire ».
  const d = document.createElement("details");
  d.className = "p1-finis p1-passees";
  d.open = stockage.lire("sessions-passees", "0") === "1";
  d.ontoggle = () => stockage.ecrire("sessions-passees", d.open ? "1" : "0");
  const sm = document.createElement("summary");
  const nSessions = new Set(anciennes.map((c) => c.session)).size;
  sm.append(icone("chevron-right", "chevron"), texte("span", `${pluriel(nSessions, "session passée", "sessions passées")} (archives)`));
  d.append(sm);
  const passe = resumeLabs(anciennes);
  for (const [session, classes] of Map.groupBy(anciennes, (c) => c.session ?? "")) {
    d.append(texte("h3", sessionEtat.sessions.find((x) => x.session === session)?.libelle ?? "Sans session", "p1-session"));
    for (const [cours, cc] of Map.groupBy(classes, (c) => c.cours)) d.append(carteCours(cours, cc, passe, true));
  }
  zone.append(d);
}

// Session proposée à l'import d'une liste : la session en cours, modifiable (A2026, H2027…).
function rendreChoixSession() {
  const sessions = new Set([sessionEtat.courante, ...sessionEtat.sessions.map((s) => s.session)].filter(Boolean));
  $("sessions-connues").replaceChildren(...[...sessions].map((v) => { const o = document.createElement("option"); o.value = v; return o; }));
  if (!$("session-classe").value) $("session-classe").value = sessionEtat.courante ?? "";
}

$("btn-session").onclick = async () => {
  const f = await Dialogue.formulaire({
    titre: "Session en cours", texte: "L'accueil, Labs et l'import proposent cette session. Les autres restent dans les archives de Labs.",
    champs: [{ cle: "session", etiquette: "Session", valeur: sessionEtat.courante ?? "", aide: "A = automne, H = hiver, puis l'année : A2026, H2027." }],
  });
  if (!f) return;
  const r = await fetch(`${API}/sessions/courante`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session: f.session }) });
  if (!r.ok) { UI.toast(await erreurApi(r), { erreur: true }); return; }
  $("session-classe").value = "";
  await charger();
};

// --- Accueil : « Le lab au centre » ---
let reprise = null;       // { url, nom, cours, groupe, lab } : celle du moteur, sinon le localStorage
let consoEtat = null;     // GET /api/consommation
let apercus = new Map();  // « cours|lab » -> { n, pct, depasse, a_analyser } : l'aperçu du lot conseillé
let lotActif = window.Coque?.lot?.statut === "en_cours";
let toastLot = null;

function repriseLocale() {
  try {
    const d = JSON.parse(localStorage.getItem("dernier"));
    return d?.url ? { url: d.url, nom: d.nom, cours: d.cours, groupe: d.groupe, lab: d.lab } : null;
  } catch { return null; }
}

function urlRapport(cours, lab, r) {
  return `lecteur.html?${new URLSearchParams({ cours, groupe: r.groupe, lab, etudiant: r.etudiant, nom: `${r.prenom} ${r.nom}` })}`;
}

// Prochain rapport à corriger : le premier analysé et pas terminé, dans l'ordre du suivi; à défaut le premier pas terminé.
function prochainRapport(suivi) {
  return suivi.rapports.find((r) => r.analyse && !r.termine) ?? suivi.rapports.find((r) => !r.termine) ?? null;
}

function rendreContinuer() {
  const zone = $("continuer");
  zone.replaceChildren();
  if (!reprise) {
    zone.append(texte("p", "Aucun rapport ouvert pour l'instant.", "vide-reprise"));
    return;
  }
  const tuile = texte("span", "", "tuile");
  tuile.append(icone("file-text", "l"));
  const corps = document.createElement("div");
  corps.append(texte("div", "Reprendre", "etq"), texte("div", reprise.nom || "Dernier rapport", "nom"),
    texte("div", `${titreLab(reprise.lab)} · ${nomCours(reprise.cours)} · gr. ${reprise.groupe}`, "mu"));
  zone.append(tuile, corps, lien("Reprendre", reprise.url, { icone: "arrow-right", classe: "primaire" }));
}

function rendreChiffres(enCours) {
  const lus = enCours.map((u) => suivis.get(cleLab(u))).filter(Boolean);
  const connu = lus.length > 0;
  const somme = (f) => lus.reduce((n, s) => n + s.rapports.filter(f).length, 0);
  $("chiffre-corriger").textContent = connu ? String(somme((r) => r.analyse && !r.termine)) : "–";
  $("chiffre-analyser").textContent = connu ? String(somme((r) => !r.analyse)) : "–";
  const c = consoEtat, lien = $("chiffre-claude");
  lien.hidden = !c;
  if (!c) return;
  const limite = c.limite, p = c.session.pct;
  $("claude-pct").textContent = limite ? "Limite atteinte" : `≈ ${Math.round(p)} %`;
  $("claude-sous").textContent = limite ? `Claude · reprise ${limite.reprise.slice(11, 16)}` : `Claude · lot conseillé : ${c.lot_conseille}`;
  const jauge = $("claude-jauge");
  jauge.className = "jauge " + (limite || p >= c.plafond_pct ? "danger" : p >= c.plafond_pct - 15 ? "attention" : "");
  jauge.querySelector("i").style.width = `${Math.min(100, limite ? 100 : p)}%`;
  jauge.querySelector("u").style.left = `${c.plafond_pct}%`;
}

// « À faire » : les exceptions seulement, en trois rubriques fixes (Bloquant, Revoir, Clore).
function exceptions(labs) {
  const liste = [];
  const lieu = (u) => `${titreLab(u.lab)} · ${nomCours(u.cours)}`;
  if (attente.length) {
    const lieux = [...new Set(attente.map((x) => `${titreLab(x.lab)} · ${nomCours(x.cours)}`))];
    liste.push({ rubrique: "Bloquant", icone: "upload", ton: "attention", titre: `${pluriel(attente.length, "fichier", "fichiers")} à associer`,
      lieu: lieux.length === 1 ? lieux[0] : pluriel(lieux.length, "lab", "labs"), detail: "choisir l'étudiant de chaque rapport", href: "#importer" });
  }
  if (pairesAConfirmer) {
    liste.push({ rubrique: "Revoir", icone: "scan-search", ton: "plagiat", titre: `${pluriel(pairesAConfirmer, "paire", "paires")} à regarder`,
      lieu: "", detail: "indices à revérifier, jamais un verdict", href: "plagiat.html" });
  }
  for (const u of labs.filter((x) => !x.fini)) {
    const s = suivis.get(cleLab(u));
    if (!s) continue;
    const manquants = s.rapports.filter((r) => !r.termine && r.francais.claude_manquant).length;
    if (manquants) {
      liste.push({ rubrique: "Revoir", icone: "sparkles", ton: "neutre", titre: `${manquants} « Claude manquant »`, lieu: lieu(u),
        detail: "passe à refaire", href: lienLab(u.cours, u.lab) });
    }
  }
  for (const u of labs) {
    const s = suivis.get(cleLab(u));
    if (!s || !s.total || u.classes.every((c) => c.labs_archives.includes(u.lab))) continue;
    if (s.export.statut === "perime") {
      liste.push({ rubrique: "Clore", icone: "file-down", ton: "attention", titre: "Export à refaire", lieu: lieu(u),
        detail: pluriel(s.export.modifies, "rapport modifié", "rapports modifiés"), href: lienLab(u.cours, u.lab) });
    } else if (s.export.statut === "jamais" && u.fini) {
      liste.push({ rubrique: "Clore", icone: "file-down", ton: "accent", titre: "Export à faire", lieu: lieu(u),
        detail: "lab terminé, jamais exporté pour LÉA", href: lienLab(u.cours, u.lab) });
    }
  }
  for (const u of labs.filter((x) => !x.fini)) {
    if (!aEnonce(u.cours, u.lab)) {
      liste.push({ rubrique: "Clore", icone: "file-text", ton: "neutre", titre: "Énoncé manquant", lieu: lieu(u),
        detail: "le plagiat le compterait", href: `plagiat.html?${new URLSearchParams({ cours: u.cours, lab: u.lab })}` });
    }
  }
  return liste;
}

function rendreAFaire(labs) {
  const liste = exceptions(labs);
  const rien = courant().length ? "Rien à faire : tout est à jour." : "Rien à faire : commence par importer une liste de classe.";
  const puces = $("faire-puces");
  puces.replaceChildren(texte("span", "À faire", "etq-faire"));
  const colonne = $("faire-colonne");
  colonne.replaceChildren();
  if (!liste.length) {
    puces.append(texte("span", rien, "rien"));
    const v = texte("p", rien, "vide-faire");
    v.prepend(icone("circle-check"));
    colonne.append(v);
    return;
  }
  for (const x of liste) {
    const tuile = () => { const t = texte("span", "", "tuile " + x.ton); t.append(icone(x.icone, "s")); return t; };
    const puce = document.createElement("a");
    puce.className = "puce-faire";
    puce.href = x.href;
    puce.append(tuile(), texte("b", x.titre));
    if (x.lieu) puce.append(texte("span", x.lieu, "mu"));
    puces.append(puce);
  }
  for (const rubrique of ["Bloquant", "Revoir", "Clore"]) {
    const items = liste.filter((x) => x.rubrique === rubrique);
    if (!items.length) continue;
    colonne.append(texte("h3", rubrique));
    for (const x of items) {
      const a = document.createElement("a");
      a.className = "exc";
      a.href = x.href;
      const t = texte("span", "", "tuile " + x.ton);
      t.append(icone(x.icone));
      const corps = texte("span", "", "corps");
      corps.append(texte("b", x.titre), texte("span", [x.lieu, x.detail].filter(Boolean).join(" · "), "mu"));
      a.append(t, corps, icone("chevron-right", "suite"));
      colonne.append(a);
    }
  }
}

function ligneLabAccueil(u) {
  const s = suivis.get(cleLab(u));
  const ligne = texte("div", "", "p1-lab");
  const nom = document.createElement("a");
  nom.className = "lab-nom";
  nom.href = lienLab(u.cours, u.lab);
  nom.append(texte("b", titreLab(u.lab)), texte("span", `${nomCours(u.cours)} · gr. ${groupesDe(u)}`, "mu"));
  const actions = texte("div", "", "actions");
  const prochain = s && prochainRapport(s);
  if (prochain) actions.append(lien("Corriger", urlRapport(u.cours, u.lab, prochain), { icone: "pen", titre: `Ouvrir ${prochain.prenom} ${prochain.nom}` }));
  const ap = apercus.get(cleLab(u));
  if (ap && ap.a_analyser > 0) {
    const b = bouton("", { icone: "sparkles", classe: "btn-analyser", surClic: () => lancerLot(u, ap.n) });
    b.append(`Analyser ${ap.n} `, texte("small", `· ${Math.round(ap.pct)} %`));
    b.title = ap.depasse ? "Ce lot dépasse la marge fixée pour la session de 5 h (il n'est pas bloqué)" : `Analyse par Claude des ${ap.n} prochains rapports de ${titreLab(u.lab)}`;
    b.disabled = lotActif;
    actions.append(b);
  }
  ligne.append(nom, etatLab(u, s, true), celluleExport(u, s), actions);
  ligne.onclick = (ev) => { if (!ev.target.closest("a, button")) location.href = lienLab(u.cours, u.lab); };
  return ligne;
}

function rendreLabsAccueil(enCours) {
  const zone = $("labs-accueil");
  zone.replaceChildren();
  if (!enCours.length) {
    const v = texte("div", "", "vide");
    v.append(icone(courant().length ? "circle-check" : "library"),
      texte("p", courant().length ? "Rien à corriger : tous les labs sont terminés." : "Aucune classe importée : commence par importer une liste de classe."));
    if (!courant().length) v.append(bouton("Importer", { icone: "upload", classe: "primaire", surClic: () => aller("importer") }));
    zone.append(v);
    return;
  }
  const tete = texte("div", "", "entete");
  tete.append(texte("span", "Lab"), texte("span", "État"), texte("span", "Export LÉA"), texte("span", "Actions"));
  tete.lastChild.style.textAlign = "right";
  zone.append(tete, ...enCours.map(ligneLabAccueil));
}

function rendreAccueil() {
  const labs = resumeLabs();
  const enCours = labs.filter((u) => !u.fini);
  const date = new Date().toLocaleDateString("fr-CA", { weekday: "long", day: "numeric", month: "long" });
  $("accueil-sous").textContent = date.charAt(0).toUpperCase() + date.slice(1);
  rendreContinuer();
  rendreChiffres(enCours);
  rendreAFaire(labs);
  rendreLabsAccueil(enCours);
}

// Un lot à la touche : « Analyser N », puis un toast « Arrêter » tant qu'il tourne. Un seul lot à la fois (les autres boutons attendent).
async function lancerLot(u, n) {
  if (lotActif) return;
  const r = await fetch(`/api/lot/${enc(u.cours)}/${enc(u.lab)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ n }) });
  if (!r.ok) { UI.toast(await erreurApi(r), { erreur: true }); return; }
  lotActif = true;
  majBoutonsLot();
  toastLot?.fermer();
  toastLot = UI.toast(`Analyse lancée : ${titreLab(u.lab)} · ${nomCours(u.cours)}, ${pluriel(n, "rapport", "rapports")}`, {
    duree: 6 * 3600 * 1000,
    action: { libelle: "Arrêter", surClic: () => { fetch("/api/lot/arreter", { method: "POST" }).catch(() => {}); } },
  });
}

function majBoutonsLot() {
  for (const b of document.querySelectorAll(".btn-analyser")) b.disabled = lotActif;
}

const FIN_LOT = {
  termine: (e) => ({ texte: `Analyse terminée : ${pluriel(e.fait, "rapport", "rapports")}` }),
  arrete: (e) => ({ texte: `Analyse arrêtée après ${pluriel(e.fait, "rapport", "rapports")}` }),
  limite: (e) => ({ texte: e.message || "Limite de Claude atteinte : reprends après la réinitialisation.", erreur: true }),
  erreur: (e) => ({ texte: e.message || "L'analyse s'est arrêtée sur une erreur.", erreur: true }),
};

document.addEventListener("coque:lot", (ev) => {
  const e = ev.detail;
  const actif = e.statut === "en_cours";
  const fin = lotActif && !actif;
  lotActif = actif;
  majBoutonsLot();
  if (!fin) return;
  toastLot?.fermer();
  toastLot = null;
  const f = FIN_LOT[e.statut]?.(e);
  if (f) UI.toast(f.texte, { erreur: f.erreur, duree: f.erreur ? 8000 : undefined });
  chargerSuivis(); // les comptes, l'export et le lot conseillé ont changé
});

aller(location.hash.slice(1));

function rendreEnoncesManquants() {
  const manquants = [];
  for (const cours of new Set(courant().map((c) => c.cours))) {
    const labs = new Set(courant().filter((c) => c.cours === cours).flatMap((c) => c.etudiants.flatMap((e) => e.labs)));
    for (const lab of [...labs].sort()) if (!enonces.some((x) => x.cours === cours && x.lab === lab)) manquants.push({ cours, lab });
  }
  const zone = $("enonces-manquants");
  zone.replaceChildren();
  zone.hidden = !manquants.length;
  if (!manquants.length) return;
  zone.append(texte("strong", `Énoncé manquant (${manquants.length}) : `), texte("span", "sans énoncé, les passages de l'énoncé comptent comme du plagiat. "));
  for (const m of manquants) {
    const a = texte("a", `${nomCours(m.cours)} · ${m.lab}`, "bk");
    a.href = `plagiat.html?${new URLSearchParams(m)}`;
    zone.append(a, " ");
  }
}

charger().catch(() => {});
