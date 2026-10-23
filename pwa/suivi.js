// Tableau de suivi d'un lab : un seul appel au moteur (GET /api/suivi/<cours>/<lab>) pour tous les rapports.
// Direction Atelier : tableau dense, filtres segmentés, menu « … » par ligne, balayage d'une ligne au doigt.
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
  const F = { moderee: "Modéré", marquee: "Marqué", faible: "Faible" };
  const FILTRES = ["tout", "a_corriger", "en_cours", "termine", "revoir"];
  let donnees = { rapports: [], groupes: [], compte: {} };
  const enAnalyse = new Set(); // rapports que Claude analyse en ce moment (un seul à la fois côté moteur)

  const chemin = (r) => [cours, r.groupe, lab, r.etudiant].map(encodeURIComponent).join("/");
  const nomComplet = (r) => `${r.prenom} ${r.nom}`;
  const message = (t) => { $("message").textContent = t; };

  const charger = async () => {
    const r = await fetch(`/api/suivi/${encodeURIComponent(cours)}/${encodeURIComponent(lab)}`);
    if (!r.ok) { message("Impossible de lire le suivi de ce lab."); return; }
    donnees = await r.json();
    rendre();
  };

  const lien = (r) => {
    const p = new URLSearchParams({ cours, groupe: r.groupe, lab, etudiant: r.etudiant, nom: nomComplet(r), fg: lire("groupe", "") });
    return `lecteur.html?${p}`;
  };

  // --- Actions (menu « … », balayage) ---
  const analyser = async (r) => {
    if (!(await Dialogue.confirmer({
      titre: `Analyser ${nomComplet(r)} avec Claude ?`,
      texte: "Fautes de français et indices d'IA. Cela compte dans ta limite d'usage.", ok: "Analyser" }))) return;
    const rep = await fetch(`/api/lot/${chemin(r)}`, { method: "POST" });
    if (!rep.ok) { message((await rep.json().catch(() => ({}))).detail || `Erreur ${rep.status}`); return; }
    enAnalyse.add(`${r.groupe}/${r.etudiant}`);
    rendre();
    message(`Analyse de ${nomComplet(r)} en cours…`);
    for (;;) {
      await new Promise((ok) => setTimeout(ok, 1500));
      const e = await (await fetch("/api/lot")).json();
      if (e.statut !== "en_cours") {
        const msg = e.erreurs?.length ? e.erreurs[0].message : e.message;
        message(""); UI.toast(msg || "Analyse terminée.", { erreur: !!e.erreurs?.length });
        break;
      }
    }
    enAnalyse.delete(`${r.groupe}/${r.etudiant}`);
    await charger();
  };

  const statut = async (r, corps) => {
    const rep = await fetch(`/api/bibliotheque/statut/${chemin(r)}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
    if (!rep.ok) { message("Impossible d'enregistrer le statut."); return false; }
    await charger();
    return true;
  };

  const terminer = async (r) => {
    if (r.termine) {
      if (await statut(r, { termine: false })) UI.toast(`${nomComplet(r)} : rapport ré-ouvert`);
      return;
    }
    const note = await Dialogue.saisir({
      titre: `Terminer le rapport de ${nomComplet(r)}`, etiquette: "Note du rapport (reportée dans le CSV pour LÉA)",
      valeur: r.note ?? "", aide: "Facultatif, par exemple 17,5. Vide = sans note.", ok: "Terminer", inputmode: "decimal" });
    if (note === null) return;
    if (await statut(r, { termine: true, note: note.trim() })) {
      UI.toast(`${nomComplet(r)} : rapport terminé`, { action: { libelle: "Annuler", surClic: () => statut(r, { termine: false }) } });
    }
  };

  const peutAnalyser = (r) => !r.termine && (r.francais.etat === "non_analyse" || !r.ia || r.references.etat === "non_analyse") && !enAnalyse.has(`${r.groupe}/${r.etudiant}`);

  const menuLigne = (r) => [
    { libelle: "Ouvrir le rapport", icone: "file-text", surClic: () => { location.href = lien(r); } },
    ...(peutAnalyser(r) ? [{ libelle: "Analyser avec Claude", icone: "sparkles", surClic: () => analyser(r) }] : []),
    { libelle: r.termine ? "Ré-ouvrir le rapport" : "Marquer terminé…", icone: r.termine ? "rotate-ccw" : "circle-check", surClic: () => terminer(r) },
    ...(r.plagiat ? [{ separateur: true }, { libelle: "Voir les paires de plagiat", icone: "scan-search", surClic: () => { location.href = "plagiat.html"; } }] : []),
  ];

  // « 2026-10-20T14:32:05 » -> « 2026-10-20 à 14 h 32 »
  const dateFr = (iso) => (iso ? iso.slice(0, 10) + " à " + iso.slice(11, 13) + " h " + iso.slice(14, 16) : "");

  // --- Cellules ---
  // `suite` : fin du libellé, masquée en portrait pour que le tableau tienne sans défilement horizontal
  const pastille = (texte, classe = "", icone = "", suite = "") => {
    const p = el("span", "", "pastille " + classe);
    if (icone) p.append(UI.icone(icone));
    p.append(document.createTextNode(texte));
    if (suite) p.append(el("span", suite, "suite"));
    return p;
  };
  const mu = (texte) => el("span", texte, "mu");
  const td = (classe, ...contenu) => { const c = el("td", "", classe); c.append(...contenu); return c; };

  const cellFrancais = (r) => {
    const fr = r.francais;
    if (fr.etat === "non_analyse") return td("", mu("Non analysé"));
    const detail = `${fr.acceptees} acceptée(s) · −${String(fr.penalite).replace(".", ",")} pt`;
    if (fr.etat === "tranche" && fr.claude_manquant) {
      const p = pastille("Claude manquant", "");
      p.title = `${detail} · relancer l'analyse`;
      return td("", p);
    }
    if (fr.etat === "tranche") return td("num double", mu(detail));
    const p = pastille(`${fr.a_trancher} à trancher`);
    p.title = detail;
    return td("", p);
  };

  const cellIa = (r) => {
    if (!r.ia) return td("", mu("Non analysé"));
    if (r.ia === "faible") return td("", mu("Faible"));
    return td("", pastille(F[r.ia] || r.ia, "p-ia", "search", "· à revoir"));
  };

  // Références : un indice à revérifier (jamais une note). Le détail est dans l'onglet « Références » du lecteur.
  const cellReferences = (r) => {
    const rf = r.references;
    if (rf.etat === "non_analyse") return td("", mu("Non vérifié"));
    if (rf.etat === "ok") return td("", mu(rf.resume.total ? "Rien à signaler" : "Aucune référence"));
    const s = rf.resume, n = s.introuvables + s.divergentes + s.douteuses + s.sans_lien + s.erreurs_forme + s.liaison;
    const a = el("a", "", "pastille");
    a.href = lien(r) + "&panneau=references";
    a.append(document.createTextNode(s.total || n ? `${n} à revoir` : "Section absente"));
    a.title = `${rf.texte} (indice à revérifier)`;
    a.onclick = (e) => e.stopPropagation();
    const c = td("double", a);
    if (rf.texte) c.append(el("span", rf.texte, "sous-ligne ref-detail"));
    return c;
  };

  // Plusieurs paires : une seule pastille « N paires » (le détail en infobulle et sur l'écran du plagiat), pour garder la ligne à 52 px.
  const cellPlagiat = (r) => {
    const p = r.plagiat;
    if (!p) return td("", mu("—"));
    const n = p.avec.length;
    const etat = { suspecte: "suspecte", confirmee: "confirmée", ecartee: "écartée" }[p.etat];
    const a = el("a", "", "pastille " + (p.etat === "ecartee" ? "p-neutre" : "p-plagiat") + " pl-multi");
    a.href = "plagiat.html";
    a.append(document.createTextNode(n > 1 ? `${n} paires` : etat), el("span", n > 1 ? `${etat}s` : `· avec ${p.avec[0]}`, "suite"));
    a.title = `Plagiat ${etat} avec ${p.avec.join(", ")}${p.etat === "ecartee" ? "" : " (indice à revérifier)"}`;
    a.onclick = (e) => e.stopPropagation();
    return td("", a);
  };

  const ETATS = { a_corriger: ["À corriger", "p-neutre"], en_cours: ["En cours", "p-nouv"], termine: ["Terminé", "p-fini"] };
  const cellEtat = (r) => {
    if (enAnalyse.has(`${r.groupe}/${r.etudiant}`)) return td("", pastille("Claude analyse…", "p-claude", "sparkles"));
    const [t, c] = ETATS[r.etat];
    return td("", pastille(t, c));
  };

  const ligne = (r) => {
    const tr = el("tr", "", r.termine ? "fini" : "");
    tr.tabIndex = 0;
    tr.dataset.cle = `${r.groupe}/${r.etudiant}`;
    const initiales = ((r.prenom[0] || "") + (r.nom[0] || "")).toUpperCase();
    const nom = el("div", "", "nom-etu");
    const bloc = el("div");
    const a = el("a", `${r.prenom} ${r.nom}`); a.href = lien(r);
    if (r.annotation) { const ic = UI.icone("pen"); ic.setAttribute("role", "img"); ic.setAttribute("aria-label", "Annotations commencées"); ic.append(Object.assign(document.createElementNS("http://www.w3.org/2000/svg", "title"), { textContent: "Annotations commencées" })); a.append(ic); }
    bloc.append(a);
    if (r.equipe.length) bloc.append(el("small", `avec ${r.equipe.join(", ")}`));
    nom.append(el("span", initiales, "avatar"), bloc);
    tr.append(td("nom", nom), cellFrancais(r), cellIa(r), cellPlagiat(r), cellReferences(r), cellEtat(r),
      td("nombre val-note", document.createTextNode(r.termine && r.note ? r.note : "—")));
    const plus = el("button", "", "btn-ico");
    plus.type = "button"; plus.setAttribute("aria-label", `Actions pour ${nomComplet(r)}`);
    plus.append(UI.icone("ellipsis", "l"));
    plus.onclick = (e) => e.stopPropagation();
    UI.menu(plus, menuLigne(r));
    tr.append(td("actions act", plus));
    // Toucher la ligne ouvre le rapport (sauf boutons, liens, et geste de balayage)
    tr.addEventListener("click", (e) => { if (!e.target.closest("a, button") && !tr.dataset.glisse) location.href = lien(r); });
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target === tr) location.href = lien(r); });
    tr._rapport = r;
    return tr;
  };

  // --- Balayage d'une ligne (au doigt seulement; le menu « … » donne les mêmes actions) ---
  const conteneur = $("tab");
  let ouverte = null; // { tr, overlay }
  const refermer = () => {
    if (!ouverte) return;
    for (const c of ouverte.tr.cells) c.style.transform = "";
    ouverte.overlay.remove();
    ouverte = null;
  };
  const decaler = (tr, dx) => { for (const c of tr.cells) c.style.transform = dx ? `translateX(${dx}px)` : ""; };
  const LARGEUR_ACTIONS = 216, SEUIL = 72;

  function actionsBalayage(tr) {
    const r = tr._rapport;
    const o = el("div", "", "balayage");
    const bouton = (classe, libelle, icone, fn) => {
      const b = el("button", "", classe); b.type = "button";
      b.append(UI.icone(icone, "l"), document.createTextNode(libelle));
      b.onclick = () => { refermer(); fn(); };
      return b;
    };
    if (r.termine) o.append(bouton("rouvrir", "Ré-ouvrir", "rotate-ccw", () => terminer(r)));
    else {
      if (peutAnalyser(r)) o.append(bouton("analyser", "Analyser", "sparkles", () => analyser(r)));
      o.append(bouton("terminer", "Terminer…", "circle-check", () => terminer(r)));
    }
    o.style.width = `${o.children.length * (LARGEUR_ACTIONS / 2)}px`;
    const boite = conteneur.getBoundingClientRect(), rang = tr.getBoundingClientRect();
    o.style.top = `${rang.top - boite.top + conteneur.scrollTop}px`;
    conteneur.append(o);
    return o;
  }

  function brancherBalayage() {
    let depart = null;
    conteneur.addEventListener("pointerdown", (e) => {
      if (e.pointerType !== "touch") return;
      const tr = e.target.closest("tbody tr:not(.groupe)");
      if (ouverte && !e.target.closest(".balayage") && ouverte.tr !== tr) refermer();
      if (!tr || e.target.closest("button, a")) return;
      depart = { tr, x: e.clientX, y: e.clientY, id: e.pointerId, actif: false, deja: ouverte?.tr === tr, largeur: 0 };
    });
    conteneur.addEventListener("pointermove", (e) => {
      if (!depart || e.pointerId !== depart.id) return;
      const dx = e.clientX - depart.x, dy = e.clientY - depart.y;
      if (!depart.actif) {
        if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { depart = null; return; } // geste de défilement
        if (Math.abs(dx) < 10 || Math.abs(dx) < 1.5 * Math.abs(dy)) return;
        depart.actif = true;
        if (!ouverte) {
          const overlay = actionsBalayage(depart.tr);
          ouverte = { tr: depart.tr, overlay };
        }
        depart.largeur = ouverte.overlay.offsetWidth;
        depart.tr.classList.remove("balaye");
        depart.tr.dataset.glisse = "1";
      }
      const base = depart.deja ? -depart.largeur : 0;
      decaler(depart.tr, Math.max(-depart.largeur - 24, Math.min(0, base + dx)));
    });
    const fin = (e) => {
      if (!depart || e.pointerId !== depart.id) return;
      const d = depart; depart = null;
      if (!d.actif) return;
      const position = (d.deja ? -d.largeur : 0) + (e.clientX - d.x);
      d.tr.classList.add("balaye");
      if (position < -SEUIL) decaler(d.tr, -d.largeur); // reste ouverte
      else refermer();
      setTimeout(() => { delete d.tr.dataset.glisse; }, 350); // le « click » qui suit le relâchement n'ouvre pas le rapport
    };
    conteneur.addEventListener("pointerup", fin);
    conteneur.addEventListener("pointercancel", fin);
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") refermer(); });
  }
  brancherBalayage();

  // --- Rendu ---
  function rendre() {
    refermer();
    let filtre = lire("filtre", "tout");
    if (!FILTRES.includes(filtre)) filtre = "tout"; // anciennes valeurs (« cours »)
    const groupe = lire("groupe", "");
    const c = donnees.compte;
    $("titre").textContent = `Suivi du ${lab}`;
    document.title = `Suivi ${lab} · ${cours}`;
    $("fil").replaceChildren(UI.icone("chevron-right"), document.createTextNode(`${cours} `), UI.icone("chevron-right"), el("b", lab));
    const pas = (donnees.rapports.filter((r) => !r.termine)[0]);
    const nbGroupes = donnees.groupes.length;
    $("sous").textContent = `${donnees.total} rapport(s) · ${cours} · ${nbGroupes} groupe(s)` + (donnees.archive ? " · lab archivé" : "")
      + (pas ? ` · prochain non terminé : ${nomComplet(pas)}` : "");

    const lot = $("vers-lot"); lot.replaceChildren(UI.icone("sparkles"), document.createTextNode("Analyse par lot"));
    const suivant = $("suivant");
    const cible = donnees.rapports.filter((r) => (!groupe || r.groupe === groupe) && !r.termine)[0];
    suivant.hidden = !cible;
    if (cible) { suivant.href = lien(cible); suivant.replaceChildren(UI.icone("pen"), document.createTextNode("Corriger le suivant")); suivant.title = nomComplet(cible); }

    // Progression : terminés et en cours
    const total = donnees.total || 0;
    $("prog").hidden = !total;
    if (total) {
      $("prog-texte").replaceChildren(el("b", String(c.termine ?? 0)), document.createTextNode(` terminés · `), el("b", String(c.en_cours ?? 0)), document.createTextNode(" en cours"));
      $("prog-pct").textContent = `${Math.round(100 * (c.termine ?? 0) / total)} %`;
      const fait = el("i", "", "fait"), cours_ = el("i", "", "cours");
      fait.style.width = `${100 * (c.termine ?? 0) / total}%`; cours_.style.width = `${100 * (c.en_cours ?? 0) / total}%`;
      $("prog-barre").replaceChildren(fait, cours_);
    }

    // État de l'export pour LÉA
    const ex = donnees.export || {}, quand = dateFr(ex.date);
    const ban = $("export");
    if (ex.statut === "perime") {
      const b = el("div", "", "banniere attention"); b.setAttribute("role", "alert");
      const corps = el("div", "", "corps");
      corps.append(el("b", "Export pour LÉA périmé : "), document.createTextNode(`${ex.modifies} rapport(s) modifié(s) depuis le dernier export (${quand}).`));
      const refaire = el("a", "Refaire l'export", "btn"); refaire.href = "/#biblio";
      b.append(UI.icone("triangle-alert"), corps, refaire);
      ban.replaceChildren(b);
    } else {
      const ok = ex.statut !== "jamais";
      const b = el("div", "", "banniere" + (ok ? " ok" : "")); b.setAttribute("role", "status");
      const corps = el("div", "", "corps");
      corps.textContent = ok ? `Export pour LÉA à jour (${quand})` + (ex.non_exportes ? `, ${ex.non_exportes} rapport(s) pas encore exporté(s).` : ".") : "Export pour LÉA : jamais exporté.";
      b.append(UI.icone(ok ? "circle-check" : "info"), corps);
      ban.replaceChildren(b);
    }

    // Filtres segmentés avec compteurs
    const dansGroupe = donnees.rapports.filter((r) => !groupe || r.groupe === groupe);
    const compte = {
      tout: dansGroupe.length, a_corriger: dansGroupe.filter((r) => r.etat === "a_corriger").length,
      en_cours: dansGroupe.filter((r) => r.etat === "en_cours").length, termine: dansGroupe.filter((r) => r.termine).length,
      revoir: dansGroupe.filter((r) => r.a_revoir && !r.termine).length,
    };
    for (const b of document.querySelectorAll("#filtres button")) {
      const on = b.dataset.f === filtre;
      b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on));
      b.querySelector(".n").textContent = String(compte[b.dataset.f]);
    }
    const sel = $("groupe");
    sel.replaceChildren(...[["", "Tous les groupes"], ...donnees.groupes.map((g) => [g, `Groupe ${g}`])].map(([v, t]) => { const o = el("option", t); o.value = v; return o; }));
    sel.value = groupe;
    sel.hidden = donnees.groupes.length < 2 && !groupe;

    let lignes = dansGroupe;
    if (filtre === "a_corriger") lignes = lignes.filter((r) => r.etat === "a_corriger");
    if (filtre === "en_cours") lignes = lignes.filter((r) => r.etat === "en_cours");
    if (filtre === "termine") lignes = lignes.filter((r) => r.termine);
    if (filtre === "revoir") lignes = lignes.filter((r) => r.a_revoir && !r.termine);

    if (!lignes.length) {
      const v = el("div", "", "vide suivi-vide");
      v.append(UI.icone("inbox"), el("p", { a_corriger: "Rien à corriger ici.", en_cours: "Aucun rapport en cours.", termine: "Aucun rapport terminé pour l'instant.",
        revoir: "Rien à revoir : aucun indice à vérifier." }[filtre] || "Aucun rapport."));
      if (filtre !== "tout") {
        const b = el("button", "Voir tous les rapports", "btn"); b.type = "button";
        b.onclick = () => { ecrire("filtre", "tout"); rendre(); };
        v.append(b);
      }
      conteneur.replaceChildren(v);
      return;
    }
    const tab = el("table", "", "tableau");
    const tete = el("thead"); const tr = el("tr");
    for (const [t, cl] of [["Étudiant", ""], ["Français", ""], ["Indice d'IA", ""], ["Plagiat", ""], ["Références", ""], ["État", ""], ["Note", "nombre"], ["", ""]]) {
      const th = el("th", t, cl); th.scope = "col";
      if (!t) th.setAttribute("aria-label", "Actions");
      tr.append(th);
    }
    tete.append(tr); tab.append(tete);
    const corps = el("tbody");
    let g = null;
    for (const r of lignes) {
      if (r.groupe !== g) {
        g = r.groupe;
        const gr = el("tr", "", "groupe"), cel = el("td", `Groupe ${g} · ${lignes.filter((x) => x.groupe === g).length} rapport(s)`);
        cel.colSpan = 8; gr.append(cel); corps.append(gr);
      }
      corps.append(ligne(r));
    }
    tab.append(corps);
    conteneur.replaceChildren(tab);
  }

  UI.segmente($("filtres"), (b) => { ecrire("filtre", b.dataset.f); rendre(); });
  $("groupe").onchange = (e) => { ecrire("groupe", e.target.value); rendre(); };
  $("ic-avert").append(UI.icone("info"));
  try { for (const cle of [cours, `${cours}/${lab}`]) localStorage.setItem("ouvert:" + cle, "1"); } catch { /* stockage indisponible */ }
  await charger();
})();
