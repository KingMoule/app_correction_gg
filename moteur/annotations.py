"""Annotations manuscrites (crayon, surligneur) d'un rapport.

Stockées à côté du rapport, séparées du PDF : `.../<lab>/<étudiant>/annotations.json`.
Le PDF annoté n'est créé qu'à l'export. Coordonnées en points PDF, origine en haut
à gauche de la page, comme les zones des fautes de français.
"""

import re
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from . import stockage
from .bibliotheque import chemin_rapport, segment_sur

router = APIRouter(prefix="/api/annotations")

COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")


class Trait(BaseModel):
    id: str | None = Field(None, max_length=64)  # stable; donné au chargement pour les fichiers de version 1
    outil: Literal["crayon", "surligneur"]
    couleur: str = Field(pattern=COULEUR.pattern)
    largeur_min: float = Field(gt=0, le=60)
    largeur_max: float = Field(gt=0, le=60)
    courbe: float = Field(1, gt=0, le=5)
    points: list[tuple[float, float, float]] = Field(min_length=1)  # x, y, pression (0 à 1)


class Annotations(BaseModel):
    """Version 2 : `revision` (compteur augmenté à chaque écriture) et `supprimes` (identifiants des
    traits effacés, gardés pour que la fusion de deux appareils ne les ressuscite pas). Les traits
    effacés ne sont plus dans `pages` : le rendu et l'export ne changent pas. La version 1 (sans
    révision ni identifiant) est lue comme révision 0, avec des identifiants déterministes."""
    version: Literal[1, 2] = 2
    revision: int = Field(0, ge=0)
    pages: dict[str, list[Trait]] = {}  # clé : numéro de page, à partir de 1
    supprimes: list[str] = []


def _normaliser(doc: Annotations) -> Annotations:
    """Version 2, identifiants uniques (déterministes `p<page>-<rang>` pour les traits qui n'en ont pas)."""
    vus: set[str] = set()
    for page, traits in doc.pages.items():
        for i, t in enumerate(traits):
            if not t.id or t.id in vus:
                t.id = f"p{page}-{i}" if f"p{page}-{i}" not in vus else uuid.uuid4().hex[:16]
            vus.add(t.id)
    doc.version = 2
    doc.supprimes = [i for i in dict.fromkeys(doc.supprimes) if i not in vus]
    return doc


def fichier_annotations(cours: str, groupe: str, lab: str, etudiant: str) -> Path:
    rapport = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not rapport.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return rapport.with_name("annotations.json")


def lire(cours: str, groupe: str, lab: str, etudiant: str) -> Annotations:
    f = fichier_annotations(cours, groupe, lab, etudiant)
    if not f.is_file():
        return Annotations()
    donnees = stockage.lire_json(f)
    try:
        return _normaliser(Annotations.model_validate(donnees)) if donnees is not None else Annotations()
    except ValidationError as e:  # fichier JSON valide mais de forme inattendue
        stockage.journal.warning("Annotations illisibles dans %s : %s", f, e)
        return Annotations()


@router.get("/{cours}/{groupe}/{lab}/{etudiant}")
def obtenir(cours: str, groupe: str, lab: str, etudiant: str) -> Annotations:
    return lire(cours, groupe, lab, etudiant)


@router.put("/{cours}/{groupe}/{lab}/{etudiant}")
def enregistrer(cours: str, groupe: str, lab: str, etudiant: str, doc: Annotations):
    """Remplace le document si `revision` est celle du moteur; sinon 409 avec le document actuel
    (le lecteur le fusionne avec ses traits et renvoie). Les identifiants effacés s'accumulent dans
    `supprimes`, sauf ceux qui sont de nouveau présents (annuler après un gommage déjà enregistré)."""
    f = fichier_annotations(cours, groupe, lab, etudiant)
    with stockage.verrou(f.parent):
        actuel = lire(cours, groupe, lab, etudiant)
        if doc.revision != actuel.revision:
            return JSONResponse(status_code=409, content={
                "detail": "Annotations modifiées depuis un autre appareil.",
                "actuel": actuel.model_dump(),
            })
        doc.pages = {k: v for k, v in doc.pages.items() if v}
        doc.supprimes = list(dict.fromkeys(actuel.supprimes + doc.supprimes))
        doc = _normaliser(doc)
        doc.revision = actuel.revision + 1
        stockage.ecrire_json(f, doc.model_dump(), separators=(",", ":"))
    return {"ok": True, "traits": sum(len(v) for v in doc.pages.values()), "revision": doc.revision}
