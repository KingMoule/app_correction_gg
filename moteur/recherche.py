"""Recherche dans toute la bibliothèque (cours passés compris) : étudiants, rapports, fichiers en attente.

Rapide : ne lit que les listes de classe, le nom des dossiers et, pour les 30 rapports retenus au plus, les petits
fichiers d'état. Jamais le contenu des PDF. Accents et casse ignorés; chaque mot de la recherche doit correspondre
(sous-chaîne du nom ou du prénom, début du DA, nom du lab pour un rapport).
"""

from fastapi import APIRouter, HTTPException, Query

from . import bibliotheque, suivi

router = APIRouter(prefix="/api/recherche")

MIN_CARACTERES = 2
MAX_RESULTATS = 30


def _correspond(mots: list[str], noms: str, da: str, lab: str = "") -> bool:
    return all(m in noms or m in lab or (m.isdigit() and da.startswith(m)) for m in mots)


@router.get("")
def rechercher(q: str = Query("", max_length=100)) -> dict:
    mots = bibliotheque.normaliser(q).split()
    if len("".join(mots)) < MIN_CARACTERES:
        raise HTTPException(422, f"Au moins {MIN_CARACTERES} caractères.")
    etudiants, rapports = [], []
    for f in sorted(bibliotheque.racine().glob("*/*/classe.json")):
        classe = bibliotheque._classe_lisible(f)
        if classe is None or f.parent.parent.name.startswith("_"):
            continue
        cours, groupe = f.parent.parent.name, f.parent.name
        labs = sorted((d.name, bibliotheque.normaliser(d.name)) for d in f.parent.iterdir() if d.is_dir())
        for e in classe["etudiants"]:
            noms = bibliotheque.normaliser(f"{e['prenom']} {e['nom']}")
            da = str(e.get("da") or "")
            deposes = [(lab, norm) for lab, norm in labs if (f.parent / lab / e["id"] / "rapport.pdf").is_file()]
            if _correspond(mots, noms, da):
                etudiants.append({"id": e["id"], "nom": e["nom"], "prenom": e["prenom"], "da": da, "cours": cours,
                                  "groupe": groupe, "nb_rapports": len(deposes), "retire": bool(e.get("retire"))})
            rapports += [{"cours": cours, "groupe": groupe, "lab": lab, "etudiant": e["id"],
                          "nom": e["nom"], "prenom": e["prenom"]}
                         for lab, norm in deposes if _correspond(mots, noms, da, norm)]
    cle = lambda r: (bibliotheque.normaliser(r["nom"]), bibliotheque.normaliser(r["prenom"]), r["cours"], r["groupe"])  # noqa: E731
    etudiants.sort(key=cle)
    rapports.sort(key=lambda r: (*cle(r), r["lab"]))
    for r in rapports[:MAX_RESULTATS]:
        dossier = bibliotheque.chemin_rapport(r["cours"], r["groupe"], r["lab"], r["etudiant"]).parent
        r["etat"] = suivi.etat_du_rapport(dossier, r["cours"], r["groupe"], r["lab"], r["etudiant"])
        r["note"] = bibliotheque.lire_note(dossier)
    attente = [m for m in bibliotheque.lister_attente()
               if _correspond(mots, bibliotheque.normaliser(str(m.get("fichier", ""))), str(m.get("da") or ""))]
    return {"q": q, "etudiants": etudiants[:MAX_RESULTATS], "rapports": rapports[:MAX_RESULTATS],
            "attente": attente[:MAX_RESULTATS],
            "plus": {"etudiants": len(etudiants) > MAX_RESULTATS, "rapports": len(rapports) > MAX_RESULTATS,
                     "attente": len(attente) > MAX_RESULTATS}}
