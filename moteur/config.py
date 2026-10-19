"""Chemins et réglages du moteur."""

import os
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_PWA = RACINE / "pwa"


def dossier_donnees() -> Path:
    """Dossier local des données (bibliothèque, listes de classe, annotations).

    Hors dépôt : `donnees/` est dans .gitignore. Modifiable avec la variable
    d'environnement CORRECTION_DONNEES.
    """
    chemin = Path(os.environ.get("CORRECTION_DONNEES", RACINE / "donnees"))
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin
