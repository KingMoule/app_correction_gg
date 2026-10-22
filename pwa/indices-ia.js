// Écran « Indices d'IA » : analyse de style par Claude + bouton Pangram.
// Toujours présenté comme un indice à revérifier, jamais comme un verdict.
(() => {
  if (!document.querySelector("link[href='outils.css']")) {
    const lien = document.createElement("link");
    lien.rel = "stylesheet"; lien.href = "outils.css";
    document.head.append(lien);
  }
  const el = (id) => document.getElementById(id);
  const FORCES = { faible: "Indice faible", moderee: "Indice modéré", marquee: "Indice marqué" };
  let courant = null; // { base, texte }

  const noeud = (tag, contenu, classe) => {
    const n = document.createElement(tag);
    n.textContent = contenu; // jamais de HTML : le texte vient du rapport et de Claude
    if (classe) n.className = classe;
    return n;
  };
  const chemin = (c) => [c.cours, c.groupe, c.lab, c.etudiant.id].map(encodeURIComponent).join("/");

  async function erreur(r) {
    const d = await r.json().catch(() => ({}));
    return d.detail || `Erreur ${r.status}`;
  }

  // Direction Atelier : indice d'IA en violet avec une loupe (jamais rouge, jamais « verdict »); Claude = étincelles.
  const avecIcone = (e, nom, libelle) => e.replaceChildren(UI.icone(nom), document.createTextNode(libelle));
  el("ia-analyser").className = "btn primaire";
  avecIcone(el("ia-analyser"), "sparkles", "Analyser le style avec Claude");
  el("ia-pangram").className = "btn";
  avecIcone(el("ia-pangram"), "clipboard", "Copier le texte et ouvrir Pangram");
  el("ia-avertissement").className = "banniere ia-avert";

  function afficher(d) {
    const zone = el("ia-resultat");
    zone.replaceChildren();
    if (!d) return;
    const force = noeud("span", "", `ia-force ${d.force}`);
    force.append(UI.icone("search"), document.createTextNode(`${FORCES[d.force] ?? FORCES.faible} · à revérifier`));
    zone.append(force);
    zone.append(noeud("p", d.resume));
    for (const s of d.signaux) {
      const b = noeud("div", "", "ia-signal");
      b.append(noeud("div", s.observation), noeud("blockquote", `« ${s.extrait} »`));
      if (!s.verifie) b.append(noeud("div", "Extrait introuvable mot pour mot dans le rapport : à vérifier.", "non-verifie"));
      zone.append(b);
    }
    if (d.contre_indices.length) {
      zone.append(noeud("h3", "Contre-indices"));
      const ul = document.createElement("ul");
      for (const c of d.contre_indices) ul.append(noeud("li", c));
      zone.append(ul);
    }
    el("ia-avertissement").textContent = d.avertissement;
  }

  window.ouvrirIndicesIA = async (cours, groupe, lab, etudiant) => {
    courant = { cours, groupe, lab, etudiant, texte: null };
    el("section-ia").hidden = false;
    el("section-ia").scrollIntoView?.({ behavior: "smooth" });
    el("ia-titre").textContent = `${etudiant.nom}, ${etudiant.prenom} · ${lab}`;
    el("ia-etat").textContent = "";
    afficher(null);
    const ici = courant;
    try {
      const [r, t] = await Promise.all([
        fetch(`/api/indices-ia/resultat/${chemin(ici)}`),
        fetch(`/api/indices-ia/texte/${chemin(ici)}`),
      ]);
      if (courant !== ici) return;
      if (r.ok) afficher(await r.json());
      // Texte chargé d'avance : la copie doit se faire dans le geste du toucher (iPad).
      if (t.ok) ici.texte = (await t.json()).texte;
      else el("ia-etat").textContent = await erreur(t);
    } catch {
      el("ia-etat").textContent = "Moteur injoignable.";
    }
  };

  el("ia-analyser").onclick = async () => {
    if (!courant) return;
    const ici = courant;
    const bouton = el("ia-analyser");
    bouton.disabled = true;
    el("ia-etat").textContent = "Analyse en cours (peut prendre une minute)…";
    try {
      const r = await fetch(`/api/indices-ia/analyser/${chemin(ici)}`, { method: "POST" });
      if (courant !== ici) return;
      if (!r.ok) { el("ia-etat").textContent = await erreur(r); return; }
      afficher(await r.json());
      el("ia-etat").textContent = "";
    } catch {
      el("ia-etat").textContent = "Moteur injoignable.";
    } finally {
      bouton.disabled = false;
    }
  };

  async function copier(texte) {
    try {
      await navigator.clipboard.writeText(texte);
      return true;
    } catch {
      const zone = document.createElement("textarea");
      zone.value = texte;
      document.body.append(zone);
      zone.select();
      const ok = document.execCommand?.("copy");
      zone.remove();
      return !!ok;
    }
  }

  // Aucun envoi automatique : le texte va dans le presse-papiers, Guillaume le colle lui-même.
  el("ia-pangram").onclick = () => {
    if (!courant?.texte) { el("ia-etat").textContent = "Texte du rapport pas encore chargé."; return; }
    const copie = copier(courant.texte); // lancée dans le geste, avant d'ouvrir l'onglet
    window.open("https://www.pangram.com", "_blank", "noopener");
    copie.then((ok) => {
      el("ia-etat").textContent = ok
        ? "Texte copié : colle-le dans Pangram."
        : "Copie refusée par le navigateur.";
    });
  };
})();
