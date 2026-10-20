"""Export du PDF annoté pour LÉA.

Le rapport reste intact sur le disque : le PDF annoté n'existe qu'ici, à la demande.
On dessine par-dessus chaque page les surlignages du crayon, les traits (largeur selon
la pression, comme à l'écran) et les fautes de français *acceptées* (surlignage rouge,
correction manuscrite sauf si effacée). Coordonnées : points PDF, origine en haut à gauche.
"""

import io
import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import Response
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .annotations import Annotations, Trait, lire
from .francais import fichiers_rapport

router = APIRouter(prefix="/api/export")

POLICE = "Caveat"
FICHIER_POLICE = Path(__file__).parent / "polices" / "Caveat-Bold.ttf"
TAILLE_CORRECTION = 14
OPACITE_SURLIGNEUR = 0.4  # comme à l'écran
ROUGE_FAUTE = "#e53935"
ROUGE_CORRECTION = "#c62828"


def enregistrer_police() -> None:
    if POLICE not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(POLICE, str(FICHIER_POLICE)))


def largeur(t: Trait, p: float) -> float:
    return t.largeur_min + (t.largeur_max - t.largeur_min) * min(1.0, max(0.0, p)) ** t.courbe


def dessiner_trait(c: canvas.Canvas, t: Trait, haut: float) -> None:
    """Même construction qu'à l'écran : courbes quadratiques entre milieux de segments."""
    pts = [(x, haut - y, p) for x, y, p in t.points]  # y vers le haut
    c.setStrokeColor(HexColor(t.couleur))
    c.setFillColor(HexColor(t.couleur))
    c.setLineCap(1)
    c.setLineJoin(1)
    if len(pts) == 1:
        x, y, p = pts[0]
        c.circle(x, y, largeur(t, p) / 2, stroke=0, fill=1)
        return

    def milieu(a, b):
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)

    def courbe(a, ctrl, fin, w):
        c.setLineWidth(w)
        p = c.beginPath()
        p.moveTo(a[0], a[1])
        # quadratique -> cubique
        p.curveTo(a[0] + 2 / 3 * (ctrl[0] - a[0]), a[1] + 2 / 3 * (ctrl[1] - a[1]),
                  fin[0] + 2 / 3 * (ctrl[0] - fin[0]), fin[1] + 2 / 3 * (ctrl[1] - fin[1]),
                  fin[0], fin[1])
        c.drawPath(p, stroke=1, fill=0)

    prec = pts[0]
    for i in range(1, len(pts)):
        m = milieu(pts[i - 1], pts[i])
        courbe(prec, pts[i - 1], m, largeur(t, (prec[2] + m[2]) / 2))
        prec = m
    courbe(prec, pts[-1], pts[-1], largeur(t, (prec[2] + pts[-1][2]) / 2))


def dessiner_surligneur(c: canvas.Canvas, t: Trait, haut: float) -> None:
    """Un seul tracé de largeur constante : le recouvrement dans un même trait ne fonce pas."""
    c.setStrokeColor(HexColor(t.couleur))
    c.setStrokeAlpha(OPACITE_SURLIGNEUR)  # après la couleur : setStrokeColor remet l'opacité à 1
    c.setLineWidth(t.largeur_max)
    c.setLineCap(1)
    c.setLineJoin(1)
    pts = [(x, haut - y) for x, y, _ in t.points]
    if len(pts) == 1:
        pts.append((pts[0][0] + 0.01, pts[0][1]))
    p = c.beginPath()
    p.moveTo(*pts[0])
    for x, y in pts[1:]:
        p.lineTo(x, y)
    c.drawPath(p, stroke=1, fill=0)


def fautes_acceptees(chemin_francais: Path) -> list[dict]:
    if not chemin_francais.is_file():
        return []
    doc = json.loads(chemin_francais.read_text(encoding="utf-8"))
    sortie = []
    for f in doc["fautes"]:
        sid = str(f["id"])
        if doc["decisions"].get(sid) != "acceptee":
            continue
        correction = doc["choix"].get(sid) or (f["suggestions"][0] if f["suggestions"] else None)
        dx, dy = doc.get("decalages", {}).get(sid, (0, 0))  # correction déplacée à la main (points PDF)
        sortie.append({"zones": f["zones"], "correction": None if f["id"] in doc["masquees"] else correction,
                       "decalage": (dx, dy)})
    return sortie


def annoter(pdf_source: Path, annotations: Annotations, fautes: list[dict]) -> bytes:
    enregistrer_police()
    sortie = PdfWriter(clone_from=str(pdf_source))
    for numero, page in enumerate(sortie.pages, start=1):
        x0, y0 = float(page.mediabox.left), float(page.mediabox.bottom)
        larg, haut = float(page.mediabox.width), float(page.mediabox.height)
        traits = annotations.pages.get(str(numero), [])
        zones = [(f, z) for f in fautes for z in f["zones"] if z["page"] == numero]
        if traits or zones:
            tampon = io.BytesIO()
            c = canvas.Canvas(tampon, pagesize=(larg, haut))
            c.translate(x0, y0)  # le coin bas gauche de la page n'est pas toujours (0, 0)
            for _, z in zones:  # surlignage rouge des fautes acceptées
                c.saveState()
                c.setFillColor(HexColor(ROUGE_FAUTE))
                c.setBlendMode("Multiply")  # le texte du rapport reste lisible sous le surlignage
                c.setFillAlpha(0.35)
                c.rect(z["x0"], haut - z["y1"], z["x1"] - z["x0"], z["y1"] - z["y0"], stroke=0, fill=1)
                c.restoreState()
            for t in traits:
                if t.outil == "surligneur":
                    c.saveState(); c.setBlendMode("Multiply"); dessiner_surligneur(c, t, haut); c.restoreState()
            for t in traits:
                if t.outil == "crayon":
                    c.saveState(); dessiner_trait(c, t, haut); c.restoreState()
            for f in fautes:  # corrections manuscrites, au-dessus du premier mot
                z = next((z for z in f["zones"]), None)
                if f["correction"] and z and z["page"] == numero:
                    c.setFillColor(HexColor(ROUGE_CORRECTION))
                    c.setFont(POLICE, TAILLE_CORRECTION)
                    dx, dy = f.get("decalage", (0, 0))
                    c.drawString(z["x0"] + dx, haut - (z["y0"] + dy) + 1, f["correction"])
            c.save()
            tampon.seek(0)
            page.merge_page(PdfReader(tampon).pages[0])
    resultat = io.BytesIO()
    sortie.write(resultat)
    return resultat.getvalue()


@router.get("/{cours}/{groupe}/{lab}/{etudiant}")
def exporter(cours: str, groupe: str, lab: str, etudiant: str) -> Response:
    rapport, francais = fichiers_rapport(cours, groupe, lab, etudiant)
    contenu = annoter(rapport, lire(cours, groupe, lab, etudiant), fautes_acceptees(francais))
    return Response(contenu, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{etudiant}_{lab}_annote.pdf"'})
