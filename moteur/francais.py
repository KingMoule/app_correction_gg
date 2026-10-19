"""API de la correction du français : extraction du PDF, fautes, décisions, barème.

`/analyser` est sans état (PDF reçu, rien conservé). Pour un rapport rangé dans la
bibliothèque, l'analyse et les décisions de Guillaume (accepter/refuser, correction
choisie) sont enregistrées dans `francais.json` à côté de `rapport.pdf`; le barème
est par cours (`<cours>/bareme.json`).
"""

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import languagetool, pdf_texte
from .bareme import Bareme, penalite
from .bibliotheque import chemin_rapport, racine, segment_sur

router = APIRouter(prefix="/api/francais")


class DemandeBareme(BaseModel):
    nb_fautes: int
    bareme: Bareme = Bareme()


@router.post("/bareme")
def calculer_bareme(d: DemandeBareme) -> dict:
    return {"nb_fautes": d.nb_fautes, "penalite": penalite(d.nb_fautes, d.bareme)}


def analyser_fichier(chemin: Path) -> tuple[pdf_texte.TexteExtrait, list[dict]]:
    """Texte extrait et fautes (avec `zones` à surligner), ou HTTPException."""
    try:
        extrait = pdf_texte.extraire(chemin)
    except pdf_texte.PdfSansTexte as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(400, f"PDF illisible : {e}")
    try:
        fautes = languagetool.verifier(extrait.texte)
    except languagetool.LanguageToolIndisponible as e:
        raise HTTPException(503, str(e))
    return extrait, [{"id": i, **asdict(f), "zones": extrait.zones(f.debut, f.fin)} for i, f in enumerate(fautes)]


@router.post("/analyser")
async def analyser(
    pdf: UploadFile = File(...),
    points_par_faute: float = Form(0.5),
    plafond: float | None = Form(None),
) -> dict:
    """Texte, fautes (avec zones à surligner) et pénalité si toutes sont acceptées."""
    contenu = await pdf.read()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "rapport.pdf"
        chemin.write_bytes(contenu)
        extrait, fautes = analyser_fichier(chemin)
    bareme = Bareme(points_par_faute=points_par_faute, plafond=plafond)
    return {
        "texte": extrait.texte,
        "pages": [asdict(p) for p in extrait.pages],
        "fautes": fautes,
        "penalite_si_toutes_acceptees": penalite(len(fautes), bareme),
    }


# --- Barème par cours -------------------------------------------------------

def fichier_bareme(cours: str) -> Path:
    dossier = racine() / segment_sur(cours, "cours")
    if not dossier.is_dir():
        raise HTTPException(404, f"Cours inconnu : {cours}.")
    return dossier / "bareme.json"


def lire_bareme(cours: str) -> Bareme:
    f = fichier_bareme(cours)
    return Bareme.model_validate_json(f.read_text(encoding="utf-8")) if f.is_file() else Bareme()


@router.get("/bareme/{cours}")
def obtenir_bareme(cours: str) -> Bareme:
    return lire_bareme(cours)


@router.put("/bareme/{cours}")
def regler_bareme(cours: str, bareme: Bareme) -> Bareme:
    ecrire(fichier_bareme(cours), bareme.model_dump())
    return bareme


# --- Rapport rangé : analyse et décisions enregistrées ------------------------

class Decisions(BaseModel):
    decisions: dict[str, Literal["acceptee", "refusee"]] = {}  # id de faute -> décision; absent = à trancher
    choix: dict[str, str] = {}  # id de faute -> correction écrite (par défaut : 1re suggestion)
    masquees: list[int] = []  # fautes dont la correction manuscrite est effacée (surlignage seul)


def ecrire(fichier: Path, contenu: dict) -> None:
    # Écriture atomique : un plantage ne laisse jamais un fichier à moitié écrit.
    temporaire = fichier.with_name(fichier.name + ".tmp")
    temporaire.write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(temporaire, fichier)


def fichiers_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> tuple[Path, Path]:
    rapport = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not rapport.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return rapport, rapport.with_name("francais.json")


def etat(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    _, f = fichiers_rapport(cours, groupe, lab, etudiant)
    bareme = lire_bareme(cours)
    doc = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    if doc is None:
        return {"analyse": False, "fautes": [], "decisions": {}, "choix": {}, "masquees": [],
                "nb_acceptees": 0, "penalite": 0.0, "bareme": bareme.model_dump()}
    nb = sum(1 for d in doc["decisions"].values() if d == "acceptee")
    return {"analyse": True, **doc, "nb_acceptees": nb, "penalite": penalite(nb, bareme),
            "bareme": bareme.model_dump()}


@router.get("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def obtenir(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    return etat(cours, groupe, lab, etudiant)


@router.post("/rapport/{cours}/{groupe}/{lab}/{etudiant}/analyser")
def analyser_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    """Analyse le rapport rangé. Une nouvelle analyse garde les décisions des fautes inchangées."""
    rapport, f = fichiers_rapport(cours, groupe, lab, etudiant)
    _, fautes = analyser_fichier(rapport)
    ancien = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    nouveau = {"version": 1, "fautes": fautes, "decisions": {}, "choix": {}, "masquees": []}
    if ancien:
        position = {(a["debut"], a["fin"], a["texte"]): str(a["id"]) for a in ancien["fautes"]}
        for fa in fautes:
            vieux = position.get((fa["debut"], fa["fin"], fa["texte"]))
            if vieux is None:
                continue
            nid = str(fa["id"])
            if vieux in ancien["decisions"]:
                nouveau["decisions"][nid] = ancien["decisions"][vieux]
            if vieux in ancien["choix"]:
                nouveau["choix"][nid] = ancien["choix"][vieux]
            if int(vieux) in ancien["masquees"]:
                nouveau["masquees"].append(fa["id"])
    ecrire(f, nouveau)
    return etat(cours, groupe, lab, etudiant)


@router.put("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def enregistrer_decisions(cours: str, groupe: str, lab: str, etudiant: str, d: Decisions) -> dict:
    _, f = fichiers_rapport(cours, groupe, lab, etudiant)
    if not f.is_file():
        raise HTTPException(409, "Rapport pas encore analysé.")
    doc = json.loads(f.read_text(encoding="utf-8"))
    ids = {str(x["id"]) for x in doc["fautes"]}
    if not (set(d.decisions) | set(d.choix) | {str(m) for m in d.masquees}) <= ids:
        raise HTTPException(422, "Faute inconnue.")
    doc.update(d.model_dump())
    ecrire(f, doc)
    return etat(cours, groupe, lab, etudiant)
