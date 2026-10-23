// Page « Consommation » : jauges 5 h et semaine, rapports restants, historique, répartition, calibrage et marge.
// Tout vient de GET /api/consommation (moteur/consommation.py); aucun HTML construit à partir de données.
(() => {
  const el = (id) => document.getElementById(id);
  const sur = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };
  const nombre = (v) => String(Math.round(v));
  const usd = (v) => `${v.toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;
  const pctf = (v) => `${v.toLocaleString("fr-CA", { maximumFractionDigits: 1 })} %`;
  const age = (min) => (min < 60 ? `${min} min` : min < 1440 ? `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")}` : `${Math.floor(min / 1440)} j`);
  const COULEURS = { francais: "var(--accent)", ia: "var(--ia)", references: "var(--claude)", plagiat: "var(--plagiat)" };

  const jauge = (valeur, repere, niveau) => {
    const j = sur("div", `jauge ${niveau || ""}`);
    const barre = sur("i"); barre.style.width = `${Math.min(100, valeur)}%`;
    j.append(barre);
    if (repere != null) { const u = sur("u"); u.style.left = `${repere}%`; j.append(u); }
    return j;
  };

  const carteJauge = (titre, pct, cout, appels, { plafond, note, niveau, aide }) => {
    const c = sur("section", "co-bloc");
    c.append(sur("h2", "", titre));
    const gros = sur("div", "co-gros");
    if (pct == null) { gros.textContent = "—"; } else { gros.append(`≈ ${nombre(pct)} `, sur("small", "", "%")); }
    c.append(gros, jauge(pct ?? 0, plafond, niveau));
    const l = sur("div", "co-legende");
    l.append(sur("span", "", "0"), sur("span", "", plafond != null ? `repère : arrêt à ${nombre(plafond)} %` : ""), sur("span", "", "100"));
    c.append(l, sur("p", "co-sous", note), sur("p", "co-sous", `Mesuré : ${usd(cout)} (équivalent API, non facturé) · ${appels} appel(s). ${aide || ""}`.trim()));
    return c;
  };

  // Fenêtre (session ou semaine) : total saisi + app depuis, dont l'app / autres usages, reste. Sans saisie récente : l'app seulement.
  const carteTotal = (titre, t, app, appels, cout, { plafond, niveau, fenetre, ratioConnu }) => {
    const ok = t.etat === "ok";
    const c = sur("section", "co-bloc");
    c.append(sur("h2", "", ok ? `${titre} · total estimé` : `${titre} · l'app seulement`));
    const gros = sur("div", "co-gros");
    const valeur = ok ? t.total : app;
    if (valeur == null) { gros.textContent = "—"; } else { gros.append(`≈ ${nombre(valeur)} `, sur("small", "", "%")); }
    c.append(gros);
    const j = jauge(ok ? t.total : app ?? 0, ok ? plafond : plafond, niveau);
    if (ok && app != null) {
      // l'app en couleur pleine, les autres usages en gris à sa suite
      j.firstChild.style.width = `${Math.min(100, app)}%`;
      const autres = sur("i", "autres"); autres.style.left = `${Math.min(100, app)}%`; autres.style.width = `${Math.min(100 - Math.min(100, app), t.autres)}%`;
      j.insertBefore(autres, j.firstChild.nextSibling);
    }
    c.append(j);
    const l = sur("div", "co-legende");
    l.append(sur("span", "", "0"), sur("span", "", plafond != null ? `repère : arrêt à ${nombre(plafond)} %` : ""), sur("span", "", "100"));
    c.append(l);
    if (ok) {
      const rep = sur("p", "co-sous");
      rep.append(sur("b", "", `Reste ≈ ${nombre(t.reste)} %`), app != null ? ` · dont l'app ≈ ${nombre(app)} %, autres usages ≈ ${nombre(t.autres)} %` : "");
      c.append(rep, sur("p", "co-sous", `Saisi il y a ${age(t.age_min)} (${nombre(t.saisi)} %)${t.depuis_app ? `, plus l'app depuis ≈ ${pctf(t.depuis_app)}` : ""}. Les autres usages depuis la saisie ne sont pas comptés : ressaisis /usage pour rafraîchir.`));
    } else if (t.etat === "perimee") {
      c.append(sur("p", "co-sous co-alerte", `Dernière saisie il y a ${age(t.age_min)} : trop ancienne pour la fenêtre de ${fenetre}, elle n'est plus fiable. Ressaisis /usage.`));
    } else {
      c.append(sur("p", "co-sous", `Chiffre de l'app seulement (français, IA, références, plagiat) : la limite est partagée avec tes autres usages de Claude. Saisis /usage pour voir le total.`));
    }
    c.append(sur("p", "co-sous", `Mesuré pour l'app : ${usd(cout)} (équivalent API, non facturé) · ${appels} appel(s).${ratioConnu ? "" : " Pas encore calibré : mesure moyenne (≈ 3 % par rapport)."}`));
    return c;
  };

  function afficher(r) {
    // Limite atteinte
    const lim = el("co-limite");
    lim.hidden = !r.limite;
    lim.className = r.limite ? "banniere erreur" : "";
    lim.replaceChildren();
    if (r.limite) {
      lim.append(UI.icone("triangle-alert"), sur("div", "corps",
        r.limite.reprise_connue ? `Limite d'usage atteinte. Reprise vers ${r.limite.reprise.slice(11, 16)} (d'après le message de Claude).`
          : `Limite d'usage atteinte. Le message de Claude ne donne pas l'heure : reprise estimée vers ${r.limite.reprise.slice(11, 16)} (5 h plus tard).`));
    }

    const niveauS = r.limite || r.session.pct >= r.plafond_pct ? "danger" : r.session.pct >= r.plafond_pct - 15 ? "attention" : "";
    const calib = r.calibrage;
    const ts = r.total.session, tw = r.total.semaine;
    const niveauT = r.limite || (ts.etat === "ok" ? ts.total : r.session.pct) >= r.plafond_pct ? "danger"
      : (ts.etat === "ok" ? ts.total : r.session.pct) >= r.plafond_pct - 15 ? "attention" : "";
    el("co-jauges").replaceChildren(
      carteTotal("Session · 5 dernières heures", ts, r.session.pct, r.session.appels, r.session.cout,
        { plafond: r.plafond_pct, niveau: r.limite ? "danger" : niveauT || niveauS, fenetre: "5 h", ratioConnu: calib.calibre }),
      carteTotal("Semaine · 7 derniers jours", tw, r.semaine.pct, r.semaine.appels, r.semaine.cout,
        { plafond: null, niveau: "", fenetre: "7 jours", ratioConnu: calib.semaine_calibree }),
    );

    // Rapports restants
    const reste = el("co-restants");
    reste.replaceChildren();
    const b1 = sur("b", "", `≈ ${r.restants} rapport(s)`), b2 = sur("b", "", `${r.lot_conseille} rapport(s)`);
    reste.append(b1, ` encore possibles avant la marge de ${nombre(r.marge_pct)} %${ts.etat === "ok" ? " (d'après le total estimé)" : " (l'app seulement)"} · lot conseillé : `, b2,
      ` (≈ ${pctf(r.pct_par_rapport)} par rapport avec français, IA et références).`);

    // Par jour
    const max = Math.max(...r.par_jour.map((j) => j.pct), 1);
    el("co-jours").replaceChildren(...r.par_jour.map((j, i) => {
      const d = sur("div", i === r.par_jour.length - 1 ? "auj" : "");
      const barre = sur("i"); barre.style.height = `${Math.max(1, (j.pct / max) * 85)}%`;
      const jour = i === r.par_jour.length - 1 ? "auj." : new Date(`${j.date}T12:00`).toLocaleDateString("fr-CA", { weekday: "short" });
      d.title = `${j.date} : ${usd(j.cout)}`;
      d.append(sur("span", "", nombre(j.pct)), barre, sur("span", "", jour));
      return d;
    }));

    // Par type
    el("co-repart").replaceChildren(...r.par_type.filter((t) => t.part > 0).map((t) => {
      const i = sur("i"); i.style.width = `${t.part * 100}%`; i.style.background = COULEURS[t.type]; i.title = t.libelle; return i;
    }));
    el("co-types").replaceChildren(...r.par_type.map((t) => {
      const tr = sur("tr"); tr.style.setProperty("--c", COULEURS[t.type]);
      const unite = t.type === "plagiat" ? "paire" : "rapport";
      tr.append(sur("td", "", t.libelle), sur("td", "", `${pctf(t.pct_moyen)} / ${unite}${t.mesure ? "" : " (défaut)"}`),
        sur("td", "", `${nombre(t.part * 100)} %`));
      return tr;
    }));

    // Calibrage
    const c = el("co-cal-etat");
    const d = calib.derniere;
    c.replaceChildren();
    const s = ts.etat !== "aucune" ? ts : null;
    el("co-saisie-etat").textContent = !s ? "Aucune saisie pour l'instant."
      : `Dernière saisie : ${nombre(s.saisi)} % il y a ${age(s.age_min)}${s.etat === "perimee" ? " (trop ancienne, plus fiable)" : ""}.`;
    if (!d) c.append("Jamais calibré : l'estimation utilise la mesure moyenne de PLAN.md (≈ 3 % de la session par rapport avec Sonnet).");
    else c.append("Dernier calibrage : ", sur("b", "", new Date(d.date).toLocaleString("fr-CA", { dateStyle: "medium", timeStyle: "short" })),
      ` (session ${nombre(d.session)} %${d.semaine != null ? `, semaine ${nombre(d.semaine)} %` : ""}). Écart avec l'estimation d'alors : ${d.ecart > 0 ? "+" : ""}${d.ecart} point(s). Rapport actuel : ${calib.pct_par_usd} % de la session par dollar${calib.calibre ? "" : " (par défaut : trop peu d'appels pour caler)"}.`);
    if (document.activeElement !== el("co-marge")) el("co-marge").value = r.marge_pct;
  }

  async function charger() {
    try {
      const rep = await fetch("/api/consommation");
      if (!rep.ok) throw new Error();
      afficher(await rep.json());
    } catch { UI.toast("Moteur injoignable.", { erreur: true }); }
  }

  const nombreSaisi = (champ) => {
    const t = champ.value.trim().replace(",", ".");
    return t === "" ? null : Number(t);
  };
  async function envoyer(url, corps, message) {
    const rep = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
    if (!rep.ok) { UI.toast("Valeur refusée : un pourcentage entre 0 et 100 est attendu.", { erreur: true }); return; }
    afficher(await rep.json());
    UI.toast(message);
    window.Coque?.majConso();
  }
  el("co-cal-form").onsubmit = (e) => {
    e.preventDefault();
    const s = nombreSaisi(el("co-cal-session")), w = nombreSaisi(el("co-cal-semaine"));
    if (s == null || Number.isNaN(s) || Number.isNaN(w)) { UI.toast("Saisis au moins le pourcentage de la session.", { erreur: true }); return; }
    const calibrer = el("co-cal-aussi").checked;
    envoyer("/api/consommation/total", { session: s, semaine: w, calibrer }, calibrer ? "Usage total enregistré et calibrage mis à jour." : "Usage total enregistré.");
    el("co-cal-session").value = el("co-cal-semaine").value = "";
    el("co-cal-aussi").checked = false;
  };
  el("co-marge-form").onsubmit = (e) => {
    e.preventDefault();
    const m = nombreSaisi(el("co-marge"));
    if (m == null || Number.isNaN(m)) { UI.toast("Saisis un pourcentage.", { erreur: true }); return; }
    envoyer("/api/consommation/reglages", { marge_pct: m }, "Marge enregistrée.");
  };

  charger();
  setInterval(() => { if (!document.hidden) charger(); }, 30000);
})();
