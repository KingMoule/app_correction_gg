// Fiche d'un étudiant (GET /api/etudiant/<cours>/<groupe>/<id>) : un rapport par lab avec son état, sa note et son équipe,
// l'historique (rapports remplacés, fichiers écartés), « Équipe… » et « Copier le DA ». Panneau à droite en paysage et sur PC,
// feuille depuis le bas en portrait (sous 900 px). Aucune donnée d'étudiant dans l'adresse : seulement cours, groupe et id.
//   FicheEtudiant.ouvrir({ cours, groupe, id, titreLab?, apres? })   `apres` : rappelé après un changement d'équipe.
// textContent seulement : aucun HTML venu des données.
(() => {
  if (!document.querySelector("link[href='fiche-etudiant.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "fiche-etudiant.css";
    document.head.append(l);
  }
  const el = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };
  const ETATS = { a_corriger: ["Reçu", "p-neutre"], en_cours: ["En cours", "p-nouv"], termine: ["Terminé", "p-fini"] };
  const date = (iso) => new Date(iso).toLocaleDateString("fr-CA", { day: "numeric", month: "short" });
  const nomComplet = (m) => `${m.prenom} ${m.nom}`;

  let courant = null; // { racine, sortir } : une seule fiche à la fois

  async function copier(texte) {
    try { await navigator.clipboard.writeText(texte); return true; } catch {
      const t = el("textarea"); t.value = texte; t.setAttribute("readonly", ""); t.style.cssText = "position:fixed;opacity:0";
      document.body.append(t); t.select();
      const ok = document.execCommand?.("copy") ?? false;
      t.remove();
      return ok;
    }
  }

  const fermer = () => courant?.sortir();

  function entete(f, sortir) {
    const t = el("div", "fiche-tete");
    if (f) {
      t.append(el("span", "avatar", `${f.prenom[0] ?? ""}${f.nom[0] ?? ""}`.toUpperCase()));
      const noms = el("div", "noms");
      noms.append(el("b", "", nomComplet(f)), el("span", "mu", `DA ${f.da || "?"} · ${UI.titreCours(f.cours)} gr. ${f.groupe}`));
      t.append(noms);
      if (f.retire) t.append(el("span", "pastille p-neutre", "Retiré"));
    } else t.append(el("b", "", "Fiche de l'étudiant"));
    const x = el("button", "btn-ico fiche-fermer"); x.type = "button";
    x.setAttribute("aria-label", "Fermer la fiche"); x.append(UI.icone("x"));
    x.onclick = sortir;
    t.append(el("span", "esp"), x);
    return t;
  }

  function rendre(racine, f, { sortir, titreLab, apres }) {
    racine.setAttribute("aria-label", `Fiche de ${nomComplet(f)}`);
    const poignee = el("span", "fiche-poignee"); poignee.setAttribute("aria-hidden", "true");
    const corps = el("div", "fiche-corps");
    // Le rapport qui compte pour une ligne : le sien, ou celui du coéquipier qui le couvre (dernier de `equipe`).
    const depositaire = (r) => (r.par_equipe ? r.equipe[r.equipe.length - 1] : f);

    corps.append(el("h3", "", "Rapports"));
    if (!f.rapports.length) corps.append(el("p", "fiche-vide", "Aucun rapport rangé pour cet étudiant."));
    for (const r of f.rapports) {
      const ligne = el("div", "fiche-rapport");
      ligne.append(el("span", "lab", titreLab(r.lab)));
      const [libelle, classe] = ETATS[r.etat] ?? ["", "p-neutre"];
      const d = el("span", "d");
      d.append(el("b", `etat ${classe}`, r.note ? `${libelle} · ${r.note}` : libelle));
      const autres = r.equipe.filter((m) => !(m.id === f.id && m.groupe === f.groupe));
      const precisions = [];
      if (r.par_equipe) precisions.push(`couvert par le rapport de ${nomComplet(depositaire(r))}`);
      else if (autres.length) precisions.push(`équipe avec ${autres.map(nomComplet).join(", ")}`);
      if (r.archive) precisions.push("lab clos");
      if (precisions.length) d.append(el("span", "", precisions.join(" · ")));
      const a = el("a", "btn", "Ouvrir");
      a.href = `lecteur.html?${new URLSearchParams({ cours: f.cours, groupe: r.groupe, lab: r.lab, etudiant: r.etudiant, nom: nomComplet(depositaire(r)) })}`;
      a.setAttribute("aria-label", `Ouvrir le rapport ${titreLab(r.lab)}`);
      ligne.append(d, a);
      corps.append(ligne);
    }

    corps.append(el("h3", "", "Historique"));
    const hist = el("div", "fiche-hist");
    const h = f.historique;
    const lignes = [
      ...h.remplaces.map((x) => `${titreLab(x.lab)} : rapport remplacé le ${date(x.date)} (l'ancien est gardé).`),
      ...h.ecartes.map((x) => `Fichier écarté le ${date(x.date)} : ${x.fichier}${x.lab ? ` (${titreLab(x.lab)})` : ""}.`),
    ];
    if (!lignes.length) hist.append(el("p", "", "Rien : aucun rapport remplacé ni fichier écarté."));
    for (const l of lignes) hist.append(el("p", "", l));
    corps.append(hist);

    const pied = el("div", "fiche-pied");
    const equipe = el("button", "btn"); equipe.type = "button";
    equipe.append(UI.icone("users"), "Équipe…");
    equipe.disabled = !f.rapports.length;
    const ouvrirEquipe = (r) => Equipe.ouvrir({ cours: f.cours, groupe: r.groupe, lab: r.lab, etudiant: r.etudiant, nom: nomComplet(depositaire(r)), apres });
    if (f.rapports.length === 1) equipe.onclick = () => ouvrirEquipe(f.rapports[0]);
    else if (f.rapports.length) UI.menu(equipe, f.rapports.map((r) => ({ libelle: titreLab(r.lab), icone: "users", surClic: () => ouvrirEquipe(r) })));
    const da = el("button", "btn tertiaire"); da.type = "button";
    da.append(UI.icone("copy"), "Copier le DA");
    da.disabled = !f.da;
    da.onclick = async () => UI.toast((await copier(f.da)) ? `DA ${f.da} copié` : "Copie impossible sur cet appareil");
    pied.append(equipe, da);

    racine.replaceChildren(poignee, entete(f, sortir), corps, pied);
  }

  async function ouvrir({ cours, groupe, id, titreLab = (l) => window.Coque?.titreLab?.(l) ?? l, apres }) {
    fermer();
    const avant = document.activeElement;
    const scrim = el("div", "fiche-scrim");
    const racine = el("aside", "fiche");
    racine.setAttribute("role", "dialog");
    racine.setAttribute("aria-label", "Fiche de l'étudiant");
    racine.tabIndex = -1;
    const clavier = (ev) => { if (ev.key === "Escape" && !document.querySelector("dialog[open], .menu")) { ev.stopPropagation(); sortir(); } };
    function sortir() {
      document.removeEventListener("keydown", clavier, true);
      scrim.remove(); racine.remove();
      document.body.classList.remove("fiche-ouverte");
      if (courant?.racine === racine) courant = null;
      if (avant?.isConnected) avant.focus?.();
    }
    courant = { racine, sortir };
    scrim.onclick = sortir;
    racine.append(el("p", "fiche-charge", "Chargement…"));
    document.body.append(scrim, racine);
    document.body.classList.add("fiche-ouverte");
    document.addEventListener("keydown", clavier, true);
    racine.focus();

    const url = `/api/etudiant/${[cours, groupe, id].map(encodeURIComponent).join("/")}`;
    const charger = async (premiere) => {
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`);
        const f = await r.json();
        if (courant?.racine !== racine) return; // fermée ou remplacée pendant le chargement
        const haut = racine.querySelector(".fiche-corps")?.scrollTop ?? 0;
        rendre(racine, f, { sortir, titreLab, apres: async () => { await apres?.(); charger(false); } });
        racine.querySelector(".fiche-corps").scrollTop = haut;
        if (premiere) racine.querySelector(".fiche-fermer").focus();
      } catch (e) {
        if (courant?.racine !== racine || !premiere) return;
        racine.replaceChildren(entete(null, sortir), el("p", "fiche-charge", `Fiche introuvable : ${e.message}`));
        racine.querySelector(".fiche-fermer").focus();
      }
    };
    await charger(true);
  }

  window.FicheEtudiant = { ouvrir, fermer };
})();
