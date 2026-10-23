"""Session d'enseignement (A2026 = automne 2026, H2027 = hiver 2027) et identifiant de cours.

Le code de cours et le n° de groupe d'Omnivox reviennent d'une session à l'autre : sans la session,
la liste de classe et les labs de la session suivante tomberaient dans les dossiers de la précédente.
La session fait donc partie de l'**identifiant du cours** (le premier segment de tous les chemins et de
toutes les routes) : `202SNURE_A2026`. Le code d'Omnivox (`202SNURE`, lettres et chiffres seulement)
ne contient jamais de `_`, donc l'identifiant se sépare sans ambiguïté.
"""

import os
import re
from datetime import date

from fastapi import HTTPException

from . import stockage
from .config import dossier_donnees

MOTIF_SESSION = re.compile(r"^[AH][0-9]{4}$")
MOTIF_CLE = re.compile(r"^(?P<code>[A-Za-z0-9]+)_(?P<session>[AH][0-9]{4})$")
LIBELLES = {"A": "Automne", "H": "Hiver"}


def session_du_jour(jour: date | None = None) -> str:
    """Automne d'août à décembre (A), hiver de janvier à juillet (H). Pas d'été (décision de Guillaume)."""
    jour = jour or date.today()
    return f"{'A' if jour.month >= 8 else 'H'}{jour.year}"


def valider(session: str) -> str:
    session = (session or "").strip().upper()
    if not MOTIF_SESSION.match(session):
        raise HTTPException(400, "Session invalide : une lettre (A automne, H hiver) et l'année, par exemple A2026.")
    return session


def libelle(session: str) -> str:
    """« A2026 » → « Automne 2026 »."""
    return f"{LIBELLES.get(session[:1], session[:1])} {session[1:]}"


def cle_cours(code: str, session: str) -> str:
    return f"{code.upper()}_{valider(session)}"


def separer(cle: str) -> tuple[str, str | None]:
    """(code Omnivox, session) d'un identifiant de cours; session None pour un ancien dossier sans session."""
    m = MOTIF_CLE.match(cle)
    return (m["code"], m["session"]) if m else (cle, None)


def code_du_cours(cle: str) -> str:
    return separer(cle)[0]


def ordre(session: str) -> tuple[int, int]:
    """Clé de tri chronologique : (année, 0 hiver / 1 automne)."""
    return int(session[1:]), 0 if session[0] == "H" else 1


def _fichier() -> "os.PathLike":
    return dossier_donnees() / "session.json"


def session_courante() -> str:
    """Session en cours : variable `CORRECTION_SESSION` (tests), sinon celle que Guillaume a choisie
    (`session.json`), sinon celle de la date du jour."""
    env = os.environ.get("CORRECTION_SESSION", "").strip().upper()
    if MOTIF_SESSION.match(env):
        return env
    doc = stockage.lire_json(_fichier(), {})
    choisie = doc.get("courante") if isinstance(doc, dict) else None
    return choisie if isinstance(choisie, str) and MOTIF_SESSION.match(choisie) else session_du_jour()


def choisir_courante(session: str) -> str:
    session = valider(session)
    stockage.ecrire_json(_fichier(), {"courante": session})
    return session
