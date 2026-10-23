"""Tests de l'export du PDF annoté. Données fictives seulement."""

import io
import json

import pdfplumber
import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from tests.test_annotations import TRAIT, URL
from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: F401

URL_EXPORT = "/api/export/202SNURE_A2026/00002/lab-3/dube-alice"
SURLIGNEUR = {"outil": "surligneur", "couleur": "#ffee58", "largeur_min": 11, "largeur_max": 11,
              "courbe": 1, "points": [[100, 300, 0.5], [300, 300, 0.5]]}


@pytest.fixture
def rapport(client, tmp_path):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf("Les etudiants mesure la tension."))])
    return client, tmp_path / "bibliotheque/202SNURE_A2026/00002/lab-3/dube-alice"


def pixels_colores(contenu: bytes, rect, page: int = 1):
    """Pixels non blancs de la page `page` dans rect (points PDF, origine en haut à gauche)."""
    with pdfplumber.open(io.BytesIO(contenu)) as p:
        image = p.pages[page - 1].to_image(resolution=72).original.convert("RGB")
    x0, y0, x1, y1 = rect
    return [image.getpixel((x, y)) for x in range(x0, x1) for y in range(y0, y1) if image.getpixel((x, y)) != (255, 255, 255)]


def test_export_sans_annotation_garde_le_rapport(rapport):
    client, _ = rapport
    r = client.get(URL_EXPORT)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert "dube-alice_lab-3_annote.pdf" in r.headers["content-disposition"]
    assert "mesure" in PdfReader(io.BytesIO(r.content)).pages[0].extract_text()


def test_export_dessine_les_traits_sans_toucher_au_rapport(rapport):
    client, dossier = rapport
    avant = (dossier / "rapport.pdf").read_bytes()
    client.put(URL, json={"version": 1, "pages": {"1": [TRAIT, SURLIGNEUR]}})
    r = client.get(URL_EXPORT)
    assert (dossier / "rapport.pdf").read_bytes() == avant
    rouge = pixels_colores(r.content, (8, 18, 20, 40))      # trait rouge, y du haut
    assert rouge and all(R > 150 and G < 120 for R, G, _ in rouge)
    jaune = pixels_colores(r.content, (150, 290, 250, 310))  # surligneur jaune
    assert jaune and all(R > 200 and G > 200 and 150 < B < 230 for R, G, B in jaune)  # translucide, pas jaune plein
    assert "mesure" in PdfReader(io.BytesIO(r.content)).pages[0].extract_text()  # texte intact


def faire_francais(dossier, decisions, masquees=(), decalages=None):
    zone = {"page": 1, "x0": 72, "y0": 90, "x1": 140, "y1": 102}
    (dossier / "francais.json").write_text(json.dumps({
        "version": 1,
        "fautes": [{"id": 0, "debut": 0, "fin": 6, "texte": "mesure", "message": "", "regle": "", "categorie": "",
                    "suggestions": ["mesurent"], "zones": [zone]}],
        "decisions": decisions, "choix": {}, "masquees": list(masquees), "decalages": decalages or {}}), encoding="utf-8")


def test_seules_les_fautes_acceptees_sont_exportees(rapport):
    client, dossier = rapport
    zone_faute = (75, 91, 138, 101)
    faire_francais(dossier, {})  # à trancher
    assert not pixels_colores(client.get(URL_EXPORT).content, zone_faute)
    faire_francais(dossier, {"0": "refusee"})
    assert not pixels_colores(client.get(URL_EXPORT).content, zone_faute)
    faire_francais(dossier, {"0": "acceptee"})
    assert pixels_colores(client.get(URL_EXPORT).content, zone_faute)


def test_correction_manuscrite_effacee(rapport):
    client, dossier = rapport
    au_dessus = (72, 78, 140, 90)  # là où s'écrit la correction
    faire_francais(dossier, {"0": "acceptee"})
    assert pixels_colores(client.get(URL_EXPORT).content, au_dessus)
    faire_francais(dossier, {"0": "acceptee"}, masquees=[0])
    assert not pixels_colores(client.get(URL_EXPORT).content, au_dessus)


def test_correction_deplacee_dans_le_pdf_exporte(rapport):
    client, dossier = rapport
    origine, deplacee = (72, 78, 140, 90), (72, 138, 140, 150)  # décalage de 60 points vers le bas
    faire_francais(dossier, {"0": "acceptee"})
    assert pixels_colores(client.get(URL_EXPORT).content, origine)
    faire_francais(dossier, {"0": "acceptee"}, decalages={"0": [0, 60]})
    contenu = client.get(URL_EXPORT).content
    assert not pixels_colores(contenu, origine) and pixels_colores(contenu, deplacee)
    assert pixels_colores(contenu, (75, 91, 138, 101))  # le surlignage ne bouge pas


def test_corrections_manuscrites_sur_toutes_les_pages(rapport):
    client, dossier = rapport
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    for n in (1, 2, 3):
        c.drawString(72, 700, f"Page {n} : les etudiants mesure la tension.")
        c.showPage()
    c.save()
    (dossier / "rapport.pdf").write_bytes(tampon.getvalue())
    fautes = [{"id": n - 1, "debut": 0, "fin": 6, "texte": "mesure", "message": "", "regle": "", "categorie": "",
               "suggestions": ["mesurent"], "zones": [{"page": n, "x0": 72, "y0": 90, "x1": 140, "y1": 102}]} for n in (1, 2, 3)]
    (dossier / "francais.json").write_text(json.dumps({
        "version": 1, "fautes": fautes, "decisions": {"0": "acceptee", "1": "acceptee", "2": "acceptee"},
        "choix": {}, "masquees": []}), encoding="utf-8")
    contenu = client.get(URL_EXPORT).content
    for n in (1, 2, 3):
        assert pixels_colores(contenu, (75, 91, 138, 101), n), f"surlignage absent, page {n}"
        assert pixels_colores(contenu, (72, 78, 140, 90), n), f"correction manuscrite absente, page {n}"


def test_export_rapport_inconnu(rapport):
    client, _ = rapport
    assert client.get("/api/export/202SNURE_A2026/00002/lab-3/personne").status_code == 404


def test_export_apres_une_coupe_de_gomme(rapport):
    """Un trait coupé (original en pierre tombale, deux morceaux) s'exporte avec le trou, comme à l'écran."""
    client, _ = rapport
    base = {"outil": "crayon", "couleur": "#d32f2f", "largeur_min": 2, "largeur_max": 2, "courbe": 1}
    entier = {**base, "id": "a", "points": [[100, 300, 0.5], [300, 300, 0.5]]}
    client.put(URL, json={"revision": 0, "pages": {"1": [entier]}})
    avant = client.get(URL_EXPORT).content
    gauche = {**base, "id": "a1", "points": [[100, 300, 0.5], [180, 300, 0.5]]}
    droite = {**base, "id": "a2", "points": [[220, 300, 0.5], [300, 300, 0.5]]}
    assert client.put(URL, json={"revision": 1, "pages": {"1": [gauche, droite]}, "supprimes": ["a"]}).status_code == 200
    apres = client.get(URL_EXPORT).content
    assert pixels_colores(avant, (190, 295, 210, 305))                    # avant : le trait passe au milieu
    assert not pixels_colores(apres, (190, 295, 210, 305))                # après : trou
    assert pixels_colores(apres, (110, 295, 170, 305)) and pixels_colores(apres, (230, 295, 290, 305))
    assert pixels_colores(avant, (110, 295, 170, 305)) == pixels_colores(apres, (110, 295, 170, 305))  # morceaux identiques à l'original
