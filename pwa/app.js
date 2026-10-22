// Point d'entrée de la PWA : bibliothèque, import, accueil. La navigation et l'état du moteur sont dans coque.js.

// --- Bibliothèque et import ---
const API = "/api/bibliotheque";
const $ = (id) => document.getElementById(id);
const enc = encodeURIComponent;
let arbre = [];
let attente = [];
let suivis = new Map(); // « cours|lab » -> réponse de /api/suivi (état d'export, fautes à trancher), chargée après l'arbre
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

// --- Navigation repliée : cours > lab > groupe > rapports ---
let enonces = [];
const stockage = {
  lire(cle, defaut) { try { return localStorage.getItem(cle) ?? defaut; } catch { return defaut; } },
  ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch { /* sans stockage : tout reste replié */ } },
};

// Nœud repliable : <details class="noeud …"> avec un résumé (chevron, titre, compteur) et un corps.
function bloc(cle, classe, titreEl, compteur, ...contenu) {
  const d = document.createElement("details");
  d.className = "noeud " + classe;
  d.open = stockage.lire("ouvert:" + cle, "0") === "1";
  d.ontoggle = () => stockage.ecrire("ouvert:" + cle, d.open ? "1" : "0");
  const s = document.createElement("summary");
  s.append(icone("chevron-right", "chevron"), titreEl);
  if (compteur) s.append(compteur);
  d.append(s, ...contenu);
  return d;
}

