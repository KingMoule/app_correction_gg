"""Annotations manuscrites (crayon, surligneur) d'un rapport.

Stockées à côté du rapport, séparées du PDF : `.../<lab>/<étudiant>/annotations.json`.
Le PDF annoté n'est créé qu'à l'export. Coordonnées en points PDF, origine en haut
à gauche de la page, comme les zones des fautes de français.
"""

import json
import os
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .bibliotheque import chemin_rapport, segment_sur

router = APIRouter(prefix="/api/annotations")

COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")


class Trait(BaseModel):
    outil: Literal["crayon", "surligneur"]
    couleur: str = Field(pattern=COULEUR.pattern)
    largeur_min: float = Field(gt=0, le=60)
    largeur_max: float = Field(gt=0, le=60)
    courbe: float = Field(1, gt=0, le=5)
    points: list[tuple[float, float, float]] = Field(min_length=1)  # x, y, pression (0 à 1)


class Annotations(BaseModel):
    version: Literal[1] = 1
    pages: dict[str, list[Trait]] = {}  # clé : numéro de page, à partir de 1


def fichier_annotations(cours: str, groupe: str, lab: str, etudiant: str) -> Path:
    rapport = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not rapport.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return rapport.with_name("annotations.json")


def lire(cours: str, groupe: str, lab: str, etudiant: str) -> Annotations:
    f = fichier_annotations(cours, groupe, lab, etudiant)
    if not f.is_file():
        return Annotations()
    return Annotations.model_validate_json(f.read_text(encoding="utf-8"))


@router.get("/{cours}/{groupe}/{lab}/{etudiant}")
def obtenir(cours: str, groupe: str, lab: str, etudiant: str) -> Annotations:
    return lire(cours, groupe, lab, etudiant)


@router.put("/{cours}/{groupe}/{lab}/{etudiant}")
def enregistrer(cours: str, groupe: str, lab: str, etudiant: str, doc: Annotations) -> dict:
    f = fichier_annotations(cours, groupe, lab, etudiant)
    doc.pages = {k: v for k, v in doc.pages.items() if v}
    # Écriture atomique : un plantage ne laisse jamais un fichier à moitié écrit.
    temporaire = f.with_name(f.name + ".tmp")
    temporaire.write_text(json.dumps(doc.model_dump(), separators=(",", ":")), encoding="utf-8")
    os.replace(temporaire, f)
    return {"ok": True, "traits": sum(len(v) for v in doc.pages.values())}
