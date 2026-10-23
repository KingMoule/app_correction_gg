"""Fiche d'un étudiant : ses rapports (un par lab), l'équipe, l'historique (remplacés, fichiers écartés).

Ne lit que les listes de classe, les noms de dossiers et les petits JSON d'état (jamais les PDF). L'adresse ne porte
que cours, groupe et id : le nom et le DA sont lus dans la liste de classe.
"""

import re
from datetime import datetime

from fastapi import APIRouter, HTTPException

from . import bibliotheque, stockage, suivi

router = APIRouter(prefix="/api/etudiant")

HORODATAGE = re.compile(r"_(\d{8}-\d{6})(?:-\d+)?$")


def _date(horodatage: str) -> str:
    return datetime.strptime(horodatage, "%Y%m%d-%H%M%S").isoformat()


def _remplaces(cours: str, groupe: str, etudiant: str) -> list[dict]:
    """Anciens dossiers de cet étudiant dans `_remplaces/` : `<cours>_<groupe>_<lab>_<étudiant>_<horodatage>`."""
    sortie = []
    for d in sorted((bibliotheque.racine() / "_remplaces").glob(f"{cours}_{groupe}_*")):
        m = HORODATAGE.search(d.name)
        if not d.is_dir() or not m:
            continue
        milieu = d.name[len(cours) + len(groupe) + 2:m.start()]
        if milieu.endswith(f"_{etudiant}") and len(milieu) > len(etudiant) + 1:
            sortie.append({"lab": milieu[:-len(etudiant) - 1], "date": _date(m.group(1))})
    return sorted(sortie, key=lambda x: x["date"])


def _ecartes(cours: str, groupe: str, etudiant: str, da: str) -> list[dict]:
    """Fichiers écartés qui lui correspondent (même DA, ou parmi les candidats de l'association)."""
    sortie = []
    for f in sorted((bibliotheque.racine() / "_ecartes").glob("*.json")):
        meta = stockage.lire_json(f)
        if not isinstance(meta, dict) or meta.get("cours") != cours:
            continue
        candidats = meta.get("candidats") if isinstance(meta.get("candidats"), list) else []
        lui = any(isinstance(c, dict) and c.get("id") == etudiant and c.get("groupe") == groupe for c in candidats)
        if lui or (da and str(meta.get("da") or "") == da):
            sortie.append({"fichier": str(meta.get("fichier") or ""), "lab": str(meta.get("lab") or ""),
                           "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")})
    return sortie


@router.get("/{cours}/{groupe}/{etudiant}")
def fiche(cours: str, groupe: str, etudiant: str) -> dict:
    for valeur, nom in ((cours, "cours"), (groupe, "groupe"), (etudiant, "étudiant")):
        bibliotheque.segment_sur(valeur, nom)
    lui = next((e for e in bibliotheque.etudiants_du_cours(cours, groupe) if e["id"] == etudiant), None)
    if lui is None:
        raise HTTPException(404, "Étudiant introuvable.")
    da = str(lui.get("da") or "")
    classes = bibliotheque.classes_du_cours(cours)
    dossiers = {}  # lab -> dossier de son rapport (ou de celui du coéquipier qui le couvre)
    for c in classes:
        for e in c["etudiants"]:
            for pdf in sorted((bibliotheque.dossier_groupe(cours, c["groupe"])).glob(f"*/{e['id']}/rapport.pdf")):
                lab, dossier = pdf.parent.parent.name, pdf.parent
                if (c["groupe"], e["id"]) == (groupe, etudiant):
                    dossiers[lab] = {"dossier": dossier, "par": None}
                    continue
                membres = stockage.lire_json(dossier / "equipe.json", [])
                if isinstance(membres, list) and any(isinstance(m, dict) and (m.get("groupe"), m.get("id")) == (groupe, etudiant)
                                                     for m in membres):
                    dossiers.setdefault(lab, {"dossier": dossier, "par": {"id": e["id"], "groupe": c["groupe"],
                                                                         "nom": e["nom"], "prenom": e["prenom"]}})
    rapports = []
    for lab, x in sorted(dossiers.items()):
        dossier, par = x["dossier"], x["par"]
        depose = (par["groupe"], par["id"]) if par else (groupe, etudiant)
        membres = stockage.lire_json(dossier / "equipe.json", [])
        equipe = [{k: m.get(k) for k in ("id", "groupe", "nom", "prenom")} for m in membres if isinstance(m, dict)] \
            if isinstance(membres, list) else []
        if par:  # couvert par le rapport d'un coéquipier : l'équipe se lit depuis son rapport
            equipe = [m for m in equipe if (m["groupe"], m["id"]) != (groupe, etudiant)] + [par]
        rapports.append({"lab": lab, "groupe": depose[0], "etudiant": depose[1], "par_equipe": par is not None,
                         "etat": suivi.etat_du_rapport(dossier, cours, depose[0], lab, depose[1]),
                         "note": bibliotheque.lire_note(dossier), "equipe": equipe,
                         "archive": bibliotheque._lire_drapeau(dossier.parent / "archive.json", "archive")})
    return {"cours": cours, "groupe": groupe, "id": etudiant, "nom": lui["nom"], "prenom": lui["prenom"], "da": da,
            "retire": bool(lui.get("retire")), "rapports": rapports,
            "historique": {"remplaces": _remplaces(cours, groupe, etudiant), "ecartes": _ecartes(cours, groupe, etudiant, da)}}
