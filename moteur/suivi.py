"""Tableau de suivi d'un lab : l'état de chaque rapport en un seul appel.

Ne calcule rien de nouveau : relit les fichiers déjà écrits à côté de chaque rapport
(annotations, français, indices d'IA, références, statut) et les décisions de plagiat. Les indices
d'IA et de plagiat sont des indices à revérifier, jamais un verdict.
"""

from fastapi import APIRouter, HTTPException

from . import bibliotheque, plagiat
from .annotations import lire as lire_annotations
from .bareme import penalite
from .export_lot import _json, claude_fait, etat_export
from .francais import lire_bareme

router = APIRouter(prefix="/api/suivi")

ETATS_PLAGIAT = {"a_confirmer": "suspecte", "en_cours": "suspecte", "erreur": "suspecte",
                 "analysee": "confirmee", "ecartee": "ecartee"}  # « sous_seuil » : rien à signaler


def _plagiat_par_rapport(cours: str, lab: str) -> dict[tuple[str, str], dict]:
    """{(groupe, étudiant): {etat, avec}} : l'état le plus sérieux des paires du rapport."""
    gravite = ["ecartee", "suspecte", "confirmee"]
    sortie: dict[tuple[str, str], dict] = {}
    for p in plagiat.etat_des_paires():
        etat = ETATS_PLAGIAT.get(p["statut"])
        if not etat:
            continue
        for moi, autre in ((p["a"], p["b"]), (p["b"], p["a"])):
            if (moi["cours"], moi["lab"]) != (cours, lab):
                continue
            actuel = sortie.setdefault((moi["groupe"], moi["etudiant"]), {"etat": etat, "avec": []})
            if gravite.index(etat) > gravite.index(actuel["etat"]):
                actuel["etat"], actuel["avec"] = etat, []  # seules les paires de l'état le plus sérieux sont citées
            if etat == actuel["etat"]:
                actuel["avec"].append(autre.get("nom") or autre["etudiant"])
    return sortie


def _francais(doc: dict | None, bareme: dict) -> dict:
    if doc is None:
        return {"etat": "non_analyse"}
    decisions = doc.get("decisions", {})
    acceptees = sum(1 for d in decisions.values() if d == "acceptee")
    a_trancher = sum(1 for f in doc.get("fautes", []) if str(f["id"]) not in decisions)
    return {"etat": "a_trancher" if a_trancher else "tranche", "a_trancher": a_trancher,
            "acceptees": acceptees, "penalite": penalite(acceptees, bareme),
            "claude_manquant": not claude_fait(doc)}  # passe Claude échouée ou jamais faite (voir export_lot)


def _references(doc: dict | None) -> dict:
    """Résumé de la vérification des références (un indice à revérifier, sans effet sur l'état ni la note)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("resume"), dict):
        return {"etat": "non_analyse"}
    r = doc["resume"]
    signale = sum(r.get(k, 0) for k in ("introuvables", "divergentes", "douteuses", "sans_lien", "erreurs_forme", "liaison"))
    return {"etat": "a_revoir" if signale or not (doc.get("section") or {}).get("trouvee") else "ok",
            "texte": r.get("texte", ""), "resume": r, "claude_ok": bool((doc.get("claude") or {}).get("ok"))}


def _commence(cours: str, groupe: str, lab: str, etudiant: str) -> bool:
    try:
        pages = lire_annotations(cours, groupe, lab, etudiant).pages
    except (HTTPException, ValueError):  # fichier absent ou illisible : pas commencée
        return False
    return any(pages.values())


def etat_global(termine: bool, annote: bool, francais: dict, ia) -> str:
    if termine:
        return "termine"
    return "en_cours" if (annote or francais["etat"] != "non_analyse" or ia) else "a_corriger"


@router.get("/{cours}/{lab}")
def suivi(cours: str, lab: str, groupe: str | None = None) -> dict:
    bibliotheque.segment_sur(lab, "lab")
    classes = [c for c in bibliotheque.classes_du_cours(cours) if not groupe or c["groupe"] == groupe]
    if not classes:
        raise HTTPException(404, f"Aucune liste de classe pour {cours}" + (f" groupe {groupe}." if groupe else "."))
    bareme = lire_bareme(cours)
    plag = _plagiat_par_rapport(cours, lab)
    rapports, dossiers = [], {}
    for c in classes:
        for e in c["etudiants"]:
            dossier = bibliotheque.chemin_rapport(cours, c["groupe"], lab, e["id"]).parent
            if not (dossier / "rapport.pdf").is_file():
                continue
            dossiers[f"{c['groupe']}/{e['id']}"] = dossier
            fr = _francais(_json(dossier / "francais.json"), bareme)
            ia = (_json(dossier / "indices_ia.json") or {}).get("force") or None
            termine = bool((_json(dossier / "statut.json") or {}).get("termine"))
            annote = _commence(cours, c["groupe"], lab, e["id"])
            p = plag.get((c["groupe"], e["id"]))
            rapports.append({
                "groupe": c["groupe"], "etudiant": e["id"], "nom": e["nom"], "prenom": e["prenom"],
                "equipe": [f"{m['prenom']} {m['nom']}" for m in _json(dossier / "equipe.json") or []],
                "annotation": annote, "francais": fr, "ia": ia,
                "references": _references(_json(dossier / "references.json")), "plagiat": p, "termine": termine,
                "note": bibliotheque.lire_note(dossier),
                "etat": etat_global(termine, annote, fr, ia),
                "a_revoir": bool(fr["etat"] == "a_trancher" or ia == "marquee" or (p and p["etat"] != "ecartee")),
            })
    rapports.sort(key=lambda r: (r["groupe"], bibliotheque.normaliser(r["nom"]), bibliotheque.normaliser(r["prenom"])))
    compte = {k: sum(1 for r in rapports if r["etat"] == k) for k in ("a_corriger", "en_cours", "termine")}
    compte["a_revoir"] = sum(1 for r in rapports if r["a_revoir"] and not r["termine"])
    archive = all(bibliotheque._lire_drapeau(bibliotheque.dossier_groupe(cours, c["groupe"]) / lab / "archive.json", "archive")
                  for c in classes if (bibliotheque.dossier_groupe(cours, c["groupe"]) / lab).is_dir())
    return {"cours": cours, "lab": lab, "groupes": [c["groupe"] for c in classes], "archive": archive,
            "total": len(rapports), "compte": compte, "rapports": rapports,
            "export": etat_export(cours, lab, dossiers)}
