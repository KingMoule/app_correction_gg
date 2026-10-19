"""API de la correction du français : extraction du PDF, fautes, barème.

Sans état : le PDF est reçu, analysé, et rien n'est conservé. La bibliothèque
et l'enregistrement des décisions (accepter/refuser) viendront d'autres fils.
"""

import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import languagetool, pdf_texte
from .bareme import Bareme, penalite

router = APIRouter(prefix="/api/francais")


class DemandeBareme(BaseModel):
    nb_fautes: int
    bareme: Bareme = Bareme()


@router.post("/bareme")
def calculer_bareme(d: DemandeBareme) -> dict:
    return {"nb_fautes": d.nb_fautes, "penalite": penalite(d.nb_fautes, d.bareme)}


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
    resultat = []
    for i, f in enumerate(fautes):
        resultat.append({"id": i, **asdict(f), "zones": extrait.zones(f.debut, f.fin)})
    bareme = Bareme(points_par_faute=points_par_faute, plafond=plafond)
    return {
        "texte": extrait.texte,
        "pages": [asdict(p) for p in extrait.pages],
        "fautes": resultat,
        "penalite_si_toutes_acceptees": penalite(len(resultat), bareme),
    }
