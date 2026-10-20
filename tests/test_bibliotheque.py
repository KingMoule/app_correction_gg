"""Tests de la bibliothèque. Données fictives seulement (aucun vrai étudiant)."""

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from moteur.app import creer_app

NOM_LISTE = "ListeEtudiants_cours202SNURE_gr00002.xlsx"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    return TestClient(creer_app())


def xlsx(lignes) -> bytes:
    wb = Workbook()
    for ligne in lignes:
        wb.active.append(ligne)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def pdf(texte: str | None = "Rapport de lab") -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    if texte:
        c.drawString(72, 700, texte)
    c.save()
    return tampon.getvalue()


ELEVES = [
    ["Liste de classe"],
    ["Nom", "Prénom"],
    ["Dubé", "Alice"],
    ["Gagnon", "Marc"],
    ["Gagnon", "Julie"],
    ["Roy", "Léa"],
    ["Tremblay-Roy", "Paul"],
]


def charger_classe(client):
    r = client.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, xlsx(ELEVES))})
    assert r.status_code == 200, r.text
    return r.json()


def importer(client, noms_pdf, lab="Lab 3"):
    return client.post(
        "/api/bibliotheque/import",
        data={"cours": "202SNURE", "groupe": "00002", "lab": lab},
        files=[("fichiers", (n, c, "application/pdf")) for n, c in noms_pdf],
    ).json()


def test_liste_de_classe(client):
    classe = charger_classe(client)
    assert (classe["cours"], classe["groupe"]) == ("202SNURE", "00002")
    assert [e["id"] for e in classe["etudiants"]] == [
        "dube-alice", "gagnon-marc", "gagnon-julie", "roy-lea", "tremblay-roy-paul"]


def test_nom_de_fichier_invalide(client):
    r = client.post("/api/bibliotheque/classes", files={"fichier": ("autre.xlsx", xlsx(ELEVES))})
    assert r.status_code == 400


def test_liste_csv(client):
    csv = "Nom;Prénom\nDubé;Alice\n".encode("latin-1")
    r = client.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE.replace("xlsx", "csv"), csv)})
    assert r.json()["etudiants"][0]["id"] == "dube-alice"


def test_liste_omnivox_cp1252(client):
    """Format réel d'Omnivox/LÉA : cp1252, « ; », valeurs `="..."`, colonnes vides. Noms fictifs."""
    lignes = [
        "No de DA;Nom de l'étudiant;Prénom de l'étudiant;      ;      ;",
        '="1234567";="Tremblay";="Émilie"; ; ;',
        '="7654321";="Gagnon-Côté";="Jean Philippe"; ; ;',
        '="1111111";="De La Fontaine";="Raphaël"; ; ;',
        " ; ; ; ; ;",
    ]
    texte = "\r\n".join(lignes) + "\r\n"
    contenu = texte.encode("cp1252")
    with pytest.raises(UnicodeDecodeError):
        contenu.decode("utf-8")
    r = client.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE.replace("xlsx", "csv"), contenu)})
    assert r.status_code == 200, r.text
    assert r.json()["etudiants"] == [
        {"id": "tremblay-emilie", "nom": "Tremblay", "prenom": "Émilie", "da": "1234567"},
        {"id": "gagnon-cote-jean-philippe", "nom": "Gagnon-Côté", "prenom": "Jean Philippe", "da": "7654321"},
        {"id": "de-la-fontaine-raphael", "nom": "De La Fontaine", "prenom": "Raphaël", "da": "1111111"},
    ]


def test_liste_xlsx_enrobage_et_da(client):
    wb = Workbook()
    wb.active.append(["No de DA", "Nom de l'étudiant", "Prénom de l'étudiant"])
    wb.active.append(['="1234567"', '="Dubé"', '="Alice"'])
    for cellule in wb.active[2]:
        cellule.data_type = "s"  # texte (et non formule), comme la valeur calculée d'Excel
    tampon = io.BytesIO()
    wb.save(tampon)
    r = client.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, tampon.getvalue())})
    assert r.json()["etudiants"] == [{"id": "dube-alice", "nom": "Dubé", "prenom": "Alice", "da": "1234567"}]


def test_association_automatique_et_rangement(client, tmp_path):
    charger_classe(client)
    res = importer(client, [("Rapport_DUBE_lab3.pdf", pdf()), ("tremblay-roy.pdf", pdf())])
    assert [r["etudiant"]["id"] for r in res["ranges"]] == ["dube-alice", "tremblay-roy-paul"]
    assert (tmp_path / "bibliotheque/202SNURE/00002/lab-3/dube-alice/rapport.pdf").is_file()
    arbre = client.get("/api/bibliotheque").json()
    assert arbre[0]["etudiants"][0]["labs"] == ["lab-3"]
    r = client.get("/api/bibliotheque/rapport/202SNURE/00002/lab-3/dube-alice")
    assert r.headers["content-type"] == "application/pdf"


def test_homonymes_departages_par_prenom_sinon_attente(client):
    charger_classe(client)
    res = importer(client, [("Gagnon_Julie.pdf", pdf()), ("Gagnon.pdf", pdf())])
    assert [r["etudiant"]["id"] for r in res["ranges"]] == ["gagnon-julie"]
    assert res["en_attente"][0]["raison"] == "ambigu"
    assert len(res["en_attente"][0]["candidats"]) == 2


def test_sans_correspondance_puis_decision(client, tmp_path):
    charger_classe(client)
    res = importer(client, [("Inconnu.pdf", pdf())])
    attente = res["en_attente"][0]
    assert attente["raison"] == "aucune_correspondance"
    assert client.get("/api/bibliotheque/attente").json()[0]["id"] == attente["id"]
    r = client.post(f"/api/bibliotheque/attente/{attente['id']}", json={"etudiant": "roy-lea"})
    assert r.status_code == 200
    assert (tmp_path / "bibliotheque/202SNURE/00002/lab-3/roy-lea/rapport.pdf").is_file()
    assert client.get("/api/bibliotheque/attente").json() == []


def test_pdf_sans_texte_refuse(client):
    charger_classe(client)
    res = importer(client, [("Dube.pdf", pdf(None)), ("Roy.pdf", b"pas un pdf")])
    assert len(res["refuses"]) == 2 and not res["ranges"]


def test_deja_importe_ne_remplace_pas(client):
    charger_classe(client)
    importer(client, [("Dube.pdf", pdf("v1"))])
    res = importer(client, [("Dube.pdf", pdf("v2"))])
    assert res["en_attente"][0]["raison"] == "deja_importe"


def test_chemin_dangereux_refuse(client):
    r = client.post("/api/bibliotheque/import", data={"cours": "..", "groupe": "x", "lab": "l"},
                    files=[("fichiers", ("a.pdf", pdf(), "application/pdf"))])
    assert r.status_code == 400
