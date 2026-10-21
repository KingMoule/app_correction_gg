"""Contenu EXACT de ce qui part à Claude (français, indices d'IA, plagiat). Claude est simulé.

Classe fictive sur deux groupes d'un même cours : aucun nom, prénom ni DA ne doit sortir.
"""

import json
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from moteur import francais_claude, indices_ia, plagiat
from moteur.anonymat import Anonymiseur
from moteur.app import creer_app
from moteur.claude import Resultat
from tests.test_anonymat import COURS, GROUPE1, GROUPE2
from tests.test_bibliotheque import pdf

TOUS = ["Bouchard", "Simon", "Wu", "Li", "Roy", "Zoé", "Dubé", "Alice", "Tremblay", "Côté", "Jean", "François",
        "Lévesque", "Léa", "Fortin", "Éloïse", "1000001", "2000001", "2000002"]
# Page titre d'Alice (groupe 00002) : coéquipiers d'un autre groupe, nom court, nom composé, DA.
TITRE = ("Rapport de Alice Dubé DA 2000001 avec Simon Bouchard, Roy et Tremblay-Côté Jean-François "
         "et Wu Li ; Fortin Éloïse aussi.")
TITRE_MASQUE = ("Rapport de [PRÉNOM] [NOM] DA [DA] avec [PRÉNOM] [NOM], [NOM] et [NOM]-[NOM] [PRÉNOM]-[PRÉNOM] "
                "et [NOM] [PRÉNOM] ; [NOM] [PRÉNOM] aussi.")


class FileFausse:
    def __init__(self, structure):
        self.structure, self.appels = structure, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.appels.append(prompt)
        f = Future()
        f.set_result(Resultat(texte="", structure=self.structure, usage={}, cout_usd=0.0))
        return f


def sans_noms(prompt):
    for mot in TOUS:
        assert mot not in prompt, mot


@pytest.fixture
def donnees(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    racine = tmp_path / "bibliotheque" / COURS
    for groupe, etudiants in (("00001", GROUPE1), ("00002", GROUPE2)):
        (racine / groupe).mkdir(parents=True)
        (racine / groupe / "classe.json").write_text(
            json.dumps({"cours": COURS, "groupe": groupe, "etudiants": etudiants}), encoding="utf-8")
    d = racine / "00002" / "lab1" / "dube-alice"
    d.mkdir(parents=True)
    (d / "equipe.json").write_text(json.dumps([{"id": "fortin-eloise", "groupe": "00003",
                                                "nom": "Fortin", "prenom": "Éloïse"}]), encoding="utf-8")
    (d / "rapport.pdf").write_bytes(pdf(TITRE))
    return TestClient(creer_app())


def test_indices_ia_prompt_exact(donnees, monkeypatch):
    fausse = FileFausse({"force": "faible", "resume": "x", "signaux": [], "contre_indices": []})
    monkeypatch.setattr(indices_ia, "obtenir_file", lambda: fausse)
    r = donnees.post(f"/api/indices-ia/analyser/{COURS}/00002/lab1/dube-alice")
    assert r.status_code == 200, r.text
    assert fausse.appels == [f"<rapport>\n{TITRE_MASQUE}\n</rapport>\n\nAnalyse le style de ce rapport."]
    sans_noms(fausse.appels[0])


def test_francais_prompt_exact(donnees, monkeypatch):
    fausse = FileFausse({"fautes": []})
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: fausse)
    texte = TITRE + " Les mesures est correctes. Le roy a la tension."
    existantes = [{"debut": 0, "fin": 6, "texte": "Alice Dubé"}]
    francais_claude.passe(texte, existantes, Anonymiseur.pour(COURS))
    attendu = (f"<rapport>\n{TITRE_MASQUE} Les mesures est correctes. Le roy a la tension.\n</rapport>\n\n"
               "<deja_signalees>\n- « [PRÉNOM] [NOM] »\n</deja_signalees>\n\n"
               "Repère les erreurs de français que le correcteur automatique a manquées.")
    assert fausse.appels == [attendu]
    sans_noms(fausse.appels[0])


