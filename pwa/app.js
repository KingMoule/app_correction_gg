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
        const ia = texte("button", "IA", "bouton-ia");
        ia.title = "Indices d'IA";
        ia.onclick = () => window.ouvrirIndicesIA?.(c.cours, c.groupe, lab, e);
        ligne.append(ia);
      }
      bloc.append(ligne);
    }
    zone.append(bloc);
  }
  $("choix-classe").replaceChildren(...arbre.map((c, i) => {
    const o = texte("option", `${c.cours} · groupe ${c.groupe}`);
    o.value = i;
    return o;
  }));
  window.rafraichirLot?.(arbre);
  await chargerAttente();
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
  };
  for (const item of liste) {
    const classe = arbre.find((c) => c.cours === item.cours && c.groupe === item.groupe);
    const bloc = texte("div", "", "attente-item");
    bloc.append(texte("strong", item.fichier), texte("p", `${raisons[item.raison]} · ${item.lab}`));
    const choix = document.createElement("select");
    const vide = texte("option", "Choisir un étudiant…");
    vide.value = "";
    choix.append(vide);
    const proposes = item.candidats.length ? item.candidats : (classe?.etudiants ?? []);
    for (const e of proposes) {
      const o = texte("option", `${e.nom}, ${e.prenom}`);
      o.value = e.id;
      choix.append(o);
    }
    const ok = texte("button", "Ranger");
    ok.onclick = () => trancher(item.id, choix.value);
    const non = texte("button", "Écarter");
    non.onclick = () => trancher(item.id, null);
    bloc.append(choix, ok, non);
    zone.append(bloc);
  }
}

async function trancher(id, etudiant) {
  if (etudiant === "") return;
  await fetch(`${API}/attente/${id}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ etudiant }),
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
  const c = arbre[$("choix-classe").value];
  const fichiers = $("fichiers-pdf").files;
  if (!c || !$("lab").value.trim() || !fichiers.length) {
    $("resultat-import").textContent = "Choisir la classe, indiquer le lab et sélectionner des PDF.";
    return;
  }
  const form = new FormData();
  form.append("cours", c.cours);
  form.append("groupe", c.groupe);
  form.append("lab", $("lab").value.trim());
  for (const f of fichiers) form.append("fichiers", f);
  $("resultat-import").textContent = "Import en cours…";
  const r = await fetch(`${API}/import`, { method: "POST", body: form });
  if (!r.ok) { $("resultat-import").textContent = await erreurApi(r); return; }
  const d = await r.json();
  $("resultat-import").textContent =
    `${d.ranges.length} rangé(s), ${d.en_attente.length} à trancher, ${d.refuses.length} refusé(s)` +
    (d.refuses.length ? ` : ${d.refuses.map((x) => `${x.fichier} (${x.raison})`).join(", ")}` : "");
  $("fichiers-pdf").value = "";
  await charger();
};

charger().catch(() => {});
