// Export par lot pour LÉA : Travaux.zip (PDF corrigés) + tableau récapitulatif (CSV), à côté de chaque lab.
// Rien n'est écrit dans la bibliothèque; le moteur prépare le ZIP en arrière-plan (progression ci-dessous).
// Direction Atelier : ce qui part (inclus / exclus), état « périmé », progression chiffrée, ZIP prêt. Styles : outils.css.
(() => {
  if (!document.querySelector("link[href='outils.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "outils.css";
    document.head.append(l);
  }
  const API_EXPORT = "/api/export-lot";
  const enc = encodeURIComponent;
  const el = (tag, contenu, classe) => {
    const e = document.createElement(tag);
    if (contenu) e.textContent = contenu;
    if (classe) e.className = classe;
    return e;
  };
  const avecIcone = (e, nom, libelle) => { e.replaceChildren(UI.icone(nom), document.createTextNode(libelle)); return e; };

  // « 2026-10-20T14:32:05 » -> « 2026-10-20 à 14 h 32 »
  const dateFr = (iso) => (iso ? iso.slice(0, 10) + " à " + iso.slice(11, 13) + " h " + iso.slice(14, 16) : "");

  function banniere(x) {
    const b = el("div", "", "banniere");
    b.setAttribute("role", "status");
    const corps = el("div", "", "corps");
    const reste = x?.non_exportes ? ` ${x.non_exportes} rapport(s) pas encore exporté(s).` : "";
    if (!x || x.statut === "jamais") {
      b.append(UI.icone("info"), Object.assign(corps, { textContent: "Jamais exporté." }));
    } else if (x.statut === "perime") {
      b.classList.add("attention"); b.setAttribute("role", "alert");
      corps.append(el("b", "Export périmé : "), document.createTextNode(`${x.modifies} rapport(s) modifié(s) depuis le dernier export (${dateFr(x.date)}). Refais l'export.${reste}`));
      b.append(UI.icone("triangle-alert"), corps);
    } else {
      b.classList.add("ok");
      corps.textContent = `Dernier export à jour (${dateFr(x.date)}).${reste}`;
      b.append(UI.icone("circle-check"), corps);
    }
    return b;
  }

  window.blocExportLea = (cours, lab, groupes) => {
    const zone = el("div", "", "export-bloc");
    const tete = el("div", "", "export-tete");
    tete.append(UI.icone("file-down", "l"), el("b", "Exporter pour LÉA"));

    const choix = document.createElement("select");
    choix.className = "saisie";
    choix.title = "Groupe à exporter";
    choix.setAttribute("aria-label", "Groupe à exporter");
    const tous = el("option", groupes.length > 1 ? "Tous les groupes" : `Groupe ${groupes[0]}`);
    tous.value = "";
    choix.append(tous, ...(groupes.length > 1 ? groupes.map((g) => { const o = el("option", `Groupe ${g}`); o.value = g; return o; }) : []));
    choix.hidden = groupes.length < 2;
    tete.append(el("span", "", "esp"), choix);

    const lignes = el("ul", "", "export-lignes");
    lignes.setAttribute("aria-live", "polite");

    const etiquette = el("label", "", "interrupteur inacheves");
    const inacheves = document.createElement("input");
    inacheves.type = "checkbox";
    inacheves.checked = false;
    etiquette.append(inacheves, el("i"), el("span", "Inclure les rapports inachevés (signalés dans le tableau)"));

    const etat = el("div", "", "export-etat");
    const exporter = el("button", "", "btn primaire");
    exporter.type = "button";
    avecIcone(exporter, "file-down", "Préparer Travaux.zip");
    const tableau = el("a", "", "btn");
    avecIcone(tableau, "table", "Tableau (CSV)");
    tableau.title = "Une ligne par étudiant (coéquipiers inclus) : DA, fautes, pénalité, note, état";
    const actions = el("div", "", "export-actions");
    actions.append(tableau, exporter);
    const suivi = el("div", "", "suivi-export");
    suivi.setAttribute("aria-live", "polite");

    const groupe = () => choix.value;
    const parametres = () => new URLSearchParams({ ...(groupe() ? { groupe: groupe() } : {}), inacheves: inacheves.checked });

    // Une ligne par catégorie : « 12 rapports corrigés — inclus ». Les inachevés sont inclus seulement si la case est cochée.
    const ligne = (n, libelle, sort, classe = "") => {
      const li = el("li", "", classe);
      li.append(el("b", String(n), "num"), el("span", libelle, "libelle"), el("span", sort, "pastille " + (sort === "exclus" ? "p-neutre" : sort === "inclus" ? "p-fini" : "")));
      return li;
    };

    async function majApercu() {
      tableau.href = `${API_EXPORT}/tableau/${enc(cours)}/${enc(lab)}?${parametres()}`;
      try {
        const q = groupe() ? `?groupe=${enc(groupe())}` : "";
        const a = await (await fetch(`${API_EXPORT}/apercu/${enc(cours)}/${enc(lab)}${q}`)).json();
        const sortInachevee = inacheves.checked ? "inclus, signalé" : "exclus";
        const rangees = [];
        if (!a.total) rangees.push(el("li", "Aucun rapport rangé pour ce choix.", "aide"));
        else {
          rangees.push(ligne(a.corrige, a.corrige > 1 ? "rapports corrigés" : "rapport corrigé", "inclus"));
          if (a.a_trancher) rangees.push(ligne(a.a_trancher, "avec des fautes à trancher", sortInachevee));
          if (a.non_analyse) rangees.push(ligne(a.non_analyse, "non analysé(s) par Claude", sortInachevee));
          if (a.claude_manquant) rangees.push(ligne(a.claude_manquant, "Claude manquant : relancer l'analyse", sortInachevee));
        }
        lignes.replaceChildren(...rangees);
        etat.replaceChildren(banniere(a.export));
        exporter.disabled = !a.total;
      } catch { lignes.replaceChildren(el("li", "Moteur injoignable.", "aide")); }
    }
    choix.onchange = inacheves.onchange = majApercu;

    function afficherEtat(e) {
      suivi.replaceChildren();
      if (e.statut === "en_cours") {
        const p = el("div", "", "progression");
        const t = el("div", "", "progression-tete");
        t.append(el("span", `Préparation du ZIP${e.courant ? ` — ${e.courant}` : ""}`), el("span", `${e.fait} / ${e.total}`, "num"));
        const barre = document.createElement("progress");
        barre.max = e.total; barre.value = e.fait;
        barre.setAttribute("aria-label", "Progression de l'export");
        p.append(t, barre, el("p", "Cela peut prendre une minute ou plus pour un grand lot; tu peux laisser cette page ouverte.", "aide"));
        suivi.append(p);
      } else if (e.statut === "erreur") {
        const b = el("div", "", "banniere erreur"); b.setAttribute("role", "alert");
        const corps = el("div", e.message || "Export impossible.", "corps");
        b.append(UI.icone("circle-alert"), corps);
        suivi.append(b);
      } else if (e.statut === "pret") {
        const mo = Math.max(0.1, e.taille / 1048576).toFixed(1).replace(".", ",");
        const nom = e.nom || "Travaux.zip";
        const pret = el("div", "", "export-pret");
        const t = el("div", "", "export-pret-tete");
        const ic = el("span", "", "logo-ok"); ic.append(UI.icone("circle-check", "l"));
        const txt = el("div");
        txt.append(el("b", "Nouvel export prêt"), el("div", `${dateFr(e.date)} · ${e.total} PDF · ${mo} Mo`, "mu"));
        t.append(ic, txt);
        const dl = el("a", "", "btn primaire");
        avecIcone(dl, "download", `Télécharger ${nom}`);
        dl.href = `${API_EXPORT}/travaux/${enc(cours)}/${enc(lab)}${e.groupe ? `?groupe=${enc(e.groupe)}` : ""}`;
        dl.download = nom;
        const archiver = el("button", "", "btn");
        archiver.type = "button";
        avecIcone(archiver, "archive", "Marquer ce lab terminé");
        archiver.title = "Facultatif : le lab passe dans « Terminés » (rien n'est supprimé)";
        archiver.onclick = async () => {
          for (const g of e.groupes) {
            await fetch(`/api/bibliotheque/archive/${enc(cours)}/${enc(g)}/${enc(lab)}`, {
              method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ archive: true }),
            });
          }
          UI.toast("Lab marqué terminé");
          await window.charger?.();
        };
        majApercu(); // le dernier export vient d'être noté
        pret.append(t, el("p", "PDF au nom d'origine + « _corrige ». Une fois remis dans LÉA, tu peux archiver le lab (le dépôt dans LÉA se fait à la main).", "aide"),
          el("div", "", "export-actions"));
        pret.lastChild.append(archiver, dl);
        suivi.append(pret);
      }
    }

    let minuterie = null;
    async function suivre() {
      clearTimeout(minuterie);
      let e;
      try { e = await (await fetch(`${API_EXPORT}/etat`)).json(); } catch { minuterie = setTimeout(suivre, 2000); return; }
      if (e.cours !== cours || e.lab !== lab) { suivi.replaceChildren(); return; }
      afficherEtat(e);
      exporter.disabled = e.statut === "en_cours";
      if (e.statut === "en_cours") minuterie = setTimeout(suivre, 600);
    }

    exporter.onclick = async () => {
      exporter.disabled = true;
      const r = await fetch(`${API_EXPORT}/${enc(cours)}/${enc(lab)}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ groupe: groupe() || null, inacheves: inacheves.checked }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        UI.toast(d.detail || `Erreur ${r.status}`, { erreur: true });
        exporter.disabled = false;
        return;
      }
      suivre();
    };

    zone.append(tete, lignes, etiquette, etat, actions, suivi);
    majApercu();
    suivre(); // reprend l'affichage si un export de ce lab est en cours ou prêt (page rechargée)
    return zone;
  };
})();
