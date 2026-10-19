"""Tests des indices d'IA. Données fictives ; Claude est simulé (aucun appel réel)."""

from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from moteur import indices_ia
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, ClaudeNonConnecte, Resultat
from tests.test_bibliotheque import NOM_LISTE, ELEVES, pdf, xlsx

class FileFausse:
    def __init__(self, structure=None, erreur=None):
        self.structure, self.erreur, self.appels = structure, erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.appels.append((prompt, schema, systeme))
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure=self.structure, usage={"output_tokens": 7}, cout_usd=0.02))
        return f


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    c = TestClient(creer_app())
    c.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, xlsx(ELEVES))})
    d = c.post("/api/bibliotheque/import", data={"cours": "202SNURE", "groupe": "00002", "lab": "lab3"},
               files=[("fichiers", ("Dubé_lab3.pdf", pdf("Il est important de noter que la tension est stable."),
                                    "application/pdf"))]).json()
    assert d["ranges"], d
    return c


def test_texte(client):
    r = client.get(f"/api/indices-ia/texte/202SNURE/00002/lab3/{_id(client)}")
    assert r.status_code == 200 and "tension est stable" in r.json()["texte"]


def _id(client):
    return next(e["id"] for e in client.get("/api/bibliotheque").json()[0]["etudiants"] if e["labs"])


def test_analyse_enregistree_et_extraits_verifies(client, monkeypatch):
    fausse = FileFausse({
        "force": "moderee", "resume": "Ton uniforme.",
        "signaux": [{"observation": "Formule générique", "extrait": "Il est important de noter"},
                    {"observation": "Inventé", "extrait": "phrase absente du rapport"}],
        "contre_indices": ["Aucun"],
    })
    monkeypatch.setattr(indices_ia, "obtenir_file", lambda: fausse)
    base = f"202SNURE/00002/lab3/{_id(client)}"
    assert client.get(f"/api/indices-ia/resultat/{base}").json() is None
    r = client.post(f"/api/indices-ia/analyser/{base}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["force"] == "moderee" and "verdict" in d["avertissement"]
    assert [s["verifie"] for s in d["signaux"]] == [True, False]
    assert "<rapport>" in fausse.appels[0][0] and fausse.appels[0][1] is indices_ia.SCHEMA
    assert client.get(f"/api/indices-ia/resultat/{base}").json()["resume"] == "Ton uniforme."


@pytest.mark.parametrize("erreur,code", [(ClaudeNonConnecte("non connecté"), 503), (ClaudeLimite("limit reached"), 429)])
def test_erreurs_claude(client, monkeypatch, erreur, code):
    monkeypatch.setattr(indices_ia, "obtenir_file", lambda: FileFausse(erreur=erreur))
    r = client.post(f"/api/indices-ia/analyser/202SNURE/00002/lab3/{_id(client)}")
    assert r.status_code == code and r.json()["detail"]


def test_force_inconnue_ramenee_a_faible(client, monkeypatch):
    monkeypatch.setattr(indices_ia, "obtenir_file",
                        lambda: FileFausse({"force": "certain", "resume": "x", "signaux": [], "contre_indices": []}))
    r = client.post(f"/api/indices-ia/analyser/202SNURE/00002/lab3/{_id(client)}")
    assert r.json()["force"] == "faible"


def test_rapport_introuvable(client):
    assert client.get("/api/indices-ia/texte/202SNURE/00002/lab3/inconnu").status_code == 404
    assert client.get("/api/indices-ia/texte/202SNURE/00002/..%2Fx/inconnu").status_code in (400, 404, 422)
