"""Tests du plagiat. Textes et étudiants fictifs ; Claude est simulé (aucun appel réel)."""

import io
import time
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur import plagiat
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, Resultat

from test_bibliotheque import NOM_LISTE, xlsx

ENONCE = ("Objectif du laboratoire : mesurer la resistance equivalente d'un circuit en serie "
          "puis en parallele avec un multimetre numerique et comparer aux valeurs theoriques calculees.")
COMMUN = ("nous avons observe que la tension aux bornes de la resistance diminue lorsque la temperature "
          "augmente ce qui confirme la dependance attendue du materiau utilise dans le circuit")
ELEVES = [["Nom", "Prénom"], ["Alpha", "Anne"], ["Beta", "Boris"], ["Gamma", "Gaëlle"], ["Delta", "Denis"]]


def pdf(*paragraphes: str) -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    y = 800
    for para in paragraphes:
        mots, ligne = para.split(), ""
        for m in mots:
            if len(ligne) + len(m) > 80:
                c.drawString(40, y, ligne)
                y -= 14
                ligne = ""
            ligne += m + " "
        c.drawString(40, y, ligne)
        y -= 20
    c.save()
    return tampon.getvalue()


class FileFactice:
    def __init__(self, reponse=None, erreur=None):
        self.reponse, self.erreur, self.prompts = reponse, erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.prompts.append(prompt)
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure=self.reponse))
        return f


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    plagiat._en_cours.clear()
    c = TestClient(creer_app())
    assert c.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, xlsx(ELEVES))}).status_code == 200
    return c


def importer(client, lab, **rapports):
    """rapports : nom de famille -> PDF."""
    r = client.post("/api/bibliotheque/import", data={"cours": "202SNURE", "groupe": "00002", "lab": lab},
                    files=[("fichiers", (f"{n}.pdf", p, "application/pdf")) for n, p in rapports.items()])
    assert r.status_code == 200 and not r.json()["en_attente"], r.json()


def test_paire_copiee_detectee_et_independants_non(client):
    original = "Introduction. " + COMMUN + " Conclusion personnelle de la premiere equipe sur les erreurs de mesure."
    copie = "Resume different. " + COMMUN + " Autre conclusion tres differente ecrite par une autre equipe de labo."
    independant = "Texte entierement different sur les moteurs electriques et les champs magnetiques rotatifs en regime permanent."
    importer(client, "lab-1", Alpha=pdf(original), Beta=pdf(copie), Gamma=pdf(independant))
    r = client.post("/api/plagiat/comparer").json()
    assert r["rapports"] == 3
    assert len(r["paires"]) == 1
    p = r["paires"][0]
    assert {p["a"]["etudiant"], p["b"]["etudiant"]} == {"alpha-anne", "beta-boris"}
    assert p["score"] > 0.5 and p["statut"] == "a_confirmer"
    d = client.get(f"/api/plagiat/paires/{p['cle']}").json()
    assert len(d["passages"]) == 1
    assert "tension aux bornes de la resistance" in d["passages"][0]["texte_a"]
    assert d["passages"][0]["texte_a"] == d["passages"][0]["texte_b"]


def test_un_mot_change_coupe_le_passage_mais_les_deux_morceaux_restent(client):
    a = pdf("zero un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze")
    b = pdf("zero un deux trois quatre cinq six sept huit neuf XXX onze douze treize quatorze quinze seize")
    importer(client, "lab-1", Alpha=a, Beta=b)
    p = client.post("/api/plagiat/comparer").json()["paires"][0]
    d = client.get(f"/api/plagiat/paires/{p['cle']}").json()
    assert [x["mots"] for x in d["passages"]] == [10]  # le morceau de 5 mots après le mot changé est trop court


def test_enonce_ignore(client):
    a = pdf(ENONCE + " Mes resultats personnels sont presentes dans le tableau un ci joint.")
    b = pdf(ENONCE + " Voici ce que mon equipe a obtenu pendant la seance de mercredi apres midi.")
    importer(client, "lab-1", Alpha=a, Beta=b)
    assert len(client.post("/api/plagiat/comparer").json()["paires"]) == 1
    r = client.post("/api/plagiat/enonces/202SNURE/lab-1", files={"pdf": ("e.pdf", pdf(ENONCE), "application/pdf")})
    assert r.status_code == 200
    assert client.get("/api/plagiat/enonces").json() == [{"cours": "202SNURE", "lab": "lab-1"}]
    assert client.post("/api/plagiat/comparer").json()["paires"] == []


