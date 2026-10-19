"""Application web du moteur : API sous /api, PWA servie à la racine.

Pour ajouter une fonction (import, français, plagiat, IA) : créer un module
`moteur/<fonction>.py` avec un `APIRouter`, puis l'inscrire dans `creer_app`.
"""

from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__, annotations, bibliotheque, francais
from .config import DOSSIER_PWA, dossier_donnees

api = APIRouter(prefix="/api")


@api.get("/etat")
def etat() -> dict:
    """Vérifie que le moteur répond et que le dossier de données est prêt."""
    return {
        "ok": True,
        "version": __version__,
        "donnees": str(dossier_donnees()),
    }


def creer_app() -> FastAPI:
    app = FastAPI(title="Correction de labs", version=__version__)
    app.include_router(api)
    app.include_router(bibliotheque.router)
    app.include_router(francais.router)
    app.include_router(annotations.router)
    # Doit rester en dernier : sert la PWA pour toute route non-API.
    app.mount("/", StaticFiles(directory=DOSSIER_PWA, html=True), name="pwa")
    return app


app = creer_app()
