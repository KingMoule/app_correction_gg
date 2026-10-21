// Point d'entrée de la PWA. Les écrans (bibliothèque, lecteur) viendront ici.
async function verifierMoteur() {
  const el = document.getElementById("etat");
  try {
    const r = await fetch("/api/etat");
    const d = await r.json();
    el.textContent = "● Moteur connecté";
    el.title = `v${d.version}`;
    el.className = "ok";
  } catch {
    el.textContent = "● Moteur injoignable";
    el.title = "L'ordi est-il allumé et sur le même Wi-Fi ?";
    el.className = "erreur";
  }
}
verifierMoteur();

// --- Bibliothèque et import ---
const API = "/api/bibliotheque";
const $ = (id) => document.getElementById(id);
let arbre = [];

function texte(tag, contenu, classe) {
  const el = document.createElement(tag);
  el.textContent = contenu; // textContent : les noms de fichiers ne sont jamais interprétés comme du HTML
  if (classe) el.className = classe;
  return el;
}

async function erreurApi(r) {
  const d = await r.json().catch(() => ({}));
  return d.detail || `Erreur ${r.status}`;
}

// --- Navigation repliée : cours > groupe > lab > rapports ---
let enonces = [];
const stockage = {
  lire(cle, defaut) { try { return localStorage.getItem(cle) ?? defaut; } catch { return defaut; } },
  ecrire(cle, valeur) { try { localStorage.setItem(cle, valeur); } catch { /* sans stockage : tout reste replié */ } },
};

