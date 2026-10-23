// Recherche dans toute la bibliothèque (GET /api/recherche?q=) : champ avec résultats groupés Étudiants / Rapports /
// Fichiers à associer, mot recherché surligné, clavier complet (flèches, Entrée, Échap).
//   Recherche.monter(zone, { surEtudiant({ cours, groupe, id }), surRapport?, titreLab? }) -> { focus }
// Le mot surligné passe par le DOM (textContent + <mark>) : jamais de HTML construit à partir des données.
(() => {
  if (!document.querySelector("link[href='recherche.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "recherche.css";
    document.head.append(l);
  }
  const DELAI = 200;
  const MIN = 2;
  const el = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };
  const ETATS = { a_corriger: ["Reçu", "p-neutre"], en_cours: ["En cours", "p-nouv"], termine: ["Terminé", "p-fini"] };
  const RAISONS = { ambigu: "plusieurs étudiants possibles", aucune_correspondance: "aucun nom reconnu",
    deja_importe: "déjà importé pour ce lab", da_inconnu: "DA absent des listes" };

  // Lettre par lettre sans accents ni casse, avec la position d'origine de chaque lettre gardée.
  function simplifier(texte) {
    let s = "";
    const pos = [];
    [...texte].forEach((c, i) => {
      const n = c.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase();
      for (const x of n) { s += x; pos.push(i); }
    });
    return { s, pos, lettres: [...texte] };
  }

  // Le texte avec les mots de la recherche entourés de <mark> (accents et casse ignorés).
  function surligner(texte, mots) {
    const { s, pos, lettres } = simplifier(texte);
    const marque = new Array(lettres.length).fill(false);
    for (const m of mots) {
      for (let i = s.indexOf(m); i !== -1; i = s.indexOf(m, i + 1)) for (let k = i; k < i + m.length; k++) marque[pos[k]] = true;
    }
    const f = document.createDocumentFragment();
    let debut = 0;
    while (debut < lettres.length) {
      let fin = debut;
      while (fin < lettres.length && marque[fin] === marque[debut]) fin++;
      const bout = lettres.slice(debut, fin).join("");
      if (marque[debut]) f.append(el("mark", "", bout)); else f.append(bout);
      debut = fin;
    }
    return f;
  }

  const motsDe = (q) => q.normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase().match(/[a-z0-9]+/g) ?? [];
  const initiales = (prenom, nom) => `${prenom[0] ?? ""}${nom[0] ?? ""}`.toUpperCase();

  function monter(zone, { surEtudiant, surRapport, titreLab = (l) => l } = {}) {
    zone.replaceChildren();
    const boite = el("div", "recherche");
    const champ = el("input", "saisie");
    champ.type = "text"; champ.inputMode = "search"; champ.enterKeyHint = "search"; champ.id = "recherche-champ"; champ.autocomplete = "off"; champ.spellcheck = false;
    champ.placeholder = "Étudiant, DA ou lab"; champ.maxLength = 100;
    champ.setAttribute("role", "combobox");
    champ.setAttribute("aria-label", "Rechercher un étudiant, un rapport ou un fichier à associer");
    champ.setAttribute("aria-autocomplete", "list");
    champ.setAttribute("aria-controls", "recherche-liste");
    champ.setAttribute("aria-expanded", "false");
    const raccourci = el("kbd", "", "Ctrl K");
    raccourci.setAttribute("aria-hidden", "true");
    const effacer = el("button", "btn-ico res-effacer"); effacer.type = "button";
    effacer.setAttribute("aria-label", "Effacer la recherche"); effacer.append(UI.icone("x"));
    const panneau = el("div", "resultats");
    panneau.hidden = true;
    const entete = el("p", "res-statut");
    entete.setAttribute("role", "status");
    const liste = el("div", "res-liste");
    liste.id = "recherche-liste"; liste.setAttribute("role", "listbox"); liste.setAttribute("aria-label", "Résultats de la recherche");
    panneau.append(entete, liste);
    boite.append(UI.icone("search"), champ, raccourci, effacer, panneau);
    zone.append(boite);

    let minuteur = null, requete = null, actif = -1;
    const options = () => [...liste.querySelectorAll("[role=option]")];

    function fermer() {
      panneau.hidden = true;
      champ.setAttribute("aria-expanded", "false");
      champ.removeAttribute("aria-activedescendant");
      actif = -1;
    }
    function ouvrirPanneau() {
      panneau.hidden = false;
      champ.setAttribute("aria-expanded", "true");
    }
    function activer(i) {
      const os = options();
      if (!os.length) { actif = -1; champ.removeAttribute("aria-activedescendant"); return; }
      actif = ((i % os.length) + os.length) % os.length;
      os.forEach((o, k) => { o.classList.toggle("sel", k === actif); o.setAttribute("aria-selected", String(k === actif)); });
      champ.setAttribute("aria-activedescendant", os[actif].id);
      os[actif].scrollIntoView?.({ block: "nearest" });
    }

    let numero = 0;
    function option(balise, { icone, avatar, corps, droite, href, surClic }) {
      const o = el(balise, "res");
      o.id = `res-${numero++}`;
      o.setAttribute("role", "option"); o.setAttribute("aria-selected", "false");
      if (href) o.href = href; else o.tabIndex = -1;
      const tete = avatar ? el("span", "avatar", avatar) : (() => { const t = el("span", "tuile-res"); t.append(UI.icone(icone, "s")); return t; })();
      o.append(tete, corps);
      if (droite) o.append(...droite);
      o.addEventListener("click", (ev) => { fermer(); if (surClic) { ev.preventDefault(); surClic(); } });
      o.addEventListener("pointermove", () => { const k = options().indexOf(o); if (k !== actif) activer(k); });
      return o;
    }
    function groupe(titre, items, plus) {
      if (!items.length) return;
      const g = el("div", "res-groupe");
      g.setAttribute("role", "group"); g.setAttribute("aria-label", titre);
      const t = el("p", "res-titre", titre); t.setAttribute("aria-hidden", "true");
      g.append(t, ...items);
      if (plus) g.append(el("p", "res-plus", "Plus de 30 résultats : précise la recherche."));
      liste.append(g);
    }

    function rendre(d, mots) {
      numero = 0;
      liste.replaceChildren();
      const nom = (prenom, famille) => { const b = el("b"); b.append(surligner(`${prenom} ${famille}`, mots)); return b; };
      groupe("Étudiants", d.etudiants.map((e) => {
        const corps = el("span", "corps");
        const da = el("span", "mu"); da.append(" · DA ", surligner(e.da, mots), ` · ${UI.titreCours(e.cours)} gr. ${e.groupe}`);
        corps.append(nom(e.prenom, e.nom), da);
        const droite = [];
        if (e.retire) droite.push(el("span", "pastille p-neutre", "Retiré"));
        droite.push(el("span", "mu fin", e.nb_rapports ? `${e.nb_rapports} rapport${e.nb_rapports > 1 ? "s" : ""}` : "aucun rapport"));
        return option("div", { avatar: initiales(e.prenom, e.nom), corps, droite, surClic: () => surEtudiant?.({ cours: e.cours, groupe: e.groupe, id: e.id }) });
      }), d.plus.etudiants);
      groupe("Rapports", d.rapports.map((r) => {
        const corps = el("span", "corps");
        const lieu = el("span", "mu"); lieu.append(" · ", surligner(titreLab(r.lab), mots), ` · ${UI.titreCours(r.cours)} · gr. ${r.groupe}`);
        corps.append(nom(r.prenom, r.nom), lieu);
        const [libelle, classe] = ETATS[r.etat] ?? ["", "p-neutre"];
        const pastille = el("span", `pastille ${classe}`, r.note ? `${libelle} · ${r.note}` : libelle);
        const url = `lecteur.html?${new URLSearchParams({ cours: r.cours, groupe: r.groupe, lab: r.lab, etudiant: r.etudiant, nom: `${r.prenom} ${r.nom}` })}`;
        return option("a", { avatar: initiales(r.prenom, r.nom), corps, droite: [pastille], href: url, surClic: surRapport ? () => surRapport(r) : null });
      }), d.plus.rapports);
      groupe("Fichiers à associer", d.attente.map((a) => {
        const corps = el("span", "corps");
        const nomFichier = el("b"); nomFichier.append(surligner(a.fichier, mots));
        corps.append(nomFichier, el("span", "mu", ` · ${RAISONS[a.raison] ?? a.raison} · ${UI.titreCours(a.cours)} · ${titreLab(a.lab)}`));
        return option("a", { icone: "upload", corps, droite: [el("span", "mu fin", "Importer")], href: "#importer" });
      }), d.plus.attente);
      const n = d.etudiants.length + d.rapports.length + d.attente.length;
      const plus = d.plus.etudiants || d.plus.rapports || d.plus.attente;
      entete.textContent = n
        ? `${n}${plus ? " et plus" : ""} résultat${n > 1 ? "s" : ""} pour « ${d.q.trim()} »`
        : `Aucun résultat pour « ${d.q.trim()} ». Essaie un autre nom, un n° de DA ou un lab.`;
      entete.classList.toggle("vide", !n);
      ouvrirPanneau();
      activer(n ? 0 : -1);
    }

    async function chercher() {
      const q = champ.value.trim();
      requete?.abort();
      if (motsDe(q).join("").length < MIN) {
        liste.replaceChildren(); entete.textContent = ""; liste.removeAttribute("aria-busy");
        if (q) { entete.textContent = "Écris au moins 2 caractères."; entete.classList.add("vide"); ouvrirPanneau(); } else fermer();
        return;
      }
      const c = requete = new AbortController();
      liste.setAttribute("aria-busy", "true");
      try {
        const r = await fetch(`/api/recherche?q=${encodeURIComponent(q)}`, { signal: c.signal });
        if (!r.ok) throw new Error(String(r.status));
        const d = await r.json();
        if (c !== requete) return;
        liste.removeAttribute("aria-busy");
        rendre(d, motsDe(q));
      } catch (e) {
        if (e.name === "AbortError") return;
        liste.removeAttribute("aria-busy");
        liste.replaceChildren();
        entete.textContent = "La recherche n'a pas répondu : le moteur est-il allumé ?";
        entete.classList.add("vide");
        ouvrirPanneau();
      }
    }

    const vider = () => { champ.value = ""; liste.replaceChildren(); entete.textContent = ""; requete?.abort(); fermer(); };
    effacer.onclick = () => { vider(); champ.focus(); };
    champ.addEventListener("input", () => { clearTimeout(minuteur); minuteur = setTimeout(chercher, DELAI); });
    champ.addEventListener("focus", () => { if (liste.children.length || entete.textContent) ouvrirPanneau(); });
    champ.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        if (panneau.hidden) { if (liste.children.length) ouvrirPanneau(); else return; }
        ev.preventDefault();
        activer(actif + (ev.key === "ArrowDown" ? 1 : -1));
      } else if (ev.key === "Enter") {
        clearTimeout(minuteur);
        const o = options()[actif];
        if (o && !panneau.hidden) { ev.preventDefault(); o.click(); } else if (champ.value.trim()) { ev.preventDefault(); chercher(); }
      } else if (ev.key === "Escape") {
        if (!panneau.hidden) { ev.preventDefault(); fermer(); } else if (champ.value) { ev.preventDefault(); vider(); } else champ.blur();
      }
    });
    document.addEventListener("pointerdown", (ev) => { if (!boite.contains(ev.target)) fermer(); });
    boite.addEventListener("focusout", (ev) => { if (ev.relatedTarget && !boite.contains(ev.relatedTarget)) fermer(); });

    return { focus() { champ.focus(); champ.select(); } };
  }

  window.Recherche = { monter };
})();