def test_meme_etudiant_et_labs_differents(client):
    texte = pdf(COMMUN)
    importer(client, "lab-1", Alpha=texte, Delta=pdf("autre sujet sans rapport avec les resistances ni aucun autre texte ici"))
    importer(client, "lab-2", Alpha=texte)  # même étudiant : ignoré
    assert client.post("/api/plagiat/comparer").json()["paires"] == []
    importer(client, "lab-2", Beta=texte)   # autre étudiant, ancien lab : repéré
    p = client.post("/api/plagiat/comparer").json()["paires"]
    # Beta est comparé aux deux copies d'Alpha, mais Alpha n'est jamais comparé à lui-même.
    assert len(p) == 2 and all("beta-boris" in (x["a"]["etudiant"], x["b"]["etudiant"]) for x in p)


def test_seuil_reglable(client):
    importer(client, "lab-1",
             Alpha=pdf(COMMUN + " fin une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize dixsept dixhuit dixneuf vingt"),
             Beta=pdf(COMMUN + " autre fin tout a fait differente puisque ecrite separement par un autre etudiant ensuite apres"))
    p = client.post("/api/plagiat/comparer").json()["paires"][0]
    assert p["statut"] == "a_confirmer"
    client.put("/api/plagiat/reglages", json={"seuil": 0.99})
    assert client.get("/api/plagiat/paires").json()["paires"][0]["statut"] == "sous_seuil"
    assert client.put("/api/plagiat/reglages", json={"seuil": 2}).status_code == 422


def _paire_copiee(client):
    importer(client, "lab-1", Alpha=pdf(COMMUN + " fin A"), Beta=pdf(COMMUN + " fin B"))
    return client.post("/api/plagiat/comparer").json()["paires"][0]["cle"]


def attendre(client, cle, statut):
    for _ in range(50):
        p = next(x for x in client.get("/api/plagiat/paires").json()["paires"] if x["cle"] == cle)
        if p["statut"] == statut:
            return p
        time.sleep(0.05)
    raise AssertionError(p["statut"])


def test_rien_envoye_sans_confirmation_puis_verdict(client, monkeypatch):
    file = FileFactice({"verdict": "copie", "confiance": "elevee", "explication": "Texte identique."})
    monkeypatch.setattr(plagiat, "file_claude", lambda: file)
    cle = _paire_copiee(client)
    assert file.prompts == []  # la comparaison seule n'appelle jamais Claude
    assert client.post(f"/api/plagiat/paires/{cle}/confirmer").json()["statut"] == "en_cours"
    p = attendre(client, cle, "analysee")
    assert p["resultat"]["verdict"] == "copie" and p["resultat"]["explication"] == "Texte identique."
    assert len(file.prompts) == 1
    # Ni noms d'étudiants ni identifiants dans ce qui part chez Claude.
    for mot in ("Alpha", "Beta", "Anne", "alpha-anne", "202SNURE"):
        assert mot not in file.prompts[0]
    assert "tension aux bornes" in file.prompts[0]


def test_erreur_claude_gardee_et_nouvelle_tentative(client, monkeypatch):
    monkeypatch.setattr(plagiat, "file_claude", lambda: FileFactice(erreur=ClaudeLimite("Limite atteinte")))
    cle = _paire_copiee(client)
    client.post(f"/api/plagiat/paires/{cle}/confirmer")
    p = attendre(client, cle, "erreur")
    assert "Limite atteinte" in p["resultat"]["erreur"]
    monkeypatch.setattr(plagiat, "file_claude", lambda: FileFactice({"verdict": "coincidence", "confiance": "faible", "explication": "x"}))
    client.post(f"/api/plagiat/paires/{cle}/confirmer")
    assert attendre(client, cle, "analysee")["resultat"]["verdict"] == "coincidence"


def test_ecarter_et_paire_inconnue(client, monkeypatch):
    file = FileFactice({"verdict": "copie", "confiance": "elevee", "explication": "x"})
    monkeypatch.setattr(plagiat, "file_claude", lambda: file)
    cle = _paire_copiee(client)
    client.post(f"/api/plagiat/paires/{cle}/ecarter")
    assert client.get("/api/plagiat/paires").json()["paires"][0]["statut"] == "ecartee"
    assert client.post("/api/plagiat/paires/inconnue/confirmer").status_code == 404
    assert file.prompts == []
