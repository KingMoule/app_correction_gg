// Onglet « Références » de l'inspecteur : résultat de /api/references (existence, forme, citations, pertinence).
// Un indice à revérifier, jamais un verdict; rien n'est écrit sur le PDF et aucune pénalité n'en découle.
// Dépend de lecteur.js ($, ref, base), de ui.js (UI) et d'inspecteur.js (InspecteurUI, Inspecteur).
(() => {
  const { h, bouton, banniere, erreurApi } = window.InspecteurUI;
  const racine = $("vue-references");
  const rf = { donnees: undefined, message: "", occupe: false, demande: false, ouvertes: new Set(), style: "iso690", styles: {} };
  const EXISTENCE = {
    trouvee: ["Existe", "p-fini"], introuvable: ["Introuvable", ""], divergente: ["Ne correspond pas", ""], non_verifiable: ["Non vérifiable", "p-neutre"],
  };
  const PERTINENCE = {
    pertinente: ["Pertinente", "p-claude"], douteuse: ["Douteuse", ""], sans_lien: ["Sans lien apparent", ""], non_conclu: ["Non conclu", "p-neutre"],
  };
  const VRAISEMBLANCE = { plausible: "plausible", incertaine: "incertain", peu_plausible: "peu plausible" };
  const STYLES_COURT = { iso690: "ISO 690 (numérique)", apa7: "APA 7 (auteur-date)" };
  const urlSure = (u) => { try { const x = new URL(u); return x.protocol === "http:" || x.protocol === "https:" ? x.href : null; } catch { return null; } };
  const nbSignales = (r) => (r ? r.introuvables + r.divergentes + r.douteuses + r.sans_lien + r.erreurs_forme + r.liaison : 0);

  function pastille(texte, classe, titre) {
    const p = h("span", "pastille " + classe, texte);
    if (titre) p.title = titre;
    return p;
  }
  function majBadge() {
    const n = nbSignales(rf.donnees?.resume), b = $("n-references");
    b.hidden = !n; b.textContent = n;
    b.title = rf.donnees?.resume?.texte ?? "";
  }

  async function charger(force) {
    if ((rf.demande && !force) || ref.some((v) => !v)) return;
    rf.demande = true;
    try {
      const [r, s] = await Promise.all([fetch(`/api/references/resultat/${base}`), fetch(`/api/references/style/${encodeURIComponent(ref[0])}`)]);
      rf.donnees = r.ok ? await r.json() : null;
      if (s.ok) { const d = await s.json(); rf.style = d.style; rf.styles = d.styles; }
      rf.message = "";
    } catch { rf.demande = false; rf.donnees = rf.donnees ?? null; rf.message = "Moteur injoignable."; }
    majBadge(); rendre();
  }
  async function verifier() {
    rf.occupe = true; rf.message = "Vérification en cours : bases de données, puis Claude (une minute environ)…"; rendre();
    try {
      const r = await fetch(`/api/references/analyser/${base}?rafraichir=true`, { method: "POST" });
      if (!r.ok) rf.message = await erreurApi(r);
      else { rf.donnees = await r.json(); rf.message = ""; majBadge(); }
    } catch { rf.message = "Moteur injoignable."; }
    rf.occupe = false; rendre();
  }
  async function changerStyle(style) {
    try {
      const r = await fetch(`/api/references/style/${encodeURIComponent(ref[0])}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ style }) });
      if (!r.ok) throw new Error(await erreurApi(r));
      rf.style = (await r.json()).style;
      UI.toast("Style enregistré pour tout le cours : relance « Revérifier » pour l'appliquer à ce rapport.");
    } catch (e) { UI.toast(e.message || "Style non enregistré.", { erreur: true }); }
    rendre();
  }

  const lien = (e) => urlSure(e.existence?.url) || (e.doi ? urlSure(`https://doi.org/${e.doi}`) : null) || urlSure(e.url);

  // « Pourquoi ? » : les appels à ce numéro que le moteur a écartés, avec la raison, pour repérer un faux négatif.
  function pourquoi(e) {
    const det = h("details", "ref-pourquoi");
    det.append(h("summary", undefined, "Pourquoi ?"));
    const cands = (rf.donnees?.appels_ecartes ?? []).filter((c) => e.numero != null && c.numero === e.numero);
    if (!cands.length) {
      det.append(h("p", "mu", "Aucun appel à ce numéro n'a été trouvé dans le texte, même parmi les candidats écartés."));
      return det;
    }
    det.append(h("p", "mu", "Appels à ce numéro écartés (ce n'étaient pas des appels de référence, d'après le moteur) :"));
    for (const c of cands) {
      const li = h("div", "ref-ecart");
      li.append(h("b", undefined, c.marque), h("span", "mu", ` ${c.raison}`), h("blockquote", undefined, `« ${c.phrase} »`));
      det.append(li);
    }
    return det;
  }

  function detail(e) {
    const d = h("div", "ref-detail");
    d.append(h("p", "ref-brut", e.brut));
    const ex = e.existence;
    d.append(h("h4", "vue-titre", "Existence"), h("p", "vue-texte", ex.detail || ""));
    if (ex.titre) d.append(h("p", "mu", `Titre trouvé : « ${ex.titre} »`));
    const href = lien(e);
    if (href) {
      const a = h("a", "btn tertiaire"); a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.append(UI.icone("external-link"), "Ouvrir la source");
      d.append(a);
    }
    d.append(h("h4", "vue-titre", "Forme"));
    if (e.forme.problemes.length) { const ul = h("ul"); for (const p of e.forme.problemes) ul.append(h("li", undefined, p)); d.append(ul); }
    else d.append(h("p", "vue-texte", "Rien à signaler (vérification partielle de la norme)."));
    d.append(h("h4", "vue-titre", "Citations"),
      h("p", "vue-texte", e.citee ? `Citée ${e.citee} fois dans le texte.` : "Jamais citée dans le texte."));
    if (!e.citee) d.append(pourquoi(e));
    const p = e.pertinence;
    if (p) {
      d.append(h("h4", "vue-titre", "Pertinence"), h("p", "vue-texte", p.explication));
      for (const ph of p.phrases ?? []) d.append(h("blockquote", undefined, `« ${ph} »`));
      if (p.verdict !== "non_conclu") d.append(h("p", "mu", "Jugement de Claude à partir du titre et du résumé de la source : un indice à revérifier."));
      if (p.description) { // source illisible : ce que Claude sait de l'ouvrage, à ne pas confondre avec un jugement sur le texte réel
        const g = h("div", "ref-desc"), ds = p.description;
        g.append(h("b", undefined, "Description générale, non vérifiée dans la source"), h("p", undefined, ds.texte));
        if (ds.avis) g.append(h("p", undefined, `Lien avec la phrase (${VRAISEMBLANCE[ds.vraisemblance] ?? ds.vraisemblance}) : ${ds.avis}`));
        g.append(h("p", "mu", "Tiré des connaissances de Claude, pas de la source : à vérifier toi-même."));
        d.append(g);
      }
    }
    return d;
  }

  function ligne(e) {
    const bloc = h("div", "ref-carte"), ouverte = rf.ouvertes.has(e.id);
    const tete = h("button", "ref-ligne"); tete.type = "button";
    tete.setAttribute("aria-expanded", String(ouverte));
    tete.append(h("span", "ref-num num", e.numero != null ? `[${e.numero}]` : "·"), h("span", "ref-texte", e.brut));
    const pastilles = h("span", "ref-pastilles");
    const [te, ce] = EXISTENCE[e.existence.etat] ?? ["?", "p-neutre"];
    pastilles.append(pastille(te, ce, e.existence.detail));
    if (e.forme.problemes.length) pastilles.append(pastille(`Forme : ${e.forme.problemes.length}`, "", e.forme.problemes.join(" ")));
    if (!e.citee) pastilles.append(pastille("Non citée", ""));
    if (e.pertinence) {
      const [tp, cp] = PERTINENCE[e.pertinence.verdict] ?? ["?", "p-neutre"];
      const decrite = !!e.pertinence.description;
      const p = pastille("", cp, e.pertinence.explication);
      if (cp === "p-claude" || decrite) p.append(UI.icone("sparkles"));
      p.append(decrite ? "Description générale (non vérifiée)" : `Pertinence : ${tp.toLowerCase()}`);
      pastilles.append(p);
    }
    tete.append(pastilles);
    tete.onclick = () => { if (rf.ouvertes.has(e.id)) rf.ouvertes.delete(e.id); else rf.ouvertes.add(e.id); rendre(); };
    bloc.append(tete);
    if (ouverte) bloc.append(detail(e));
    return bloc;
  }

  function rendre() {
    const d = rf.donnees;
    racine.replaceChildren(banniere("Un indice à revérifier, jamais un verdict. Rien n'est écrit sur le PDF et la note n'est pas touchée. Seules les références (titre, auteurs, DOI, adresse) sont cherchées sur Internet.", ""));
    if (d === undefined && !rf.message) { racine.append(h("p", "vue-texte", "Chargement…")); return; }
    if (d) {
      const tete = h("div", "ref-resume");
      tete.append(h("b", undefined, d.resume?.texte ?? ""), h("span", "mu", `${d.resume?.total ?? 0} référence(s) · ${STYLES_COURT[d.style] ?? d.style} · vérifié le ${(d.date || "").slice(0, 10)}`));
      racine.append(tete);
      if (d.hors_ligne) racine.append(banniere("Hors ligne : l'existence des références n'a pas pu être vérifiée. Relance « Revérifier » une fois connecté.", "attention"));
      if (d.claude && d.claude.ok === false) racine.append(banniere(`Pertinence non jugée : ${d.claude.erreur?.message ?? "Claude n'a pas répondu"} Relance « Revérifier » plus tard.`, "attention"));
      if (d.liaison.length) {
        racine.append(h("h3", "vue-titre", `Citations et liste · ${d.liaison.length}`));
        const ul = h("ul", "ref-liaison"); for (const p of d.liaison) ul.append(h("li", undefined, p.detail));
        racine.append(ul);
      }
      if (d.entrees.length) {
        racine.append(h("h3", "vue-titre", `Références · ${d.entrees.length}`));
        const liste = h("div", "ref-liste"); for (const e of d.entrees) liste.append(ligne(e));
        racine.append(liste);
      }
    } else racine.append(h("p", "vue-texte", "Les références de ce rapport n'ont pas encore été vérifiées."));
    if (rf.message) racine.append(h("p", "vue-texte", rf.message));
    const actions = h("div", "vue-actions");
    const b = bouton(d ? "Revérifier" : "Vérifier les références", d ? "" : "primaire", d ? "refresh-cw" : "sparkles", verifier);
    b.disabled = rf.occupe;
    actions.append(b);
    racine.append(actions);

    const volet = h("details", "ref-style"), resume = h("summary");
    resume.append("Style du cours ", h("span", "mu", STYLES_COURT[rf.style] ?? rf.style));
    const champ = h("label", "champ"), sel = h("select", "saisie");
    champ.append(h("span", "etiquette", "Style de bibliographie (tout le cours)"), sel);
    for (const [v, t] of Object.entries(Object.keys(rf.styles).length ? rf.styles : STYLES_COURT)) { const o = h("option", undefined, t); o.value = v; sel.append(o); }
    sel.value = rf.style;
    sel.onchange = () => changerStyle(sel.value);
    volet.append(resume, champ);
    racine.append(volet);
  }

  window.Refs = { charger };
  rendre();
  if (window.Inspecteur.onglet() === "references") charger();
  setTimeout(() => { if (!rf.demande) charger(); }, 1200); // pastille de l'onglet sans l'ouvrir
})();
