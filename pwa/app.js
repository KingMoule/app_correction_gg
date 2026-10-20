// Point d'entrée de la PWA. Les écrans (bibliothèque, lecteur) viendront ici.
async function verifierMoteur() {
  const el = document.getElementById("etat");
  try {
    const r = await fetch("/api/etat");
    const d = await r.json();
    el.textContent = `Moteur connecté (v${d.version})`;
    el.className = "ok";
  } catch {
    el.textContent = "Moteur injoignable : l'ordi est-il allumé et sur le même Wi-Fi ?";
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

async function charger() {
  arbre = await (await fetch(API)).json();
  const zone = $("arbre");
  zone.replaceChildren();
  if (!arbre.length) zone.append(texte("p", "Aucune classe importée."));
  for (const c of arbre) {
    const bloc = document.createElement("details");
    bloc.open = true;
    bloc.append(texte("summary", `${c.cours} · groupe ${c.groupe} (${c.etudiants.length})`));
    for (const e of c.etudiants) {
      const ligne = texte("div", `${e.nom}, ${e.prenom} `, "etudiant");
      for (const lab of e.labs) {
        const a = texte("a", lab);
        const q = new URLSearchParams({ cours: c.cours, groupe: c.groupe, lab, etudiant: e.id, nom: `${e.prenom} ${e.nom}` });
        a.href = `lecteur.html?${q}`;
        ligne.append(a);
        const equipe = e.equipes?.[lab];
        if (equipe?.length) ligne.append(texte("small", ` (avec ${equipe.map((x) => `${x.prenom} ${x.nom}`).join(", ")})`));
        const ia = texte("button", "IA", "bouton-ia");
        ia.title = "Indices d'IA";
        ia.onclick = () => window.ouvrirIndicesIA?.(c.cours, c.groupe, lab, e);
        ligne.append(ia);
      }
      bloc.append(ligne);
    }
    zone.append(bloc);
  }
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
    ok.onclick = () => trancher(item.id, choix.value ? JSON.parse(choix.value) : "");
    const non = texte("button", "Écarter");
    non.onclick = () => {
      if (confirm("Écarter ce fichier ? Il sera mis de côté dans le dossier _ecartes (récupérable).")) trancher(item.id, null);
    };
    bloc.append(choix, ok, non);
    zone.append(bloc);
  }
}

async function trancher(id, choix) {
  if (choix === "") return;
  const [etudiant, groupe] = choix ?? [null, null];
  await fetch(`${API}/attente/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ etudiant, groupe }),
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
  ev.target.value = "";
  await charger();
};

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
  for (const x of d.ranges.filter((y) => y.equipe.length)) {
    liste.append(texte("li", `${x.etudiant.prenom} ${x.etudiant.nom} avec ${x.equipe.map((c) => `${c.prenom} ${c.nom}`).join(", ")}`));
  }
  zone.append(liste);
}

charger().catch(() => {});
