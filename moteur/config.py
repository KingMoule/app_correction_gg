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


def chemin_a_risque(chemin: Path) -> str | None:
    """Pourquoi ce dossier de données est à risque, ou None s'il est sûr.

    Dans le dépôt Git ou sous OneDrive, les données peuvent être commitées
    par erreur ou synchronisées dans le nuage.
    """
    absolu = chemin.resolve()
    try:
        absolu.relative_to(RACINE)
        return "dans le dépôt Git"
    except ValueError:
        pass
    if any("onedrive" in morceau.lower() for morceau in absolu.parts):
        return "dans OneDrive"
    return None
