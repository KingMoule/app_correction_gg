// Navigation entre les rapports d'un lab depuis le lecteur : Précédent, Rapport suivant (prochain non terminé),
// retour au tableau de suivi, « Terminé et suivant ». L'ordre est celui du tableau (groupe puis nom),
// lu en un seul appel : GET /api/suivi/<cours>/<lab>.
(async () => {
  if (ref.some((v) => !v)) return;
  const [cours, groupe, lab, etudiant] = ref;
  const API_BIB = "/api/bibliotheque";
  const filtreGroupe = params.has("fg") ? params.get("fg") : groupe; // « fg » vient du tableau (vide = tous les groupes)
  $("tableau").href = `suivi.html?${new URLSearchParams({ cours, lab })}`;
  let suivi;
  try {
    const r = await fetch(`/api/suivi/${[cours, lab].map(encodeURIComponent).join("/")}?groupe=${encodeURIComponent(filtreGroupe)}`);
    if (r.ok) suivi = await r.json();
  } catch { /* moteur injoignable : le lecteur reste utilisable sans navigation */ }
  const liste = suivi?.rapports ?? [];
  const i = liste.findIndex((e) => e.groupe === groupe && e.etudiant === etudiant);
  if (i < 0) { $("suivi").hidden = true; return; }

  try { // la bibliothèque s'ouvre déjà dépliée sur ce lab au retour
    for (const cle of [cours, `${cours}/${lab}`, `${cours}/${lab}/${groupe}`]) localStorage.setItem("ouvert:" + cle, "1");
  } catch { /* stockage indisponible */ }

  const courant = liste[i];
  let termine = courant.termine;

  // prochain rapport non terminé après celui-ci, puis depuis le début
  const prochain = () => [...liste.slice(i + 1), ...liste.slice(0, i)].find((e) => !e.termine);

  const afficher = () => {
    $("position").textContent = `${i + 1} / ${liste.length}`;
    $("statut").textContent = termine ? "terminé" : "à corriger";
    $("statut").className = "etiquette " + (termine ? "p-fini" : "p-cours");
    $("termine").textContent = termine ? "↩ Ré-ouvrir" : "✔ Terminé";
    $("termine-suivant").hidden = termine;
    $("prec").disabled = i <= 0;
    $("suiv").disabled = !prochain();
    $("suiv").title = prochain() ? "Enregistre, puis ouvre le prochain rapport non terminé du lab"
      : "Aucun autre rapport à corriger";
  };

  const aller = async (e) => {
    if (!(await window.enregistrerAvant())) return;
    const q = new URLSearchParams(location.search);
    q.set("groupe", e.groupe);
    q.set("etudiant", e.etudiant);
    q.set("nom", `${e.prenom} ${e.nom}`);
    q.set("fg", filtreGroupe);
    location.href = `lecteur.html?${q}`;
  };

  const marquer = async (valeur) => {
    if (!(await window.enregistrerAvant())) return false;
    const corps = { termine: valeur };
    if (valeur) { // note du rapport (vide = pas de note); Annuler = ne rien faire
      const note = prompt("Note du rapport (ex. 17,5), facultatif :", courant.note ?? "");
      if (note === null) return false;
      corps.note = note.trim();
    }
    const r = await fetch(`${API_BIB}/statut/${[cours, groupe, lab, etudiant].map(encodeURIComponent).join("/")}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps),
    });
    if (!r.ok) { alert("Impossible d'enregistrer le statut."); return false; }
    termine = courant.termine = valeur;
    if (valeur) courant.note = corps.note;
    afficher();
    return true;
  };

  const vers = (e) => {
    if (e) return aller(e);
    alert("Tous les rapports de ce lab sont terminés.");
    return window.enregistrerAvant().then((ok) => { if (ok) location.href = $("tableau").href; });
  };

  $("prec").onclick = () => aller(liste[i - 1]);
  $("suiv").onclick = () => vers(prochain());
  $("termine").onclick = () => marquer(!termine);
  $("termine-suivant").onclick = async () => { if (await marquer(true)) vers(prochain()); };
  afficher();
})();
