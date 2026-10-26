// Double remise d'une équipe : les deux coéquipiers ont chacun remis le rapport. Boîte de dialogue qui montre les deux
// copies côte à côte (déposant, date de remise, pages, aperçu de la première page, travail déjà fait) et laisse
// Guillaume choisir : garder l'une, l'autre ou les deux. Aucune présélection; rien n'est supprimé (mis de côté).
//   DoubleRemise.ouvrir({ rangees: { cours, lab, a: { groupe, id }, b: { groupe, id } } | attente: "<id>", apres })
//   DoubleRemise.nommage(copies, nommage) : phrase « A a nommé B comme coéquipier ».
// textContent seulement : aucun HTML venu des données.
(() => {
  if (!document.querySelector("link[href='double-remise.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "double-remise.css";
    document.head.append(l);
  }
  const API = "/api/bibliotheque";
  const enc = encodeURIComponent;
  const el = (tag, classe, texte) => {
    const n = document.createElement(tag);
    if (classe) n.className = classe;
    if (texte != null) n.textContent = texte;
    return n;
  };
  const nom = (c) => `${c.prenom} ${c.nom}`;
  const detail = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;
  const pluriel = (n, un, plusieurs) => `${n} ${n > 1 ? plusieurs : un}`;

  function dateFr(iso) {
    if (!iso) return null;
    const d = new Date(iso); // sans fuseau : lue comme heure locale, celle du nom du fichier LÉA
    return Number.isNaN(d.getTime()) ? null : d.toLocaleString("fr-CA", { dateStyle: "long", timeStyle: "short" });
  }

  function nommage(copies, quoi) {
    const [a, b] = copies;
    if (quoi === "mutuel") return `${nom(a)} et ${nom(b)} se nomment l'une l'autre comme coéquipier.`;
    const [qui, lui] = ["b_nomme_a", "nouveau_nomme"].includes(quoi) ? [b, a] : [a, b]; // l'autre est celui qui est nommé
    return `${nom(qui)} a nommé ${nom(lui)} comme coéquipier sur la page titre.`;
  }

  // Ce que la copie a déjà, en phrases courtes. `vide` : rien (copie qui vient d'arriver).
  function travail(t) {
    if (t.vide) return ["Aucun travail encore : ni annotation, ni analyse, ni note."];
    const l = [];
    if (t.traits) l.push(`${pluriel(t.traits, "trait", "traits")} au crayon`);
    if (t.francais) l.push(`Français analysé : ${pluriel(t.francais.fautes, "faute", "fautes")}, ${pluriel(t.francais.acceptees, "acceptée", "acceptées")}`);
    if (t.ia) l.push(`Indice d'IA : ${t.ia}`);
    if (t.references) l.push("Références vérifiées");
    if (t.comparaison) l.push("Comparaison de style faite");
    l.push(t.termine ? "Marquée terminée" : "Pas terminée");
    if (t.note) l.push(`Note : ${t.note}`);
    return l;
  }

  async function apercu(zone, url) {
    try {
      if (!window.pdfjsLib) {
        await new Promise((ok, ko) => {
          const s = document.createElement("script");
          s.src = "vendor/pdf.min.js"; s.onload = ok; s.onerror = ko;
          document.head.append(s);
        });
      }
      pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
      const r = await fetch(url);
      if (!r.ok) throw new Error(String(r.status));
      const doc = await pdfjsLib.getDocument({ data: await r.arrayBuffer() }).promise;
      const page = await doc.getPage(1);
      const base = page.getViewport({ scale: 1 });
      const largeur = Math.max(160, zone.clientWidth || 280);
      const echelle = (largeur / base.width) * Math.min(window.devicePixelRatio || 1, 2);
      const vue = page.getViewport({ scale: echelle });
      const toile = el("canvas");
      toile.width = Math.floor(vue.width); toile.height = Math.floor(vue.height);
      toile.setAttribute("role", "img");
      await page.render({ canvasContext: toile.getContext("2d"), viewport: vue }).promise;
      zone.replaceChildren(toile);
    } catch {
      zone.replaceChildren(el("p", "aide", "Aperçu indisponible."));
    }
  }

  async function ouvrir({ rangees, attente, apres }) {
    const url = attente ? `${API}/attente/${enc(attente)}/double`
      : `${API}/double/${[rangees.cours, rangees.lab, rangees.a.groupe, rangees.a.id, rangees.b.groupe, rangees.b.id].map(enc).join("/")}`;
    const r = await fetch(url);
    if (!r.ok) { UI.toast(await detail(r), { erreur: true }); await apres?.(); return; }
    const d = await r.json();
    const [c0, c1] = d.copies;

    const dlg = el("dialog", "dialogue double");
    dlg.setAttribute("aria-labelledby", "double-titre");
    const forme = el("div", "double-corps");
    const titre = el("h2", "", `Double remise : ${nom(c0)} et ${nom(c1)}`);
    titre.id = "double-titre"; titre.tabIndex = -1;
    forme.append(titre,
      el("p", "", `Les deux ont remis un rapport pour ce lab. ${nommage(d.copies, d.nommage)} Choisis la copie à garder : `
        + "l'autre est mise de côté (récupérable), jamais supprimée."));

    const grille = el("div", "double-copies");
    const choix = el("div", "double-actions");
    const fermer = () => dlg.close();

    const appliquer = async (corps, message) => {
      const rep = await fetch(attente ? `${API}/attente/${enc(attente)}/double`
        : `${API}/double/${enc(d.cours)}/${enc(d.lab)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
      if (!rep.ok) { UI.toast(await detail(rep), { erreur: true }); return; }
      fermer();
      UI.toast(message);
      await apres?.();
    };
    const corpsRangees = (garde) => ({ a: rangees.a, b: rangees.b, choix: garde, confirmer: true });

    // « Garder la copie de X » : confirmation qui dit ce qui sera mis de côté et ce qui reste rattaché.
    const garder = async (gardee, ecartee, corps) => {
      const t = ecartee.travail;
      const ce = ecartee.source === "attente"
        ? `Le fichier de ${nom(ecartee)} (${ecartee.fichier || "sans nom"}) sera mis de côté dans le dossier _ecartes.`
        : `La copie de ${nom(ecartee)} sera mise de côté avec tout son dossier dans le dossier _remplaces`
          + (t.vide ? "." : ` : ${travail(t).join(", ").toLowerCase()}.`);
      const ok = await Dialogue.confirmer({
        titre: `Garder la copie de ${nom(gardee)} ?`,
        texte: `${ce}\n\nElle reste récupérable (rien n'est supprimé). ${nom(ecartee)} reste rattaché(e) comme coéquipier(ère) : `
          + "pas de « non remis », et l'export pour LÉA garde une ligne pour chacun.",
        ok: `Garder la copie de ${nom(gardee)}` });
      if (ok) await appliquer(corps, `Copie de ${nom(gardee)} gardée`);
    };

    d.copies.forEach((c, i) => {
      const autre = d.copies[1 - i];
      const carte = el("section", "double-copie");
      carte.setAttribute("aria-label", `Copie de ${nom(c)}`);
      const tete = el("h3", "", nom(c));
      tete.append(el("span", "pastille", c.source === "attente" ? "Nouvelle copie" : "Déjà rangée"));
      const faits = el("dl", "double-faits");
      const fait = (k, v) => { faits.append(el("dt", "", k), el("dd", "", v)); };
      fait("Remis le", dateFr(c.remis_le) || "date inconnue (absente du nom du fichier)");
      fait("Fichier", c.fichier || "nom d'origine inconnu");
      fait("Pages", c.pages == null ? "illisible" : String(c.pages));
      const vue = el("div", "double-apercu");
      vue.append(el("p", "aide", "Aperçu…"));
      const liste = el("ul", "double-travail");
      for (const ligne of travail(c.travail)) liste.append(el("li", "", ligne));
      const bouton = el("button", "btn primaire", `Garder la copie de ${nom(c)}`);
      bouton.type = "button";
      bouton.onclick = () => garder(c, autre, attente
        ? { choix: i === 0 ? "existante" : "nouvelle", confirmer: true } : corpsRangees(i === 0 ? "a" : "b"));
      carte.append(tete, faits, vue, el("h4", "", "Travail déjà fait"), liste, bouton);
      grille.append(carte);
      apercu(vue, c.pdf);
    });

    const deux = el("button", "btn", "Garder les deux (deux rapports distincts)");
    deux.type = "button";
    deux.onclick = async () => {
      const ok = await Dialogue.confirmer({
        titre: "Garder les deux copies ?",
        texte: `${nom(c0)} et ${nom(c1)} auront chacun leur rapport, corrigé séparément. Le lien d'équipe entre eux sera retiré `
          + "pour ce lab. Rien n'est mis de côté.", ok: "Garder les deux" });
      if (ok) await appliquer(attente ? { choix: "les_deux" } : corpsRangees("les_deux"), "Les deux copies gardées");
    };
    const plusTard = el("button", "btn tertiaire", "Décider plus tard");
    plusTard.type = "button";
    plusTard.onclick = fermer;
    choix.append(plusTard, deux);

    forme.append(grille, choix);
    dlg.append(forme);
    dlg.addEventListener("close", () => dlg.remove());
    document.body.append(dlg);
    dlg.showModal();
    titre.focus(); // aucun bouton de choix n'a le focus : pas de présélection
  }

  window.DoubleRemise = { ouvrir, nommage };
})();
