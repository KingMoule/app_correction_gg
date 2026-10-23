// Équipe d'un rapport (coéquipiers) : retirer ou ajouter un étudiant du cours, enregistré tout de suite par
// PUT /api/bibliotheque/equipe/<cours>/<groupe>/<lab>/<étudiant>. Utilisé par le suivi (menu « … » d'une ligne).
//   Equipe.ouvrir({ cours, groupe, lab, etudiant, nom, apres }) : boîte de dialogue (lit la bibliothèque, puis édite).
//   Equipe.editer({ cours, groupe, lab, etudiant, equipe, classes, apres }) : renvoie le panneau d'édition seul.
// `apres` est rappelé après chaque modification enregistrée (le suivi se recharge). textContent seulement : aucun HTML venu des données.
(() => {
  if (!document.querySelector("link[href='equipe.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "equipe.css";
    document.head.append(l);
  }
  const API = "/api/bibliotheque";
  const chemin = (c, g, l, e) => [c, g, l, e].map(encodeURIComponent).join("/");
  const el = (tag, classe, texte) => {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texte != null) n.textContent = texte;
    return n;
  };
  const detail = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;

  function editer({ cours, groupe, lab, etudiant, equipe, classes, apres }) {
    const zone = el("div", "equipe-edition");
    const rendre = (membres) => {
      zone.replaceChildren();
      if (!membres.length) zone.append(el("p", "aide", "Aucun coéquipier : ce rapport est rendu seul(e)."));
      for (const m of membres) {
        const l = el("div", "membre");
        l.append(el("span", "nom", `${m.prenom} ${m.nom}`), el("span", "mu", `groupe ${m.groupe}`));
        const b = el("button", "btn tertiaire"); b.type = "button";
        b.append(UI.icone("x"), document.createTextNode("Retirer"));
        b.setAttribute("aria-label", `Retirer ${m.prenom} ${m.nom} de l'équipe`);
        b.onclick = () => enregistrer(membres.filter((x) => x !== m));
        l.append(b);
        zone.append(l);
      }
      const choix = el("select", "saisie");
      choix.setAttribute("aria-label", "Ajouter un coéquipier");
      choix.append(el("option", "", "Ajouter un coéquipier…"));
      const deja = new Set(membres.map((m) => `${m.groupe}/${m.id}`));
      for (const g of classes.filter((x) => x.cours === cours)) {
        for (const x of g.etudiants.filter((y) => !y.retire && !deja.has(`${g.groupe}/${y.id}`) && !(g.groupe === groupe && y.id === etudiant))) {
          const o = el("option", "", `${x.nom}, ${x.prenom} (groupe ${g.groupe})`);
          o.value = JSON.stringify({ id: x.id, groupe: g.groupe, nom: x.nom, prenom: x.prenom });
          choix.append(o);
        }
      }
      choix.onchange = () => { if (choix.value) enregistrer([...membres, JSON.parse(choix.value)]); };
      zone.append(choix);
    };
    const enregistrer = async (membres) => {
      const r = await fetch(`${API}/equipe/${chemin(cours, groupe, lab, etudiant)}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ equipe: membres.map((m) => ({ groupe: m.groupe, id: m.id })) }) });
      if (!r.ok) { UI.toast(await detail(r), { erreur: true }); return; }
      rendre((await r.json()).equipe);
      await apres?.();
    };
    rendre(equipe);
    return zone;
  }

  async function ouvrir({ cours, groupe, lab, etudiant, nom, apres }) {
    let classes;
    try {
      const r = await fetch(API);
      if (!r.ok) throw new Error(await detail(r));
      classes = await r.json();
    } catch (e) { UI.toast(`Impossible de lire la bibliothèque : ${e.message}`, { erreur: true }); return; }
    const classe = classes.find((c) => c.cours === cours && c.groupe === groupe);
    const equipe = classe?.etudiants.find((e) => e.id === etudiant)?.equipes?.[lab] ?? [];
    const d = el("dialog", "dialogue");
    const forme = el("form"); forme.method = "dialog";
    forme.append(el("h2", "", `Équipe de ${nom}`),
      el("p", "", "Les coéquipiers partagent le rapport et la note (saisie dans LÉA). Chaque changement est enregistré tout de suite."),
      editer({ cours, groupe, lab, etudiant, equipe, classes, apres }));
    const pied = el("div", "dialogue-pied");
    const fermer = el("button", "btn primaire", "Fermer"); fermer.type = "submit";
    pied.append(fermer);
    forme.append(pied);
    d.append(forme);
    d.addEventListener("close", () => d.remove());
    document.body.append(d);
    d.showModal();
    fermer.focus();
  }

  window.Equipe = { ouvrir, editer };
})();
