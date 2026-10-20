// Navigation entre les rapports d'un même lab depuis le lecteur : ‹ ›, statut, « Terminé et suivant ».
(async () => {
  if (ref.some((v) => !v)) return;
  const [cours, groupe, lab, etudiant] = ref;
  const API_BIB = "/api/bibliotheque";
  let classe;
  try {
    const arbre = await (await fetch(API_BIB)).json();
    classe = arbre.find((c) => c.cours === cours && c.groupe === groupe);
  } catch { /* moteur injoignable : le lecteur reste utilisable sans navigation */ }
  if (!classe) { $("suivi").hidden = true; return; }

  try { // la bibliothèque s'ouvre déjà dépliée sur ce lab au retour
    for (const cle of [cours, `${cours}/${lab}`, `${cours}/${lab}/${groupe}`]) localStorage.setItem("ouvert:" + cle, "1");
  } catch { /* stockage indisponible */ }

  const liste = classe.etudiants.filter((e) => e.labs.includes(lab));
  const i = liste.findIndex((e) => e.id === etudiant);
  const courant = liste[i];
  let termine = courant?.termines.includes(lab);

  const afficher = () => {
    $("position").textContent = `${i + 1} / ${liste.length}`;
    $("statut").textContent = termine ? "terminé" : "à corriger";
    $("statut").className = "etiquette " + (termine ? "p-fini" : "p-cours");
    $("termine").textContent = termine ? "↩ Ré-ouvrir" : "✔ Terminé";
    $("termine-suivant").hidden = termine;
    $("prec").disabled = i <= 0;
    $("suiv").disabled = i >= liste.length - 1;
  };

  const aller = async (e) => {
    await window.toutEnregistrer();
    const q = new URLSearchParams(location.search);
    q.set("etudiant", e.id);
    q.set("nom", `${e.prenom} ${e.nom}`);
    location.href = `lecteur.html?${q}`;
  };

  const marquer = async (valeur) => {
    await window.toutEnregistrer();
    const corps = { termine: valeur };
    if (valeur) { // note du rapport (vide = pas de note); Annuler = ne rien faire
      const note = prompt("Note du rapport (ex. 17,5), facultatif :", courant?.notes?.[lab] ?? "");
      if (note === null) return false;
      corps.note = note.trim();
    }
    const r = await fetch(`${API_BIB}/statut/${[cours, groupe, lab, etudiant].map(encodeURIComponent).join("/")}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps),
    });
    if (!r.ok) { alert("Impossible d'enregistrer le statut."); return false; }
    termine = valeur;
    courant.termines = valeur ? [lab] : [];
    if (valeur) courant.notes = { ...courant.notes, [lab]: corps.note };
    afficher();
    return true;
  };

  $("prec").onclick = () => aller(liste[i - 1]);
  $("suiv").onclick = () => aller(liste[i + 1]);
  $("termine").onclick = () => marquer(!termine);
  $("termine-suivant").onclick = async () => {
    if (!(await marquer(true))) return;
    // prochain rapport à corriger après celui-ci, puis depuis le début
    const reste = [...liste.slice(i + 1), ...liste.slice(0, i)].find((e) => !e.termines.includes(lab));
    if (reste) aller(reste);
    else { alert("Tous les rapports de ce lab sont terminés."); location.href = "/#biblio"; }
  };
  afficher();
})();
