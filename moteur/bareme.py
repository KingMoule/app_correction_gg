"""Barème de pénalité pour le français : points par faute, plafond optionnel."""

from pydantic import BaseModel, Field


class Bareme(BaseModel):
    points_par_faute: float = Field(0.5, ge=0)
    plafond: float | None = Field(None, ge=0)  # None = aucun plafond


def penalite(nb_fautes: int, bareme: Bareme) -> float:
    """Pénalité totale pour `nb_fautes` fautes acceptées, plafonnée si demandé."""
    total = max(nb_fautes, 0) * bareme.points_par_faute
    if bareme.plafond is not None:
        total = min(total, bareme.plafond)
    return round(total, 2)
