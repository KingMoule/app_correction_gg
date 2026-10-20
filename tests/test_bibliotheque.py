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


# --- DA, noms composés, multi-groupes, coéquipiers (données fictives) ---------

def liste_csv(lignes, groupe):
    texte = "No de DA;Nom de l'étudiant;Prénom de l'étudiant\r\n" + "\r\n".join(
        f'="{da}";="{nom}";="{prenom}"' for da, nom, prenom in lignes)
    return (f"ListeEtudiants_cours202SNURE_gr{groupe}.csv", texte.encode("cp1252"))


def deux_groupes(client):
    for groupe, lignes in [
        ("00001", [("1000001", "Bele-Gombos", "Anna"), ("1000002", "Martin", "Luc")]),
        ("00002", [("2000001", "Dubé", "Alice"), ("2000002", "Martin", "Zoé")]),
    ]:
        nom, contenu = liste_csv(lignes, groupe)
        assert client.post("/api/bibliotheque/classes", files={"fichier": (nom, contenu)}).status_code == 200


def importer_cours(client, noms_pdf, groupe=""):
    return client.post(
        "/api/bibliotheque/import",
        data={"cours": "202SNURE", "groupe": groupe, "lab": "Lab 1"},
        files=[("fichiers", (n, c, "application/pdf")) for n, c in noms_pdf],
    ).json()


def test_candidats_nom_compose_sans_separateurs():
    from moteur.bibliotheque import candidats
    el = [{"id": "a", "nom": "Bele-Gombos", "prenom": "Anna"}, {"id": "b", "nom": "Roy", "prenom": "X"}]
    assert [e["id"] for e in candidats("BeleGombos_2576245_Rapport.pdf", el)] == ["a"]
    assert [e["id"] for e in candidats("Bele-Gombos_Rapport.pdf", el)] == ["a"]
    assert candidats("Royer_Rapport.pdf", el) == []  # « roy » ne se colle pas dans « royer »


def test_da_prioritaire_sur_le_nom():
    from moteur.bibliotheque import extraire_da, associer
    assert extraire_da("fictif_2626310_Rapport_partiel_1_-__Remis_le_2026-09-18_17h43m16s.pdf") == "2626310"
    el = [{"id": "a", "nom": "Martin", "prenom": "Luc", "da": "1000002"},
          {"id": "b", "nom": "Martin", "prenom": "Zoé", "da": "2000002"}]
    trouves, da = associer("Martin_2000002_Rapport.pdf", el)
    assert [e["id"] for e in trouves] == ["b"] and da == "2000002"
    trouves, _ = associer("Martin_9999999_Rapport.pdf", el)  # DA inconnu : repli sur le nom (ambigu)
    assert len(trouves) == 2


def test_import_multigroupes_et_recap(client, tmp_path):
    deux_groupes(client)
    res = importer_cours(client, [
        ("BeleGombos_1000001_Rapport.pdf", pdf()),
        ("Dube_2000001_Rapport.pdf", pdf()),
        ("Martin_2000002_Rapport.pdf", pdf()),
        ("Martin_Rapport.pdf", pdf()),          # homonymes, sans DA : ambigu
        ("Inconnu_3333333_Rapport.pdf", pdf()),  # DA inconnu, nom inconnu
        ("scan.pdf", pdf(None)),
    ])
    assert res["par_groupe"] == {"00001": 1, "00002": 2}
    assert {a["raison"] for a in res["en_attente"]} == {"ambigu", "da_inconnu"}
    assert len(res["refuses"]) == 1
    assert (tmp_path / "bibliotheque/202SNURE/00001/lab-1/bele-gombos-anna/rapport.pdf").is_file()
    assert (tmp_path / "bibliotheque/202SNURE/00002/lab-1/martin-zoe/rapport.pdf").is_file()
    ambigu = next(a for a in res["en_attente"] if a["raison"] == "ambigu")
    r = client.post(f"/api/bibliotheque/attente/{ambigu['id']}", json={"etudiant": "martin-luc", "groupe": "00001"})
    assert r.status_code == 200
    assert (tmp_path / "bibliotheque/202SNURE/00001/lab-1/martin-luc/rapport.pdf").is_file()


def test_groupe_restreint_limite_la_recherche(client):
    deux_groupes(client)
    res = importer_cours(client, [("Dube_2000001_Rapport.pdf", pdf())], groupe="00001")
    assert not res["ranges"] and res["en_attente"][0]["raison"] == "da_inconnu"


def test_coequipiers_reperes_et_plagiat_ignore(client):
    deux_groupes(client)
    page = "Rapport de lab\nPar Alice Dubé et Anna Bele-Gombos"
    res = importer_cours(client, [("Dube_2000001_Rapport.pdf", pdf(page))])
    equipe = res["ranges"][0]["equipe"]
    assert [(c["groupe"], c["id"]) for c in equipe] == [("00001", "bele-gombos-anna")]
    assert client.get("/api/bibliotheque").json()[1]["etudiants"][0]["equipes"]["lab-1"][0]["id"] == "bele-gombos-anna"
    from moteur.plagiat import _meme_etudiant
    x = {"cours": "C", "groupe": "00002", "etudiant": "dube-alice", "lab": "l", "equipe": ["00001/bele-gombos-anna"]}
    y = {"cours": "C", "groupe": "00001", "etudiant": "bele-gombos-anna", "lab": "l"}
    assert _meme_etudiant(x, y) and _meme_etudiant(y, x)


def test_ecarter_ne_supprime_pas(client, tmp_path):
    charger_classe(client)
    attente = importer(client, [("Inconnu.pdf", pdf())])["en_attente"][0]
    assert client.post(f"/api/bibliotheque/attente/{attente['id']}", json={}).status_code == 200
    assert client.get("/api/bibliotheque/attente").json() == []
    assert (tmp_path / "bibliotheque/_ecartes" / f"{attente['id']}.pdf").is_file()


def test_statut_termine_et_archive(client):
    charger_classe(client)
    importer(client, [("Dube_Rapport.pdf", pdf("Dube Alice"))])
    arbre = client.get("/api/bibliotheque").json()[0]
    alice = next(e for e in arbre["etudiants"] if e["nom"] == "Dubé")
    assert alice["labs"] == ["lab-3"] and alice["termines"] == [] and arbre["labs_archives"] == []

    base = f"/api/bibliotheque/statut/202SNURE/00002/lab-3/{alice['id']}"
    assert client.put(base, json={"termine": True}).json() == {"termine": True}
    arbre = client.get("/api/bibliotheque").json()[0]
    assert next(e for e in arbre["etudiants"] if e["nom"] == "Dubé")["termines"] == ["lab-3"]
    client.put(base, json={"termine": False})
    assert next(e for e in client.get("/api/bibliotheque").json()[0]["etudiants"] if e["nom"] == "Dubé")["termines"] == []

    assert client.put("/api/bibliotheque/statut/202SNURE/00002/lab-9/abc", json={"termine": True}).status_code == 404
    assert client.put("/api/bibliotheque/archive/202SNURE/00002/lab-3", json={"archive": True}).status_code == 200
    assert client.get("/api/bibliotheque").json()[0]["labs_archives"] == ["lab-3"]
    client.put("/api/bibliotheque/archive/202SNURE/00002/lab-3", json={"archive": False})
    assert client.get("/api/bibliotheque").json()[0]["labs_archives"] == []
    assert client.put("/api/bibliotheque/archive/202SNURE/00002/lab-9", json={"archive": True}).status_code == 404
