// Export par lot pour LÉA : Travaux.zip (PDF corrigés) + tableau récapitulatif (CSV), à côté de chaque lab.
// Rien n'est écrit dans la bibliothèque; le moteur prépare le ZIP en arrière-plan (progression ci-dessous).
(() => {
  const API_EXPORT = "/api/export-lot";
  const enc = encodeURIComponent;
  const el = (tag, contenu, classe) => {
    const e = document.createElement(tag);
    if (contenu) e.textContent = contenu;
    if (classe) e.className = classe;
    return e;
  };

  function resume(a) {
    if (!a.total) return "Aucun rapport rangé pour ce choix.";
    const inacheves = [a.a_trancher && `${a.a_trancher} à trancher`, a.non_analyse && `${a.non_analyse} non analysé(s)`,
      a.claude_manquant && `${a.claude_manquant} Claude manquant`]
      .filter(Boolean).join(", ");
    return `${a.total} rapport(s) : ${a.corrige} corrigé(s)` + (inacheves ? `, ${inacheves}` : "") + ".";
  }

  // « 2026-10-20T14:32:05 » -> « 2026-10-20 à 14 h 32 »
  const dateFr = (iso) => (iso ? iso.slice(0, 10) + " à " + iso.slice(11, 13) + " h " + iso.slice(14, 16) : "");

  function etatExport(x) {
    if (!x || x.statut === "jamais") return "Jamais exporté.";
    const reste = x.non_exportes ? ` ${x.non_exportes} rapport(s) pas encore exporté(s).` : "";
    return x.statut === "perime"
      ? `⚠ Export PÉRIMÉ : ${x.modifies} rapport(s) modifié(s) depuis le dernier export (${dateFr(x.date)}). Refais l'export.${reste}`
      : `Dernier export à jour (${dateFr(x.date)}).${reste}`;
  }

  window.blocExportLea = (cours, lab, groupes) => {
    const zone = el("div", "", "enonce export-lea");
    zone.append(el("b", "Exporter pour LÉA"));

    const choix = document.createElement("select");
    choix.title = "Groupe à exporter";
    const tous = el("option", groupes.length > 1 ? "Tous les groupes" : `Groupe ${groupes[0]}`);
    tous.value = "";
    choix.append(tous, ...(groupes.length > 1 ? groupes.map((g) => { const o = el("option", `Groupe ${g}`); o.value = g; return o; }) : []));
    choix.hidden = groupes.length < 2;

    const etiquette = el("label", "", "inacheves");
    const inacheves = document.createElement("input");
    inacheves.type = "checkbox";
    inacheves.checked = true;
    etiquette.append(inacheves, " Inclure les rapports inachevés (signalés dans le tableau)");

    const apercu = el("span", "…", "aide");
    const exporter = el("button", "Préparer Travaux.zip", "bk principal");
    const tableau = el("a", "Tableau (CSV)", "bk");
    tableau.title = "Une ligne par étudiant (coéquipiers inclus) : DA, fautes, pénalité, note, état";
    const peremption = el("p", "", "aide");
    const suivi = el("div", "", "suivi-export");
    suivi.setAttribute("aria-live", "polite");

    const groupe = () => choix.value;
    const parametres = () => new URLSearchParams({ ...(groupe() ? { groupe: groupe() } : {}), inacheves: inacheves.checked });

    async function majApercu() {
      tableau.href = `${API_EXPORT}/tableau/${enc(cours)}/${enc(lab)}?${parametres()}`;
      try {
        const q = groupe() ? `?groupe=${enc(groupe())}` : "";
        const a = await (await fetch(`${API_EXPORT}/apercu/${enc(cours)}/${enc(lab)}${q}`)).json();
        apercu.textContent = resume(a);
        peremption.textContent = etatExport(a.export);
        peremption.className = "aide" + (a.export?.statut === "perime" ? " export-perime" : "");
        exporter.disabled = !a.total;
      } catch { apercu.textContent = "Moteur injoignable."; }
    }
    choix.onchange = inacheves.onchange = majApercu;

    function afficherEtat(e) {
      suivi.replaceChildren();
      if (e.statut === "en_cours") {
        const barre = document.createElement("progress");
        barre.max = e.total; barre.value = e.fait;
        suivi.append(el("p", `Préparation du ZIP : ${e.fait} / ${e.total}${e.courant ? ` — ${e.courant}` : ""}. ` +
          "Cela peut prendre une minute ou plus pour un grand lot; tu peux laisser cette page ouverte."), barre);
      } else if (e.statut === "erreur") {
        suivi.append(el("p", e.message || "Export impossible.", "erreur"));
      } else if (e.statut === "pret") {
        const mo = Math.max(0.1, e.taille / 1048576).toFixed(1).replace(".", ",");
        const nom = e.nom || "Travaux.zip";
        const dl = el("a", `⬇ Télécharger ${nom} (${mo} Mo)`, "bk principal");
        dl.href = `${API_EXPORT}/travaux/${enc(cours)}/${enc(lab)}${e.groupe ? `?groupe=${enc(e.groupe)}` : ""}`;
        dl.download = nom;
        const archiver = el("button", "Marquer ce lab terminé", "bk");
        archiver.title = "Facultatif : le lab passe dans « Terminés » (rien n'est supprimé)";
        archiver.onclick = async () => {
          for (const g of e.groupes) {
            await fetch(`/api/bibliotheque/archive/${enc(cours)}/${enc(g)}/${enc(lab)}`, {
              method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ archive: true }),
            });
          }
          await window.charger?.();
        };
        majApercu(); // le dernier export vient d'être noté
        suivi.append(el("p", `ZIP prêt (${dateFr(e.date)}) : ${e.total} PDF. Une fois remis dans LÉA, tu peux archiver le lab.`), dl, archiver);
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
        alert(d.detail || `Erreur ${r.status}`);
        exporter.disabled = false;
        return;
      }
      suivre();
    };

    zone.append(choix, etiquette, apercu, peremption, exporter, tableau, suivi);
    majApercu();
    suivre(); // reprend l'affichage si un export de ce lab est en cours ou prêt (page rechargée)
    return zone;
  };
})();
