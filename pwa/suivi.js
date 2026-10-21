// Tableau de suivi d'un lab : un seul appel au moteur (GET /api/suivi/<cours>/<lab>) pour tous les rapports.
(async () => {
  const q = new URLSearchParams(location.search);
  const cours = q.get("cours"), lab = q.get("lab");
  const $ = (id) => document.getElementById(id);
  const el = (tag, contenu = "", classe = "") => {
    const n = document.createElement(tag);
    n.textContent = contenu; // jamais de HTML : les noms viennent de la bibliothèque
    if (classe) n.className = classe;
    return n;
  };
  const lire = (cle, defaut) => { try { return localStorage.getItem("suivi:" + cle) ?? defaut; } catch { return defaut; } };
  const ecrire = (cle, v) => { try { localStorage.setItem("suivi:" + cle, v); } catch { /* stockage indisponible */ } };
  const F = { moderee: "modérée", marquee: "marquée", faible: "faible" };
  let donnees = { rapports: [], groupes: [], compte: {} };

  const charger = async () => {
    const r = await fetch(`/api/suivi/${encodeURIComponent(cours)}/${encodeURIComponent(lab)}`);
    if (!r.ok) { $("message").textContent = "Impossible de lire le suivi de ce lab."; return; }
    donnees = await r.json();
    rendre();
  };

  const lien = (r) => {
    const p = new URLSearchParams({ cours, groupe: r.groupe, lab, etudiant: r.etudiant, nom: `${r.prenom} ${r.nom}`, fg: lire("groupe", "") });
    return `lecteur.html?${p}`;
  };

  const cellule = (libelle, pastille, classe, detail) => {
    const d = el("div");
    d.append(el("span", libelle, "lib"));
    if (pastille) d.append(el("span", pastille, `pastille ${classe}`));
    else d.append(document.createTextNode("—"));
    if (detail) d.append(el("small", detail));
    return d;
  };

  const analyser = async (r, bouton) => {
    if (!confirm(`Analyser ${r.prenom} ${r.nom} avec Claude (français et indices d'IA) ? Cela compte dans ta limite d'usage.`)) return;
    bouton.disabled = true;
    const rep = await fetch(`/api/lot/${[cours, r.groupe, lab, r.etudiant].map(encodeURIComponent).join("/")}`, { method: "POST" });
    if (!rep.ok) { $("message").textContent = (await rep.json().catch(() => ({}))).detail || `Erreur ${rep.status}`; bouton.disabled = false; return; }
    $("message").textContent = `Analyse de ${r.prenom} ${r.nom} en cours…`;
    for (;;) {
      await new Promise((ok) => setTimeout(ok, 1500));
      const e = await (await fetch("/api/lot")).json();
      if (e.statut !== "en_cours") { $("message").textContent = e.erreurs?.length ? e.erreurs[0].message : e.message; break; }
    }
    await charger();
  };

  const terminer = async (r) => {
    const corps = { termine: !r.termine };
    if (!r.termine) {
      const note = prompt("Note du rapport (ex. 17,5), facultatif :", r.note ?? "");
      if (note === null) return;
      corps.note = note.trim();
    }
    const rep = await fetch(`/api/bibliotheque/statut/${[cours, r.groupe, lab, r.etudiant].map(encodeURIComponent).join("/")}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
    if (!rep.ok) { $("message").textContent = "Impossible d'enregistrer le statut."; return; }
    await charger();
  };

  // « 2026-10-20T14:32:05 » -> « 2026-10-20 à 14 h 32 »
  const dateFr = (iso) => (iso ? iso.slice(0, 10) + " à " + iso.slice(11, 13) + " h " + iso.slice(14, 16) : "");

  const ligne = (r) => {
    const l = el("div", "", "ligne" + (r.termine ? " fini" : ""));
    const nom = el("div", "", "nom");
    const a = el("a", `${r.nom}, ${r.prenom}`); a.href = lien(r);
    if (r.equipe.length) a.append(el("small", `avec ${r.equipe.join(", ")}`));
    nom.append(a);
    const fr = r.francais;
    l.append(nom,
      cellule("Annotation", r.annotation ? "commencée" : "pas commencée", r.annotation ? "p-fini" : "p-neutre"),
      fr.etat === "non_analyse" ? cellule("Français", "non analysé", "p-neutre")
        : fr.etat === "tranche" && fr.claude_manquant
          ? cellule("Français", "Claude manquant", "p-alerte", `${fr.acceptees} acceptée(s) · −${fr.penalite} pt · relancer l'analyse`)
          : cellule("Français", fr.etat === "tranche" ? "tranché" : `${fr.a_trancher} à trancher`, fr.etat === "tranche" ? "p-fini" : "p-cours",
            `${fr.acceptees} acceptée(s) · −${fr.penalite} pt`),
      r.ia ? cellule("Indice d'IA", F[r.ia] || r.ia, r.ia === "marquee" ? "p-alerte" : r.ia === "moderee" ? "p-cours" : "p-fini", "à revérifier")
        : cellule("Indice d'IA", "non analysé", "p-neutre"));
    const p = r.plagiat;
    l.append(p ? cellule("Plagiat", { suspecte: "paire suspecte", confirmee: "confirmée", ecartee: "écartée" }[p.etat],
      p.etat === "ecartee" ? "p-neutre" : "p-alerte", p.etat === "ecartee" ? "" : `avec ${p.avec.join(", ")} (à revérifier)`)
      : cellule("Plagiat", "", ""));
    const act = el("div", "", "act");
    act.append(el("span", { a_corriger: "à corriger", en_cours: "en cours", termine: "terminé" }[r.etat] + (r.termine && r.note ? ` · ${r.note}` : ""),
      "pastille " + { a_corriger: "p-nouv", en_cours: "p-cours", termine: "p-fini" }[r.etat]));
    if (!r.termine && (r.francais.etat === "non_analyse" || !r.ia)) {
      const b = el("button", "Analyser", "bk"); b.onclick = () => analyser(r, b); act.append(b);
    }
    const t = el("button", r.termine ? "↩ Ré-ouvrir" : "✔ Terminé", "bk"); t.onclick = () => terminer(r);
    const o = el("a", "Ouvrir", "gros"); o.href = lien(r);
    act.append(t, o);
    l.append(act);
    return l;
  };

  function rendre() {
    const filtre = lire("filtre", "cours"), groupe = lire("groupe", "");
    $("titre").textContent = `Suivi du ${lab} · ${cours}`;
    document.title = `Suivi ${lab} · ${cours}`;
    const c = donnees.compte;
    $("resume").replaceChildren(...[[donnees.total, "rapports"], [c.a_corriger, "à corriger"], [c.en_cours, "en cours"],
      [c.termine, "terminés"], [c.a_revoir, "⚠ à revoir"]].map(([n, t]) => { const s = el("span", ` ${t}`); s.prepend(el("b", String(n ?? 0))); return s; }));
    if (donnees.archive) $("resume").append(el("span", "lab archivé"));
    const ex = donnees.export || {}, quand = dateFr(ex.date);
    const bandeau = $("export");
    bandeau.className = "aide" + (ex.statut === "perime" ? " export-perime" : "");
    bandeau.textContent = ex.statut === "jamais" ? "Export pour LÉA : jamais exporté."
      : ex.statut === "perime" ? `⚠ Export pour LÉA PÉRIMÉ : ${ex.modifies} rapport(s) modifié(s) depuis le dernier export (${quand}). Refaire l'export.`
      : `Export pour LÉA à jour (${quand})` + (ex.non_exportes ? `, ${ex.non_exportes} rapport(s) pas encore exporté(s).` : ".");
    const sel = $("groupe");
    sel.replaceChildren(...[["", "Tous les groupes"], ...donnees.groupes.map((g) => [g, `Groupe ${g}`])].map(([v, t]) => { const o = el("option", t); o.value = v; return o; }));
    sel.value = groupe;
    document.querySelectorAll("#filtres button").forEach((b) => b.classList.toggle("on", b.dataset.f === filtre));
    let lignes = donnees.rapports.filter((r) => !groupe || r.groupe === groupe);
    if (filtre === "cours") lignes = lignes.filter((r) => !r.termine);
    if (filtre === "revoir") lignes = lignes.filter((r) => r.a_revoir && !r.termine);
    const tab = $("tab");
    tab.replaceChildren();
    const tete = el("div", "", "ligne tete");
    tete.append(...["Étudiant", "Annotation", "Français", "Indice d'IA", "Plagiat", "État"].map((t) => el("div", t)));
    tab.append(tete);
    if (!lignes.length) tab.append(el("p", filtre === "cours" ? "Rien à corriger ici : tout est terminé." : "Aucun rapport.", "aide"));
    let g = null;
    for (const r of lignes) {
      if (r.groupe !== g) {
        g = r.groupe;
        tab.append(el("div", `Groupe ${g} · ${lignes.filter((x) => x.groupe === g).length} rapport(s)`, "ligne titre-groupe"));
      }
      tab.append(ligne(r));
    }
  }

  document.querySelectorAll("#filtres button").forEach((b) => {
    b.onclick = () => { ecrire("filtre", b.dataset.f); rendre(); };
  });
  $("groupe").onchange = (e) => { ecrire("groupe", e.target.value); rendre(); };
  $("fil").textContent = `› ${cours} › ${lab}`;
  try { for (const cle of [cours, `${cours}/${lab}`]) localStorage.setItem("ouvert:" + cle, "1"); } catch { /* stockage indisponible */ }
  await charger();
})();