def test_francais_positions_en_texte_original(donnees, monkeypatch):
    """Claude voit le texte masqué mais ses extraits sont replacés dans le texte original."""
    texte = TITRE + " Les mesures est correctes. Alice Dubé a tension."
    fausse = FileFausse({"fautes": [
        {"extrait": "mesures est", "correction": "mesures sont", "message": "Accord"},
        {"extrait": "[NOM] [PRÉNOM] aussi", "correction": "x", "message": "m"},  # contient un masque : écartée
    ]})
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: fausse)
    fautes, erreur = francais_claude.passe(texte, [], Anonymiseur.pour(COURS))
    assert erreur is None and len(fautes) == 1
    f = fautes[0]
    assert texte[f["debut"]:f["fin"]] == "mesures est" == f["texte"]
    assert f["debut"] == texte.index("mesures est") > len(TITRE_MASQUE) - 40
    # le masque raccourcit le texte : sans replacement dans l'original, les positions seraient fausses
    assert len(Anonymiseur.pour(COURS).masquer(texte)) != len(texte)


def test_plagiat_prompt_exact(donnees):
    p = {
        "a": {"cours": COURS}, "b": {"cours": COURS}, "nb_passages": 2, "couverture_a": 0.5, "couverture_b": 0.25,
        "passages": [
            {"mots": 14, "texte_a": TITRE, "texte_b": "Rapport de Léa Lévesque DA 2000003 matricule 123456789"},
            {"mots": 8, "texte_a": "la tension aux bornes de la résistance diminue",
             "texte_b": "la tension aux bornes de la résistance diminue"},
        ],
    }
    prompt = plagiat.construire_prompt(p)
    attendu = (
        "<passages>\n"
        f"<passage numero=\"1\" mots=\"14\">\n<rapport_a>{TITRE_MASQUE}</rapport_a>\n"
        "<rapport_b>Rapport de [PRÉNOM] [NOM] DA [DA] matricule [DA]</rapport_b>\n</passage>\n"
        "<passage numero=\"2\" mots=\"8\">\n<rapport_a>la tension aux bornes de la résistance diminue</rapport_a>\n"
        "<rapport_b>la tension aux bornes de la résistance diminue</rapport_b>\n</passage>\n"
        "</passages>\n\n"
        "Le programme a trouvé 2 passage(s) commun(s) (50 % du rapport A, 25 % du rapport B), 2 montré(s) "
        "ci-dessus. Les passages de l'énoncé du lab sont déjà retirés. "
        "Les équipes de laboratoire partagent parfois leurs données et mesures. "
        "Donne ton verdict (copie, paraphrase ou coïncidence), ta confiance et une explication courte.")
    assert prompt == attendu
    sans_noms(prompt)


def test_plagiat_cours_different_masque_les_deux_listes(donnees, tmp_path):
    autre = tmp_path / "bibliotheque" / "203AUTRE" / "00001"
    autre.mkdir(parents=True)
    (autre / "classe.json").write_text(json.dumps({"cours": "203AUTRE", "groupe": "00001", "etudiants": [
        {"id": "x", "nom": "Ancien", "prenom": "Pierre", "da": "3000001"}]}), encoding="utf-8")
    p = {"a": {"cours": COURS}, "b": {"cours": "203AUTRE"}, "nb_passages": 1, "couverture_a": 0.1,
         "couverture_b": 0.1, "passages": [{"mots": 9, "texte_a": "Alice Dubé", "texte_b": "Pierre Ancien 3000001"}]}
    prompt = plagiat.construire_prompt(p)
    assert "<rapport_a>[PRÉNOM] [NOM]</rapport_a>\n<rapport_b>[PRÉNOM] [NOM] [DA]</rapport_b>" in prompt
