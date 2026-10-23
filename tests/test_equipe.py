"""Coéquipiers (audit M1) : détection stricte sur la page titre, équipe modifiable à la main.

Toutes les pages titres sont fictives."""
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur.app import creer_app
from moteur.bibliotheque import coequipiers
from moteur.plagiat import _meme_etudiant

COURS = "202SNURE"
ETUDIANTS = [
    {"id": "dube-alice", "groupe": "00002", "nom": "Dubé", "prenom": "Alice"},
    {"id": "roy-marie", "groupe": "00002", "nom": "Roy", "prenom": "Marie"},
    {"id": "bele-gombos-anna", "groupe": "00001", "nom": "Bele-Gombos", "prenom": "Anna"},
    {"id": "tremblay-roy-paul", "groupe": "00001", "nom": "Tremblay-Roy", "prenom": "Paul"},
    {"id": "martin-luc", "groupe": "00001", "nom": "Martin", "prenom": "Luc"},
]
DEPOSANT = ETUDIANTS[0]


def pdf(lignes: list[str]) -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    y = 780
    for ligne in lignes:
        c.drawString(72, y, ligne)
        y -= 20
    c.save()
    return tampon.getvalue()


def ids(contenu: bytes) -> list[str]:
    return [e["id"] for e in coequipiers(contenu, ETUDIANTS, DEPOSANT)]


def test_vraie_equipe_detectee_prenom_nom_et_nom_prenom():
    assert ids(pdf(["Rapport de laboratoire 3", "Par Alice Dubé et Anna Bele-Gombos"])) == ["bele-gombos-anna"]
    assert ids(pdf(["Rapport", "Présenté par : DUBÉ Alice, TREMBLAY-ROY Paul"])) == ["tremblay-roy-paul"]
    assert ids(pdf(["Rapport", "Tremblay-Roy, Paul", "Bele-Gombos, Anna"])) == ["bele-gombos-anna", "tremblay-roy-paul"]


def test_nom_compose_accents_et_majuscules():
    assert ids(pdf(["Équipe : PAUL TREMBLAY ROY"])) == ["tremblay-roy-paul"]
    assert ids(pdf(["Équipe : anna bele gombos"])) == ["bele-gombos-anna"]


def test_enseignant_et_prenom_dans_le_texte_non_retenus():
    page = ["Rapport de lab", "Enseignant : M. Roy", "Introduction", "Marie a observé la réaction.",
            "Nous avons suivi la méthode de Curie."]
    assert ids(pdf(page)) == []


def test_nom_et_prenom_eloignes_non_retenus():
    assert ids(pdf(["Rapport de Marie Curie", "Enseignant : Mme Roy"])) == []
    assert ids(pdf(["Marie", "Roy"])) == []  # deux lignes distinctes


def test_nom_seul_sans_prenom_non_retenu():
    assert ids(pdf(["Remis à Roy", "Par Alice Dubé et Martin"])) == []


def test_nom_cite_hors_de_l_en_tete_non_retenu():
    page = ["Titre"] + [f"Ligne {i} du texte" for i in range(20)] + ["Mesures de Marie Roy"]
    assert ids(pdf(page)) == []


def test_ligne_d_enseignant_ignoree_meme_avec_nom_et_prenom():
    assert ids(pdf(["Rapport", "Enseignant : Marie Roy"])) == []


# --- Modification manuelle ----------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    c = TestClient(creer_app())
    for groupe, lignes in [("00001", [("1000001", "Bele-Gombos", "Anna"), ("1000002", "Martin", "Luc")]),
                           ("00002", [("2000001", "Dubé", "Alice"), ("2000002", "Roy", "Marie")])]:
        texte = "No de DA;Nom de l'étudiant;Prénom de l'étudiant\r\n" + "\r\n".join(
            f'="{da}";="{n}";="{p}"' for da, n, p in lignes)
        r = c.post("/api/bibliotheque/classes", files={"fichier": (f"ListeEtudiants_cours{COURS}_gr{groupe}.csv", texte.encode("cp1252"))})
        assert r.status_code == 200, r.text
    return c


def deposer(client, page):
    res = client.post("/api/bibliotheque/import", data={"cours": COURS, "groupe": "", "lab": "Lab 1"},
                      files=[("fichiers", ("Dube_2000001_Rapport.pdf", pdf(page), "application/pdf"))]).json()
    assert len(res["ranges"]) == 1, res
    return res


def url_equipe():
    return f"/api/bibliotheque/equipe/{COURS}/00002/lab-1/dube-alice"


def test_import_ne_retient_pas_l_enseignant_homonyme(client):
    res = deposer(client, ["Rapport de lab", "Enseignant : M. Roy", "Introduction", "Marie Curie a décrit la loi."])
    assert res["ranges"][0]["equipe"] == []
    assert res["cours"] == COURS and res["lab"] == "lab-1"


def test_modifier_l_equipe_ajout_retrait_et_validation(client, tmp_path):
    deposer(client, ["Rapport", "Par Alice Dubé"])
    r = client.put(url_equipe(), json={"equipe": [{"groupe": "00001", "id": "bele-gombos-anna"},
                                                   {"groupe": "00001", "id": "bele-gombos-anna"},
                                                   {"groupe": "00002", "id": "dube-alice"}]})
    assert r.status_code == 200
    assert [m["id"] for m in r.json()["equipe"]] == ["bele-gombos-anna"]  # doublon et déposant écartés
    fichier = tmp_path / "bibliotheque" / COURS / "00002" / "lab-1" / "dube-alice" / "equipe.json"
    assert fichier.is_file()
    assert client.get("/api/bibliotheque").json()[1]["etudiants"][0]["equipes"]["lab-1"][0]["prenom"] == "Anna"
    assert client.put(url_equipe(), json={"equipe": [{"groupe": "00001", "id": "inconnu"}]}).status_code == 400
    assert client.put(f"/api/bibliotheque/equipe/{COURS}/00002/lab-1/roy-marie", json={"equipe": []}).status_code == 404
    assert client.put(url_equipe(), json={"equipe": []}).json() == {"equipe": []}
    assert not fichier.exists()


def test_equipe_modifiee_prise_en_compte_par_suivi_export_et_plagiat(client):
    deposer(client, ["Rapport", "Par Alice Dubé"])
    assert client.get(f"/api/suivi/{COURS}/lab-1").json()["rapports"][0]["equipe"] == []
    client.put(url_equipe(), json={"equipe": [{"groupe": "00001", "id": "bele-gombos-anna"}]})
    rapport = client.get(f"/api/suivi/{COURS}/lab-1").json()["rapports"][0]
    assert rapport["equipe"] == ["Anna Bele-Gombos"]
    tableau = client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content.decode("utf-8-sig")
    assert ";Bele-Gombos;Anna;00001;" in tableau  # une ligne par coéquipier
    x = {"cours": COURS, "groupe": "00002", "etudiant": "dube-alice", "lab": "lab-1", "equipe": ["00001/bele-gombos-anna"]}
    y = {"cours": COURS, "groupe": "00001", "etudiant": "bele-gombos-anna", "lab": "lab-1"}
    assert _meme_etudiant(x, y) and _meme_etudiant(y, x)
    client.put(url_equipe(), json={"equipe": []})
    assert ";Bele-Gombos;Anna;00001;équipe" not in client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content.decode("utf-8-sig")