function bloc(cle, titreEl, compteur, ...contenu) {
  const d = document.createElement("details");
  d.open = stockage.lire("ouvert:" + cle, "0") === "1";
  d.ontoggle = () => stockage.ecrire("ouvert:" + cle, d.open ? "1" : "0");
  const s = document.createElement("summary");
  s.append(titreEl);
  if (compteur) s.append(texte("span", compteur, "n"));
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

// Équipe d'un rapport : retirer ou ajouter un coéquipier (étudiants du cours), enregistré tout de suite.
function editerEquipe(cours, groupe, lab, etudiant, equipe, apres) {
  const zone = texte("div", "", "equipe-edition");
  const rendre = (membres) => {
    zone.replaceChildren(texte("strong", "Équipe"));
    if (!membres.length) zone.append(texte("p", "Aucun coéquipier."));
    for (const m of membres) {
      const l = texte("div", `${m.prenom} ${m.nom} (groupe ${m.groupe}) `, "rap");
      const b = texte("button", "Retirer", "bk");
      b.onclick = () => enregistrer(membres.filter((x) => x !== m));
      l.append(b);
      zone.append(l);
    }
    const choix = document.createElement("select");
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

function ligneRapport(c, lab, e) {
  const fini = e.termines.includes(lab);
  const ligne = texte("div", "", "rap");
  const nom = texte("span", `${e.nom}, ${e.prenom}`, "nom");
  const equipe = e.equipes?.[lab];
  if (equipe?.length) nom.append(texte("small", ` (avec ${equipe.map((x) => `${x.prenom} ${x.nom}`).join(", ")})`));
  const q = new URLSearchParams({ cours: c.cours, groupe: c.groupe, lab, etudiant: e.id, nom: `${e.prenom} ${e.nom}` });
  const ouvrir = texte("a", "Annoter", "gros");
  ouvrir.href = `lecteur.html?${q}`;
  ouvrir.title = "Ouvrir le rapport dans l'outil d'annotation";
  const francais = texte("a", "Français", "bk");
  q.set("panneau", "francais");
  francais.href = `lecteur.html?${q}`;
  francais.title = "Ouvrir le rapport avec le panneau des fautes de français";
  const ia = texte("button", "IA", "bk");
  ia.title = "Indices d'IA";
  ia.onclick = () => window.ouvrirIndicesIA?.(c.cours, c.groupe, lab, e);
  const statut = texte("button", fini ? "↩ Ré-ouvrir" : "✔ Terminé", "bk");
  statut.onclick = async () => {
    let corps = { termine: !fini };
    if (!fini) { // note du rapport, demandée à « Terminé » (vide = pas de note); Annuler = ne rien faire
      const note = prompt("Note du rapport (ex. 17,5), facultatif :", e.notes?.[lab] ?? "");
      if (note === null) return;
      corps = { termine: true, note: note.trim() };
    }
    if (await api("PUT", `${API}/statut/${c.cours}/${c.groupe}/${lab}/${e.id}`, corps)) await charger();
  };
  if (e.notes?.[lab]) nom.append(texte("small", ` · note ${e.notes[lab]}`));
  const eq = texte("button", "Équipe", "bk");
  eq.title = "Ajouter ou retirer un coéquipier";
  eq.onclick = () => {
    if (ligne.nextElementSibling?.classList.contains("equipe-edition")) { ligne.nextElementSibling.remove(); return; }
    ligne.after(editerEquipe(c.cours, c.groupe, lab, e.id, e.equipes?.[lab] ?? [], charger));
  };
  ligne.append(nom, eq, ia, statut, francais, ouvrir);
  return ligne;
}

function blocEnonce(cours, lab) {
  const existe = enonces.some((x) => x.cours === cours && x.lab === lab);
  const zone = texte("div", "", "enonce");
  zone.append(texte("span", existe ? "📄 Énoncé enregistré" : "Aucun énoncé"));
  if (existe) {
    const voir = texte("a", "Voir", "bk");
    voir.href = `/api/plagiat/enonces/${encodeURIComponent(cours)}/${encodeURIComponent(lab)}`;
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
    const r = await fetch(`/api/plagiat/enonces/${encodeURIComponent(cours)}/${encodeURIComponent(lab)}`, { method: "POST", body: form });
    if (!r.ok) alert(await erreurApi(r));
    await charger();
  };
  const bouton = texte("button", existe ? "Remplacer" : "Téléverser", "bk");
  bouton.onclick = () => champ.click();
  zone.append(bouton, champ);
  return zone;
}

function blocGroupe(c, lab) {
  const avec = c.etudiants.filter((e) => e.labs.includes(lab));
  const faits = avec.filter((e) => e.termines.includes(lab));
  const fini = labFini(c, lab);
  const titre = texte("span", `Groupe ${c.groupe}`);
  titre.append(texte("span", fini ? "terminé" : `${faits.length} / ${avec.length}`, `pastille ${fini ? "p-fini" : "p-cours"}`));
  const archiver = texte("button", c.labs_archives.includes(lab) ? "Ré-ouvrir le lab" : "Marquer le lab terminé", "bk");
  archiver.onclick = async () => {
    if (await api("PUT", `${API}/archive/${c.cours}/${c.groupe}/${lab}`, { archive: !c.labs_archives.includes(lab) })) await charger();
  };
  const analyser = texte("button", "Analyser", "bk");
  analyser.title = "Analyse par lot (Claude) de ce groupe";
  analyser.onclick = () => { window.choisirLot?.(c.cours, c.groupe, lab); aller("outils"); };
  const plagiat = texte("a", "Plagiat", "bk");
  plagiat.href = `plagiat.html?${new URLSearchParams({ cours: c.cours, lab })}`;
  const encours = avec.filter((e) => !e.termines.includes(lab)).map((e) => ligneRapport(c, lab, e));
  const termines = faits.map((e) => ligneRapport(c, lab, e));
  const cle = `${c.cours}/${lab}/${c.groupe}`;
  const outils = texte("div", "", "outils-lab");
  outils.append(analyser, plagiat, archiver);
  const sousTermines = termines.length
    ? [remplir(bloc(cle + "/termines", texte("span", "Terminés"), String(termines.length)), termines)] : [];
  return remplir(bloc(cle, titre, fini ? "" : `${encours.length} à corriger`),
    [outils, ...encours, ...sousTermines]);
}

function remplir(details, enfants) {
  const corps = texte("div", "", "corps");
  corps.append(...enfants);
  details.append(corps);
  return details;
}

function rendreArbre() {
  const filtre = stockage.lire("filtre", "cours");
  document.querySelectorAll("#filtres button").forEach((b) => b.classList.toggle("on", b.dataset.f === filtre));
  const zone = $("arbre");
  zone.replaceChildren();
  if (!arbre.length) zone.append(texte("p", "Aucune classe importée."));
  const parCours = Map.groupBy(arbre, (c) => c.cours);
  for (const [cours, classes] of parCours) {
    const labs = [...new Set(classes.flatMap((c) => c.etudiants.flatMap((e) => e.labs)))].sort();
    const blocsLabs = [];
    for (const lab of labs) {
      const groupes = classes.filter((c) => {
        if (!c.etudiants.some((e) => e.labs.includes(lab))) return false;
        const fini = labFini(c, lab);
        return filtre === "tout" || (filtre === "finis" ? fini : !fini);
      });
      if (!groupes.length) continue;
      const total = groupes.reduce((n, c) => n + c.etudiants.filter((e) => e.labs.includes(lab)).length, 0);
      const faits = groupes.reduce((n, c) => n + c.etudiants.filter((e) => e.termines.includes(lab)).length, 0);
      const titre = texte("span", lab);
      titre.append(texte("span", `${faits} / ${total}`, `pastille ${faits === total ? "p-fini" : ""}`));
      const suivi = texte("a", "Suivi du lab", "bk principal");
      suivi.href = `suivi.html?${new URLSearchParams({ cours, lab })}`;
      blocsLabs.push(remplir(bloc(`${cours}/${lab}`, titre, `${groupes.length} groupe(s)`),
        [suivi, blocEnonce(cours, lab),
          window.blocExportLea(cours, lab, classes.filter((c) => c.etudiants.some((e) => e.labs.includes(lab))).map((c) => c.groupe)),
          ...groupes.map((c) => blocGroupe(c, lab))]));
    }
    zone.append(remplir(bloc(cours, texte("b", cours), `${labs.length} lab(s) · ${classes.length} groupe(s)`),
      blocsLabs.length ? blocsLabs : [texte("p", "Aucun lab dans cette vue.", "aide")]));
  }
}

document.querySelectorAll("#filtres button").forEach((b) => {
  b.onclick = () => { stockage.ecrire("filtre", b.dataset.f); rendreArbre(); };
});

async function charger() {
  arbre = await (await fetch(API)).json();
  enonces = await (await fetch("/api/plagiat/enonces")).json().catch(() => []);
  rendreArbre();
  rendreAccueil();
  rendreEnoncesManquants();
  const cours = [...new Set(arbre.map((c) => c.cours))];
  $("choix-cours").replaceChildren(...cours.map((c) => { const o = texte("option", c); o.value = c; return o; }));
  $("choix-cours").onchange = remplirGroupes;
  remplirGroupes();
  window.rafraichirLot?.(arbre);
  await chargerAttente();
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
}

async function chargerAttente() {
  const liste = await (await fetch(`${API}/attente`)).json();
  $("section-attente").hidden = !liste.length;
  $("badge-attente").hidden = !liste.length;
  $("badge-attente").textContent = liste.length;
  const zone = $("attente");
  zone.replaceChildren();
  const raisons = {
    ambigu: "Plusieurs étudiants possibles",
    aucune_correspondance: "Aucun nom reconnu",
    deja_importe: "Rapport déjà importé pour ce lab (le remplacer ?)",
    da_inconnu: "N° de DA absent des listes de classe, aucun nom reconnu",
  };
  for (const item of liste) {
    const classes = arbre.filter((c) => c.cours === item.cours && (!item.groupe || c.groupe === item.groupe));
    const bloc = texte("div", "", "attente-item");
    bloc.append(texte("strong", item.fichier), texte("p", `${raisons[item.raison]} · ${item.cours} · ${item.lab}${item.da ? ` · DA ${item.da}` : ""}`));
    const choix = document.createElement("select");
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
    const ok = texte("button", "Ranger");
    ok.onclick = () => {
      const [etudiant, groupe] = choix.value ? JSON.parse(choix.value) : [];
      const existe = etudiant && arbre.some((c) => c.cours === item.cours && c.groupe === groupe
        && c.etudiants.some((e) => e.id === etudiant && e.labs.includes(item.lab)));
      if (existe && !confirm("Cet étudiant a déjà un rapport pour ce lab. Remplacer ? Les corrections de l'ancien rapport "
        + "(annotations, fautes, statut, note) seront mises de côté dans le dossier _remplaces (récupérable) "
        + "et le nouveau rapport repartira à neuf.")) return;
      trancher(item.id, choix.value ? JSON.parse(choix.value) : "", existe);
    };
    const non = texte("button", "Écarter");
    non.onclick = () => {
      if (confirm("Écarter ce fichier ? Il sera mis de côté dans le dossier _ecartes (récupérable).")) trancher(item.id, null);
    };
    bloc.append(choix, ok, non);
    zone.append(bloc);
  }
}

async function trancher(id, choix, remplacer = false) {
  if (choix === "") return;
  const [etudiant, groupe] = choix ?? [null, null];
  await fetch(`${API}/attente/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ etudiant, groupe, remplacer }),
  });
  await charger();
}

$("fichier-classe").onchange = async (ev) => {
  const fichier = ev.target.files[0];
  if (!fichier) return;
  const form = new FormData();
  form.append("fichier", fichier);
  const r = await fetch(`${API}/classes`, { method: "POST", body: form });
  if (!r.ok) alert(await erreurApi(r));
  else afficherRecapClasse(await r.json());
  ev.target.value = "";
  await charger();
};

function afficherRecapClasse(classe) {
  const m = classe.recap;
  const zone = $("resultat-classe");
  zone.replaceChildren(texte("strong", `Liste ${classe.cours} groupe ${classe.groupe} : ${m.ajoutes.length} ajouté(s), ${m.inchanges + m.mis_a_jour.length} inchangé(s), ${m.retires.length} retiré(s), ${m.conflits.length} à trancher`));
  const liste = document.createElement("ul");
  const ligne = (titre, noms) => { if (noms.length) liste.append(texte("li", `${titre} : ${noms.join(", ")}`)); };
  ligne("Ajoutés", m.ajoutes);
  ligne("Retirés de la liste (rapports gardés)", m.retires);
  ligne("Revenus", m.reactives);
  ligne("Mis à jour (nom ou DA)", m.mis_a_jour);
  for (const c of m.conflits) liste.append(texte("li", `À trancher, ${c.nom} : ${c.raison}`));
  zone.append(liste);
}

$("importer").onclick = async () => {
  const cours = $("choix-cours").value;
  const fichiers = $("fichiers-pdf").files;
  if (!cours || !$("lab").value.trim() || !fichiers.length) {
    $("resultat-import").textContent = "Choisir le cours, indiquer le lab et sélectionner des PDF.";
    return;
  }
  const form = new FormData();
  form.append("cours", cours);
  form.append("groupe", $("choix-groupe").value);
  form.append("lab", $("lab").value.trim());
  for (const f of fichiers) form.append("fichiers", f);
  $("resultat-import").textContent = "Import en cours…";
  const r = await fetch(`${API}/import`, { method: "POST", body: form });
  if (!r.ok) { $("resultat-import").textContent = await erreurApi(r); return; }
  afficherRecap(await r.json());
  $("fichiers-pdf").value = "";
  await charger();
};

const RAISONS = {
  ambigu: "plusieurs étudiants possibles",
  aucune_correspondance: "aucun nom reconnu",
  da_inconnu: "DA absent des listes",
  deja_importe: "déjà importé pour ce lab",
};

function afficherRecap(d) {
  const zone = $("resultat-import");
  zone.replaceChildren(texte("strong", `${d.ranges.length} rangé(s), ${d.en_attente.length} à trancher, ${d.refuses.length} refusé(s)`));
  const liste = document.createElement("ul");
  for (const [g, n] of Object.entries(d.par_groupe)) liste.append(texte("li", `Groupe ${g} : ${n} rangé(s)`));
  for (const x of d.en_attente) liste.append(texte("li", `À trancher : ${x.fichier} (${RAISONS[x.raison] ?? x.raison})`));
  for (const x of d.refuses) liste.append(texte("li", `Refusé : ${x.fichier} (${x.raison})`));
  zone.append(liste);
  // Équipe détectée sur la page titre, à vérifier : modifiable pour chaque rapport rangé.
  const equipes = texte("details", "");
  equipes.open = d.ranges.some((y) => y.equipe.length);
  equipes.append(texte("summary", "Équipes détectées (à vérifier)"));
  for (const x of d.ranges) {
    const l = texte("div", `${x.etudiant.prenom} ${x.etudiant.nom} : ${x.equipe.length ? "avec " + x.equipe.map((c) => `${c.prenom} ${c.nom}`).join(", ") : "seul(e)"} `, "rap");
    const b = texte("button", "Modifier l'équipe", "bk");
    b.onclick = () => {
      if (l.nextElementSibling?.classList.contains("equipe-edition")) { l.nextElementSibling.remove(); return; }
      l.after(editerEquipe(d.cours, x.groupe, d.lab, x.etudiant.id, x.equipe, charger));
    };
    l.append(b);
    equipes.append(l);
  }
  if (d.ranges.length) zone.append(equipes);
}

charger().catch(() => {});

// --- Navigation entre les vues et accueil ---
const VUES = ["accueil", "biblio", "importer", "outils"];

function aller(vue) {
  if (!VUES.includes(vue)) vue = "accueil";
  for (const v of VUES) $("v-" + v).hidden = v !== vue;
  document.querySelectorAll("#nav button").forEach((b) => b.classList.toggle("on", b.dataset.v === vue));
  if (location.hash !== "#" + vue) history.replaceState(null, "", "#" + vue);
  scrollTo(0, 0);
}
document.querySelectorAll("#nav button").forEach((b) => { b.onclick = () => aller(b.dataset.v); });
document.querySelectorAll("[data-go]").forEach((b) => { b.onclick = () => aller(b.dataset.go); });
window.onhashchange = () => aller(location.hash.slice(1));

function rendreAccueil() {
  let dernier = null;
  try { dernier = JSON.parse(localStorage.getItem("dernier")); } catch { /* aucun rapport ouvert */ }
  const zone = $("continuer");
  zone.replaceChildren();
  if (dernier?.url) {
    const carte = texte("div", "", "carte");
    carte.append(texte("b", dernier.nom || "Dernier rapport"), texte("small", ` · ${dernier.cours} · ${dernier.lab} · groupe ${dernier.groupe}`));
    const lien = texte("a", "Reprendre la correction", "gros");
    lien.href = dernier.url;
    carte.append(document.createElement("br"), document.createElement("br"), lien);
    zone.append(texte("h2", "Continuer"), carte);
  }
  const cartes = $("a-corriger");
  cartes.replaceChildren();
  for (const c of arbre) {
    const labs = [...new Set(c.etudiants.flatMap((e) => e.labs))].sort();
    for (const lab of labs) {
      if (labFini(c, lab)) continue;
      const total = c.etudiants.filter((e) => e.labs.includes(lab)).length;
      const faits = c.etudiants.filter((e) => e.termines.includes(lab)).length;
      const carte = texte("div", "", "carte");
      carte.append(texte("b", lab), texte("small", ` · ${c.cours} · groupe ${c.groupe}`), document.createElement("br"),
        texte("small", `${faits} / ${total} terminés`), document.createElement("br"));
      const barre = document.createElement("progress");
      barre.max = total; barre.value = faits;
      const ouvrir = texte("button", "Ouvrir le lab", "bk");
      ouvrir.onclick = () => {
        for (const cle of [c.cours, `${c.cours}/${lab}`, `${c.cours}/${lab}/${c.groupe}`]) stockage.ecrire("ouvert:" + cle, "1");
        stockage.ecrire("filtre", "cours");
        rendreArbre();
        aller("biblio");
      };
      const suivi = texte("a", "Suivi", "bk");
      suivi.href = `suivi.html?${new URLSearchParams({ cours: c.cours, lab })}`;
      carte.append(barre, document.createElement("br"), ouvrir, suivi);
      cartes.append(carte);
    }
  }
  if (!cartes.children.length) cartes.append(texte("p", arbre.length ? "Rien à corriger : tout est terminé." : "Aucune classe importée : commence par « Importer ».", "aide"));
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