async function api(methode, chemin, corps) {
  const r = await fetch(chemin, { method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
  if (!r.ok) alert(await erreurApi(r));
  return r.ok;
}

function labFini(c, lab) {
  const avec = c.etudiants.filter((e) => e.labs.includes(lab));
  return c.labs_archives.includes(lab) || (avec.length > 0 && avec.every((e) => e.termines.includes(lab)));
}

// Un lab = un cours + un nom de lab, tous groupes confondus.
function resumeLabs() {
  const parLab = new Map();
  for (const c of arbre) {
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

function progression(faits, total) {
  const zone = texte("div", "", "prog");
  const barre = texte("div", "", "barre");
  const i = document.createElement("i");
  i.className = "fait";
  i.style.width = total ? `${Math.round((100 * faits) / total)}%` : "0";
  barre.append(i);
  barre.setAttribute("role", "img");
  barre.setAttribute("aria-label", `${faits} sur ${total} terminés`);
  zone.append(barre, texte("span", `${faits} / ${total}`, "num"));
  return zone;
}

const initiales = (e) => ((e.prenom?.[0] ?? "") + (e.nom?.[0] ?? "")).toUpperCase();

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

function ligneRapport(c, lab, e) {
  const fini = e.termines.includes(lab);
  const ligne = texte("div", "", "rap");
  const avatar = texte("span", initiales(e), "avatar");
  const nom = texte("span", "", "nom");
  nom.append(texte("b", `${e.nom}, ${e.prenom}`));
  const equipe = e.equipes?.[lab];
  const details = [];
  if (equipe?.length) details.push(`avec ${equipe.map((x) => `${x.prenom} ${x.nom}`).join(", ")}`);
  if (e.notes?.[lab]) details.push(`note ${e.notes[lab]}`);
  if (details.length) nom.append(texte("small", details.join(" · ")));
  const q = new URLSearchParams({ cours: c.cours, groupe: c.groupe, lab, etudiant: e.id, nom: `${e.prenom} ${e.nom}` });
  const lecteur = `lecteur.html?${q}`;
  q.set("panneau", "francais");
  const lecteurFrancais = `lecteur.html?${q}`;

  const statut = async () => {
    let corps = { termine: !fini };
    if (!fini) { // note du rapport, demandée à « Terminé » (vide = pas de note); Annuler = ne rien faire
      const note = prompt("Note du rapport (ex. 17,5), facultatif :", e.notes?.[lab] ?? "");
      if (note === null) return;
      corps = { termine: true, note: note.trim() };
    }
    if (await api("PUT", `${API}/statut/${c.cours}/${c.groupe}/${lab}/${e.id}`, corps)) await charger();
  };

  const annoter = lien("Annoter", lecteur, { icone: "pen", titre: "Ouvrir le rapport dans l'outil d'annotation" });
  const plus = document.createElement("button");
  plus.type = "button";
  plus.className = "btn-ico";
  plus.setAttribute("aria-label", `Autres actions pour ${e.prenom} ${e.nom}`);
  plus.append(icone("ellipsis"));
  UI.menu(plus, [
    { libelle: "Fautes de français", icone: "spell-check", surClic: () => { location.href = lecteurFrancais; } },
    { libelle: "Indices d'IA", icone: "scan-search", surClic: () => window.ouvrirIndicesIA?.(c.cours, c.groupe, lab, e) },
    { libelle: "Équipe (coéquipiers)", icone: "users", surClic: () => basculerEquipe(ligne, () => editerEquipe(c.cours, c.groupe, lab, e.id, e.equipes?.[lab] ?? [], charger)) },
    { separateur: true },
    fini ? { libelle: "Ré-ouvrir le rapport", icone: "rotate-ccw", surClic: statut } : { libelle: "Marquer terminé", icone: "circle-check", surClic: statut },
  ]);
  ligne.append(avatar, nom);
  if (fini) ligne.append(pastille("Terminé", "p-fini"));
  ligne.append(annoter, plus);
  return ligne;
}

function blocEnonce(cours, lab) {
  const existe = enonces.some((x) => x.cours === cours && x.lab === lab);
  const zone = texte("div", "", "enonce");
  zone.append(icone("file-text"), texte("b", "Énoncé"));
  zone.append(existe ? pastille("Enregistré", "p-fini") : pastille("Aucun énoncé", "p-neutre"));
  const espace = texte("span", "", "esp");
  zone.append(espace);
  if (existe) {
    const voir = lien("Voir", `/api/plagiat/enonces/${enc(cours)}/${enc(lab)}`, { icone: "external-link", classe: "tertiaire" });
    voir.target = "_blank";
    zone.append(voir);
  }
  const champ = document.createElement("input");
  champ.type = "file";
  champ.accept = "application/pdf";
  champ.hidden = true;
  champ.onchange = async () => {
    if (!champ.files[0]) return;
    if (existe && !confirm("Remplacer l'énoncé de ce lab ?")) { champ.value = ""; return; }
    const form = new FormData();
    form.append("pdf", champ.files[0]);
    const r = await fetch(`/api/plagiat/enonces/${enc(cours)}/${enc(lab)}`, { method: "POST", body: form });
    if (!r.ok) alert(await erreurApi(r));
    await charger();
  };
  zone.append(bouton(existe ? "Remplacer" : "Téléverser", { icone: "file-up", surClic: () => champ.click() }), champ);
  return zone;
}

function blocGroupe(c, lab) {
  const avec = c.etudiants.filter((e) => e.labs.includes(lab));
  const faits = avec.filter((e) => e.termines.includes(lab));
  const fini = labFini(c, lab);
  const archive = c.labs_archives.includes(lab);
  const titre = texte("span", `Groupe ${c.groupe}`, "titre");
  const encours = avec.filter((e) => !e.termines.includes(lab)).map((e) => ligneRapport(c, lab, e));
  const termines = faits.map((e) => ligneRapport(c, lab, e));
  const cle = `${c.cours}/${lab}/${c.groupe}`;

  const analyser = bouton("Analyser", { icone: "sparkles", titre: "Analyse par lot (Claude) de ce groupe",
    surClic: () => { window.choisirLot?.(c.cours, c.groupe, lab); aller("outils"); } });
  const plagiat = lien("Plagiat", `plagiat.html?${new URLSearchParams({ cours: c.cours, lab })}`, { icone: "scan-search" });
  const plus = document.createElement("button");
  plus.type = "button";
  plus.className = "btn-ico";
  plus.setAttribute("aria-label", `Autres actions du groupe ${c.groupe}`);
  plus.append(icone("ellipsis"));
  UI.menu(plus, [{
    libelle: archive ? "Ré-ouvrir le lab" : "Marquer le lab terminé", icone: archive ? "rotate-ccw" : "circle-check",
    surClic: async () => { if (await api("PUT", `${API}/archive/${c.cours}/${c.groupe}/${lab}`, { archive: !archive })) await charger(); },
  }]);
  const outils = texte("div", "", "outils-lab");
  outils.append(analyser, plagiat, texte("span", "", "esp"), plus);

  const sousTermines = termines.length
    ? [remplir(bloc(cle + "/termines", "termines", texte("span", "Terminés", "titre"), texte("span", String(termines.length), "n")), termines)] : [];
  const compte = texte("span", "", "n");
  compte.append(fini ? pastille("Terminé", "p-fini") : texte("span", `${encours.length} à corriger`), progression(faits.length, avec.length));
  return remplir(bloc(cle, "groupe", titre, compte), [outils, ...encours, ...sousTermines]);
}

function remplir(details, enfants) {
  const corps = texte("div", "", "corps");
  corps.append(...enfants);
  details.append(corps);
  return details;
}

function filtreCourant() { return stockage.lire("filtre", "cours"); }

function selonFiltre(fini, filtre) { return filtre === "tout" || (filtre === "finis" ? fini : !fini); }

// Compteurs des contrôles segmentés : labs en cours, terminés, tous.
function majCompteurs(seg, labs, filtre) {
  const n = { cours: labs.filter((u) => !u.fini).length, finis: labs.filter((u) => u.fini).length, tout: labs.length };
  for (const b of seg.querySelectorAll("button")) {
    b.querySelector(".n").textContent = n[b.dataset.f];
    b.classList.toggle("on", b.dataset.f === filtre);
    b.setAttribute("aria-pressed", String(b.dataset.f === filtre));
  }
}

function etatVideBibliotheque() {
  const v = texte("div", "", "vide carte");
  v.append(icone("library"), texte("h2", "Ta bibliothèque est vide"),
    texte("p", "Commence par la liste de classe exportée d'Omnivox ou de LÉA, puis importe les PDF d'un lab."),
    bouton("Importer une liste de classe", { icone: "upload", classe: "primaire", surClic: () => aller("importer") }));
  return v;
}

function rendreArbre() {
  const filtre = filtreCourant();
  const zone = $("arbre");
  zone.replaceChildren();
  const tous = resumeLabs();
  majCompteurs($("filtres"), tous, filtre);
  $("biblio-sous").textContent = arbre.length
    ? `${pluriel(new Set(arbre.map((c) => c.cours)).size, "cours", "cours")} · ${pluriel(tous.length, "lab", "labs")} · ${pluriel(arbre.length, "groupe", "groupes")}`
    : "Aucune classe importée.";
  if (!arbre.length) { zone.append(etatVideBibliotheque()); return; }
  const parCours = Map.groupBy(arbre, (c) => c.cours);
  for (const [cours, classes] of parCours) {
    const labs = tous.filter((u) => u.cours === cours);
    const blocsLabs = [];
    for (const u of labs) {
      const lab = u.lab;
      const groupes = u.classes.filter((c) => selonFiltre(labFini(c, lab), filtre));
      if (!groupes.length) continue;
      const total = groupes.reduce((n, c) => n + c.etudiants.filter((e) => e.labs.includes(lab)).length, 0);
      const faits = groupes.reduce((n, c) => n + c.etudiants.filter((e) => e.termines.includes(lab)).length, 0);
      const compte = texte("span", "", "n");
      compte.append(texte("span", pluriel(groupes.length, "groupe", "groupes"), "mu"), progression(faits, total));
      const suivi = lien("Suivi du lab", `suivi.html?${new URLSearchParams({ cours, lab })}`, { icone: "table", classe: "primaire" });
      const entete = texte("div", "", "outils-lab");
      entete.append(suivi);
      blocsLabs.push(remplir(bloc(`${cours}/${lab}`, "lab", texte("span", lab, "titre"), compte),
        [entete, blocEnonce(cours, lab),
          window.blocExportLea(cours, lab, u.classes.map((c) => c.groupe)),
          ...groupes.map((c) => blocGroupe(c, lab))]));
    }
    const resume = texte("span", `${pluriel(labs.length, "lab", "labs")} · ${pluriel(classes.length, "groupe", "groupes")}`, "n");
    zone.append(remplir(bloc(cours, "cours", texte("span", cours, "titre"), resume),
      blocsLabs.length ? blocsLabs : [texte("p", "Aucun lab dans cette vue.", "aide vide-vue")]));
  }
}

for (const [seg, rendre] of [["filtres", () => rendreArbre()], ["filtres-accueil", () => rendreLabsAccueil()]]) {
  const cle = seg === "filtres" ? "filtre" : "filtre-accueil";
  $(seg).addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    stockage.ecrire(cle, b.dataset.f);
    rendre();
  });
}

async function charger() {
  arbre = await (await fetch(API)).json();
  enonces = await (await fetch("/api/plagiat/enonces")).json().catch(() => []);
  rendreArbre();
  rendreAccueil();
  rendreEnoncesManquants();
  const cours = [...new Set(arbre.map((c) => c.cours))];
  const choisi = $("choix-cours").value;
  $("choix-cours").replaceChildren(...cours.map((c) => { const o = texte("option", c); o.value = c; return o; }));
  if (cours.includes(choisi)) $("choix-cours").value = choisi;
  $("choix-cours").onchange = remplirGroupes;
  remplirGroupes();
  rendreClassesChargees();
  window.rafraichirLot?.(arbre);
  window.Coque?.labs(arbre);
  await chargerAttente();
  rendreEtapes();
  chargerSuivis(); // sans attendre : l'accueil se complète (À faire, export) quand les réponses arrivent
}

// Une requête de suivi par lab pas archivé : fautes à trancher et état de l'export. Échec silencieux : l'accueil s'en passe.
let chargementSuivis = 0;
async function chargerSuivis() {
  const tour = ++chargementSuivis;
  const labs = resumeLabs().filter((u) => !u.classes.every((c) => c.labs_archives.includes(u.lab)));
  const [reponses, paires] = await Promise.all([
    Promise.all(labs.map(async (u) => {
      try { return [`${u.cours}|${u.lab}`, await (await fetch(`/api/suivi/${enc(u.cours)}/${enc(u.lab)}`)).json()]; } catch { return null; }
    })),
    fetch("/api/plagiat/paires").then((r) => r.json()).catch(() => null),
  ]);
  if (tour !== chargementSuivis) return; // un rechargement plus récent est passé devant
  suivis = new Map(reponses.filter((x) => x?.[1]?.rapports));
  pairesAConfirmer = (paires?.paires ?? []).filter((p) => p.statut === "a_confirmer").length;
  rendreAccueil();
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
    const contexte = texte("p", `${item.cours} · ${item.lab}${item.da ? ` · DA ${item.da}` : ""}`, "aide");
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
    li.append(icone("circle-check"), texte("b", c.cours), texte("span", `groupe ${c.groupe} · ${pluriel(actifs, "étudiant", "étudiants")}`));
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
  corps.append(texte("b", `Liste ${classe.cours} groupe ${classe.groupe} : ${pluriel(m.ajoutes.length, "ajouté", "ajoutés")}, ${m.inchanges + m.mis_a_jour.length} inchangé(s), ${m.retires.length} retiré(s), ${conflits} à trancher`));
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

// Ouvre un lab dans la bibliothèque : cours, lab et tous ses groupes dépliés.
function ouvrirLab(u) {
  for (const cle of [u.cours, `${u.cours}/${u.lab}`, ...u.classes.map((c) => `${u.cours}/${u.lab}/${c.groupe}`)]) stockage.ecrire("ouvert:" + cle, "1");
  stockage.ecrire("filtre", u.fini ? "finis" : "cours");
  rendreArbre();
  aller("biblio");
}

function rendreAccueil() {
  rendreContinuer();
  rendreAFaire();
  rendreLabsAccueil();
  const labs = resumeLabs();
  const restants = labs.filter((u) => !u.fini).reduce((n, u) => n + u.total - u.faits, 0);
  const nbLabs = labs.filter((u) => !u.fini).length;
  const date = new Date().toLocaleDateString("fr-CA", { weekday: "long", day: "numeric", month: "long" });
  $("accueil-sous").textContent = arbre.length
    ? `${date.charAt(0).toUpperCase() + date.slice(1)} · ${restants ? `${pluriel(restants, "rapport restant", "rapports restants")} dans ${pluriel(nbLabs, "lab", "labs")}` : "tout est corrigé"}`
    : date.charAt(0).toUpperCase() + date.slice(1);
}

function rendreContinuer() {
  let dernier = null;
  try { dernier = JSON.parse(localStorage.getItem("dernier")); } catch { /* aucun rapport ouvert */ }
  const zone = $("continuer");
  zone.replaceChildren();
  zone.hidden = !dernier?.url;
  $("continuer").closest(".accueil-haut").classList.toggle("sans-reprise", !dernier?.url);
  if (!dernier?.url) return;
  const carte = texte("div", "", "carte reprise");
  const tuile = texte("span", "", "tuile");
  tuile.append(icone("file-text", "l"));
  const corps = texte("div", "", "reprise-corps");
  corps.append(texte("div", "Reprendre là où tu étais", "reprise-etq"), texte("div", dernier.nom || "Dernier rapport", "reprise-nom"),
    texte("div", `${dernier.cours} · ${dernier.lab} · groupe ${dernier.groupe}`, "mu"));
  carte.append(tuile, corps, lien("Reprendre", dernier.url, { icone: "arrow-right", classe: "primaire" }));
  zone.append(carte);
}

// Bloc « À faire » (emprunté à la direction C) : ce qui attend une décision, avec un lien direct.
function ligneFaire({ icone: nom, ton, titre, sous, href, surClic }) {
  const el = document.createElement(href ? "a" : "button");
  el.className = "faire";
  if (href) el.href = href; else { el.type = "button"; el.onclick = surClic; }
  const tuile = texte("span", "", "tuile " + ton);
  tuile.append(icone(nom));
  const corps = texte("span", "", "faire-corps");
  corps.append(texte("b", titre), texte("span", sous, "mu"));
  el.append(tuile, corps, icone("chevron-right", "suite"));
  return el;
}

function elementsAFaire() {
  const liste = [];
  if (attente.length) {
    liste.push({ icone: "upload", ton: "attention", titre: `${pluriel(attente.length, "fichier", "fichiers")} à associer`,
      sous: "Import · choisir l'étudiant de chaque rapport", href: "#importer" });
  }
  const labs = resumeLabs();
  for (const u of labs) {
    const s = suivis.get(`${u.cours}|${u.lab}`);
    if (!s) continue;
    const ouvert = s.rapports.filter((r) => !r.termine);
    const fautes = ouvert.reduce((n, r) => n + (r.francais.a_trancher ?? 0), 0);
    const concernes = ouvert.filter((r) => r.francais.a_trancher).length;
    if (fautes) {
      liste.push({ icone: "spell-check", ton: "attention", titre: `${pluriel(fautes, "faute", "fautes")} à trancher`,
        sous: `${u.lab} · ${u.cours} · ${pluriel(concernes, "rapport", "rapports")}`,
        href: `suivi.html?${new URLSearchParams({ cours: u.cours, lab: u.lab })}` });
    }
  }
  if (pairesAConfirmer) {
    liste.push({ icone: "scan-search", ton: "plagiat", titre: `${pluriel(pairesAConfirmer, "paire", "paires")} à regarder`,
      sous: "Plagiat · des indices à revérifier, jamais un verdict", href: "plagiat.html" });
  }
  for (const u of labs) {
    const s = suivis.get(`${u.cours}|${u.lab}`);
    if (!s || !s.total || u.classes.every((c) => c.labs_archives.includes(u.lab))) continue;
    if (s.export.statut === "perime") {
      liste.push({ icone: "file-down", ton: "attention", titre: "Export à refaire", surClic: () => ouvrirLab(u),
        sous: `${u.lab} · ${u.cours} · ${pluriel(s.export.modifies, "rapport modifié", "rapports modifiés")} depuis l'export` });
    } else if (s.export.statut === "jamais" && u.fini) {
      liste.push({ icone: "file-down", ton: "accent", titre: `${u.lab} terminé : prépare Travaux.zip`, surClic: () => ouvrirLab(u),
        sous: `${u.cours} · ${pluriel(u.total, "rapport", "rapports")}, jamais exporté pour LÉA` });
    }
  }
  return liste;
}

function rendreAFaire() {
  const zone = $("a-faire");
  zone.replaceChildren();
  const elements = elementsAFaire();
  if (!elements.length) {
    const v = texte("div", "", "faire-vide");
    v.append(icone("circle-check"), texte("p", arbre.length ? "Rien à faire pour l'instant : tout est à jour." : "Rien à faire : commence par importer une liste de classe."));
    zone.append(v);
    return;
  }
  zone.append(...elements.map(ligneFaire));
}

// Pastille d'export LÉA d'un lab (état connu seulement quand le suivi du lab est chargé).
function pastilleExport(u) {
  const s = suivis.get(`${u.cours}|${u.lab}`);
  if (!s) return texte("span", "—", "mu");
  const x = s.export;
  if (x.statut === "perime") return pastille(`À refaire · ${x.modifies} modifié(s)`);
  if (x.statut === "a_jour") return pastille("À jour", "p-fini");
  return pastille("Jamais exporté", "p-neutre");
}

function rendreLabsAccueil() {
  const filtre = stockage.lire("filtre-accueil", "cours");
  const tous = resumeLabs();
  majCompteurs($("filtres-accueil"), tous, filtre);
  const zone = $("labs-accueil");
  zone.replaceChildren();
  const labs = tous.filter((u) => selonFiltre(u.fini, filtre));
  if (!labs.length) {
    const v = texte("div", "", "vide carte");
    v.append(icone(arbre.length ? "circle-check" : "library"),
      texte("p", !arbre.length ? "Aucune classe importée : commence par importer une liste de classe."
        : filtre === "finis" ? "Aucun lab terminé pour l'instant." : "Rien à corriger : tout est terminé."));
    if (!arbre.length) v.append(bouton("Importer", { icone: "upload", classe: "primaire", surClic: () => aller("importer") }));
    zone.append(v);
    return;
  }
  const table = document.createElement("table");
  table.className = "tableau";
  const tete = table.createTHead().insertRow();
  for (const [t, classe] of [["Lab", ""], ["Progression", "col-prog"], ["Export LÉA", "col-export"], ["", "col-actions"]]) {
    const th = texte("th", t, classe);
    if (!t) th.setAttribute("aria-label", "Actions");
    tete.append(th);
  }
  const corps = table.createTBody();
  for (const u of labs) {
    const tr = corps.insertRow();
    tr.className = "ligne-lab";
    const nom = tr.insertCell();
    nom.append(texte("b", u.lab), texte("div", `${u.cours} · gr. ${u.classes.map((c) => c.groupe).join(", ")}`, "mu"));
    const prog = tr.insertCell();
    prog.className = "col-prog";
    prog.append(progression(u.faits, u.total));
    const exp = tr.insertCell();
    exp.className = "col-export";
    exp.append(pastilleExport(u));
    const actions = tr.insertCell();
    actions.className = "actions col-actions";
    const ouvrir = document.createElement("button");
    ouvrir.type = "button";
    ouvrir.className = "btn-ico";
    ouvrir.setAttribute("aria-label", `Ouvrir ${u.lab} (${u.cours}) dans la bibliothèque`);
    ouvrir.append(icone("chevron-right"));
    ouvrir.onclick = () => ouvrirLab(u);
    actions.append(lien("Suivi", `suivi.html?${new URLSearchParams({ cours: u.cours, lab: u.lab })}`, { icone: "table" }), " ", ouvrir);
    tr.onclick = (ev) => { if (!ev.target.closest("a, button")) ouvrirLab(u); };
  }
  const defil = texte("div", "", "tableau-defil");
  defil.append(table);
  zone.append(defil);
}

aller(location.hash.slice(1));

function rendreEnoncesManquants() {
  const manquants = [];
  for (const cours of new Set(arbre.map((c) => c.cours))) {
    const labs = new Set(arbre.filter((c) => c.cours === cours).flatMap((c) => c.etudiants.flatMap((e) => e.labs)));
    for (const lab of [...labs].sort()) if (!enonces.some((x) => x.cours === cours && x.lab === lab)) manquants.push({ cours, lab });
  }
  const zone = $("enonces-manquants");
  zone.replaceChildren();
  zone.hidden = !manquants.length;
  if (!manquants.length) return;
  zone.append(texte("strong", `Énoncé manquant (${manquants.length}) : `), texte("span", "sans énoncé, les passages de l'énoncé comptent comme du plagiat. "));
  for (const m of manquants) {
    const a = texte("a", `${m.cours} · ${m.lab}`, "bk");
    a.href = `plagiat.html?${new URLSearchParams(m)}`;
    zone.append(a, " ");
  }
}

charger().catch(() => {});
