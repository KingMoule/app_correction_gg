"""Extraction du texte d'un PDF (exporté de Word) avec la position de chaque mot.

Le texte complet est reconstruit mot à mot : chaque mot garde son intervalle
[debut, fin) dans ce texte, ce qui permet de transformer une faute signalée par
LanguageTool (décalage + longueur) en rectangles à surligner sur la page.
Coordonnées en points PDF, origine en haut à gauche de la page.
"""

from dataclasses import dataclass
from pathlib import Path

import pdfplumber


class PdfSansTexte(Exception):
    """PDF sans couche de texte (scan) : refusé, voir PLAN.md (OCR plus tard)."""


@dataclass
class Mot:
    page: int  # à partir de 1
    debut: int
    fin: int
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass
class Page:
    numero: int
    largeur: float
    hauteur: float


@dataclass
class TexteExtrait:
    texte: str
    pages: list[Page]
    mots: list[Mot]

    def zones(self, debut: int, fin: int) -> list[dict]:
        """Rectangles couvrant [debut, fin), un par ligne et par page."""
        lignes: dict[tuple[int, float], dict] = {}
        for m in self.mots:
            if m.fin <= debut or m.debut >= fin:
                continue
            cle = (m.page, round(m.y0, 0))
            z = lignes.get(cle)
            if z is None:
                lignes[cle] = {"page": m.page, "x0": m.x0, "y0": m.y0, "x1": m.x1, "y1": m.y1}
            else:
                z["x0"], z["x1"] = min(z["x0"], m.x0), max(z["x1"], m.x1)
                z["y0"], z["y1"] = min(z["y0"], m.y0), max(z["y1"], m.y1)
        return list(lignes.values())


def extraire(chemin: str | Path) -> TexteExtrait:
    morceaux: list[str] = []
    pages: list[Page] = []
    mots: list[Mot] = []
    longueur = 0
    with pdfplumber.open(chemin) as pdf:
        for i, p in enumerate(pdf.pages, start=1):
            pages.append(Page(i, float(p.width), float(p.height)))
            ligne_prec = None
            for w in p.extract_words(keep_blank_chars=False, use_text_flow=False):
                ligne = round(w["top"], 0)
                if morceaux:
                    sep = " " if ligne_prec == ligne else "\n"
                    morceaux.append(sep)
                    longueur += len(sep)
                debut = longueur
                morceaux.append(w["text"])
                longueur += len(w["text"])
                mots.append(Mot(i, debut, longueur, w["x0"], w["top"], w["x1"], w["bottom"]))
                ligne_prec = ligne
            if morceaux and i < len(pdf.pages):
                morceaux.append("\n")
                longueur += 1
    texte = "".join(morceaux)
    if not texte.strip():
        raise PdfSansTexte("Le PDF ne contient pas de texte (scan ?).")
    return TexteExtrait(texte, pages, mots)
