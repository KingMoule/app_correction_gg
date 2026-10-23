"""« Reprendre » et « Récents » enregistrés par le moteur (le PC voit ce que l'iPad a ouvert).

`<données>/reprendre.json` : les 5 derniers rapports ouverts, sans doublon, le plus récent d'abord
(`dernier` = le premier). Écrit par le lecteur à chaque ouverture; rien de plus que l'identité du rapport.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import bibliotheque, stockage
from .config import dossier_donnees

router = APIRouter(prefix="/api/reprendre")

GARDE = 5
APPAREILS = ("iPad", "PC")


class Ouverture(BaseModel):
    cours: str = Field(max_length=40)
    groupe: str = Field(max_length=40)
    lab: str = Field(max_length=40)
    etudiant: str = Field(max_length=120)
    appareil: str | None = Field(None, max_length=20)  # « iPad » ou « PC »; sinon déduit du User-Agent


def _fichier():
    return dossier_donnees() / "reprendre.json"


def _appareil(demande: str | None, agent: str) -> str:
    if demande in APPAREILS:
        return demande
    return "iPad" if "iPad" in agent or "iPhone" in agent else "PC"


def _cle(r: dict) -> tuple:
    return (r.get("cours"), r.get("groupe"), r.get("lab"), r.get("etudiant"))


def _recents(doc) -> list[dict]:
    recents = doc.get("recents") if isinstance(doc, dict) else None
    return [r for r in recents if isinstance(r, dict)][:GARDE] if isinstance(recents, list) else []


def _reponse(recents: list[dict]) -> dict:
    return {"dernier": recents[0] if recents else None, "recents": recents}


@router.get("")
def lire() -> dict:
    return _reponse(_recents(stockage.lire_json(_fichier(), {})))


@router.put("")
def enregistrer(o: Ouverture, requete: Request) -> dict:
    for valeur, nom in ((o.cours, "cours"), (o.groupe, "groupe"), (o.lab, "lab"), (o.etudiant, "étudiant")):
        bibliotheque.segment_sur(valeur, nom)
    if not bibliotheque.chemin_rapport(o.cours, o.groupe, o.lab, o.etudiant).is_file():
        raise HTTPException(404, "Rapport introuvable.")
    eleve = next((e for e in bibliotheque.etudiants_du_cours(o.cours, o.groupe) if e["id"] == o.etudiant), {})
    entree = {"cours": o.cours, "groupe": o.groupe, "lab": o.lab, "etudiant": o.etudiant,
              "nom": eleve.get("nom", ""), "prenom": eleve.get("prenom", ""),
              "date": datetime.now().astimezone().isoformat(timespec="seconds"),
              "appareil": _appareil(o.appareil, requete.headers.get("user-agent", ""))}

    def ajouter(doc):
        reste = [r for r in _recents(doc) if _cle(r) != _cle(entree)]
        return {"recents": [entree, *reste][:GARDE]}

    return _reponse(_recents(stockage.modifier_json(_fichier(), ajouter, {})))
