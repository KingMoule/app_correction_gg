import json
import urllib.parse
from concurrent.futures import Future

import httpx
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur import francais_claude, languagetool, pdf_texte
from moteur.claude import ClaudeDelai, ClaudeEchec, ClaudeLimite, ClaudeNonConnecte, Resultat
from moteur.app import creer_app
from moteur.bareme import Bareme, penalite

_orig = languagetool.verifier


@pytest.fixture
def pdf_fictif(tmp_path):
    chemin = tmp_path / "rapport.pdf"
    c = canvas.Canvas(str(chemin))
    c.drawString(72, 750, "Les etudiants mesure la tension.")
    c.drawString(72, 730, "Le resultat est correct.")
    c.showPage()
    c.drawString(72, 750, "Deuxieme page.")
    c.save()
    return chemin


def lt_factice(texte_faute, monkeypatch):
    def handler(request):
        champs = urllib.parse.parse_qs(request.content.decode())
        if "data" in champs:
            texte = "".join(p.get("text", p.get("markup", "")) for p in json.loads(champs["data"][0])["annotation"])
        else:
            texte = champs["text"][0]
        d = texte.index(texte_faute)
        return httpx.Response(200, json={"matches": [{
            "offset": d, "length": len(texte_faute), "message": "Accord",
            "rule": {"id": "ACCORD", "category": {"id": "GRAMMAR"}},
            "replacements": [{"value": "mesurent"}],
        }]})
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_extraction_positions(pdf_fictif):
    e = pdf_texte.extraire(pdf_fictif)
    assert "Les etudiants mesure la tension." in e.texte
    assert len(e.pages) == 2
    d = e.texte.index("mesure")
    z = e.zones(d, d + 6)
    assert len(z) == 1 and z[0]["page"] == 1
    assert 72 < z[0]["x0"] < z[0]["x1"] < 595 and z[0]["y0"] < z[0]["y1"]
    # deuxième page
    d2 = e.texte.index("Deuxieme")
    assert e.zones(d2, d2 + 8)[0]["page"] == 2


def test_pdf_sans_texte(tmp_path):
    chemin = tmp_path / "vide.pdf"
    c = canvas.Canvas(str(chemin))
    c.showPage()
    c.save()
    with pytest.raises(pdf_texte.PdfSansTexte):
        pdf_texte.extraire(chemin)


def test_languagetool_decalages(monkeypatch):
    fautes = languagetool.verifier("Ils mesure.", client=lt_factice("mesure", monkeypatch))
    assert fautes[0].texte == "mesure" and fautes[0].suggestions == ["mesurent"]


def test_languagetool_injoignable(monkeypatch):
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://127.0.0.1:9")
    with pytest.raises(languagetool.LanguageToolIndisponible):
        languagetool.verifier("Bonjour")


def test_bareme():
    assert penalite(4, Bareme(points_par_faute=0.5)) == 2.0
    assert penalite(40, Bareme(points_par_faute=0.5, plafond=5)) == 5.0
    assert penalite(0, Bareme()) == 0.0


def test_api_analyser(pdf_fictif, monkeypatch):
    client_lt = lt_factice("mesure", monkeypatch)
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr", client=None, **kw: _orig(t, client=client_lt, **kw))
    c = TestClient(creer_app())
    with open(pdf_fictif, "rb") as f:
        r = c.post("/api/francais/analyser", files={"pdf": ("r.pdf", f, "application/pdf")},
                   data={"points_par_faute": "0.5", "plafond": "1"})
    assert r.status_code == 200
    j = r.json()
    assert j["fautes"][0]["texte"] == "mesure" and j["fautes"][0]["zones"][0]["page"] == 1
    assert j["penalite_si_toutes_acceptees"] == 0.5


def test_api_bareme():
    r = TestClient(creer_app()).post("/api/francais/bareme",
        json={"nb_fautes": 30, "bareme": {"points_par_faute": 1, "plafond": 10}})
    assert r.json()["penalite"] == 10


def test_api_languagetool_absent(pdf_fictif, monkeypatch):
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://127.0.0.1:9")
    with open(pdf_fictif, "rb") as f:
        r = TestClient(creer_app()).post("/api/francais/analyser", files={"pdf": ("r.pdf", f)})
    assert r.status_code == 503



# --- Rapport rangé dans la bibliothèque ---------------------------------------

from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: E402,F401

URL_RAPPORT = "/api/francais/rapport/202SNURE/00002/lab-3/dube-alice"


class FileFausse:
    """Claude simulé : aucun appel réel."""

    def __init__(self, fautes=None, erreur=None):
        self.fautes, self.erreur, self.appels = fautes or [], erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.appels.append(prompt)
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure={"fautes": self.fautes}, usage={}, cout_usd=0.0))
        return f


@pytest.fixture
def rapport_range(client, monkeypatch):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf("Les etudiants mesure la tension. Il a manger hier."))])
    client_lt = lt_factice("mesure", monkeypatch)
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr", client=None, **kw: _orig(t, client=client_lt, **kw))
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse())
    return client


FAUTE_CLAUDE = {"extrait": "a manger", "correction": "a mangé", "message": "Participe passé"}


def test_passe_claude_ajoute_les_fautes_valides(rapport_range, monkeypatch):
    fausse = FileFausse([
        FAUTE_CLAUDE,
        {"extrait": "phrase absente", "correction": "x", "message": "inventée"},   # pas dans le texte
        {"extrait": "mesure", "correction": "mesurent", "message": "doublon LT"},   # chevauche LanguageTool
    ])
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: fausse)
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    assert [f["texte"] for f in j["fautes"]] == ["mesure", "a manger"]
    c = j["fautes"][1]
    assert c["source"] == "claude" and c["suggestions"] == ["a mangé"] and c["zones"] and c["id"] == 1
    assert j["fautes"][0]["source"] == "languagetool"
    assert j["claude"] == {"ok": True, "erreur": None, "ajoutees": 1}
    assert "<rapport>" in fausse.appels[0] and "Dubé" not in fausse.appels[0]
    # mêmes décisions, barème et export que LanguageTool
    j = rapport_range.put(URL_RAPPORT, json={"decisions": {"1": "acceptee"}, "choix": {"1": "a mangé"}}).json()
    assert j["nb_acceptees"] == 1 and j["penalite"] == 0.5


@pytest.mark.parametrize("erreur,code", [(ClaudeNonConnecte("non connecté"), 503), (ClaudeLimite("limit"), 429),
                                         (ClaudeDelai("trop long"), 504), (ClaudeEchec("autre"), 502)])
def test_erreur_claude_garde_languagetool(rapport_range, monkeypatch, erreur, code):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse(erreur=erreur))
    r = rapport_range.post(URL_RAPPORT + "/analyser")
    assert r.status_code == 200
    j = r.json()
    assert [f["texte"] for f in j["fautes"]] == ["mesure"]
    assert j["claude"]["ok"] is False and j["claude"]["erreur"]["code"] == code


def test_nouvelle_analyse_garde_decision_faute_claude(rapport_range, monkeypatch):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    rapport_range.post(URL_RAPPORT + "/analyser")
    rapport_range.put(URL_RAPPORT, json={"decisions": {"1": "refusee"}})
    assert rapport_range.post(URL_RAPPORT + "/analyser").json()["decisions"] == {"1": "refusee"}


def test_rapport_pas_analyse(rapport_range):
    j = rapport_range.get(URL_RAPPORT).json()
    assert j["analyse"] is False and j["penalite"] == 0
    assert rapport_range.put(URL_RAPPORT, json={}).status_code == 409


def test_analyse_decisions_et_bareme_par_cours(rapport_range, tmp_path):
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    assert j["analyse"] and j["fautes"][0]["texte"] == "mesure" and j["nb_acceptees"] == 0
    assert (tmp_path / "bibliotheque/202SNURE/00002/lab-3/dube-alice/francais.json").is_file()
    # barème du cours : 2 points par faute, plafond 1
    r = rapport_range.put("/api/francais/bareme/202SNURE", json={"points_par_faute": 2, "plafond": 1})
    assert r.status_code == 200
    j = rapport_range.put(URL_RAPPORT, json={
        "decisions": {"0": "acceptee"}, "choix": {"0": "mesurent"}, "masquees": [0]}).json()
    assert j["nb_acceptees"] == 1 and j["penalite"] == 1 and j["masquees"] == [0]
    assert rapport_range.get(URL_RAPPORT).json()["choix"] == {"0": "mesurent"}


def test_nouvelle_analyse_garde_les_decisions(rapport_range):
    rapport_range.post(URL_RAPPORT + "/analyser")
    rapport_range.put(URL_RAPPORT, json={"decisions": {"0": "refusee"}})
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    assert j["decisions"] == {"0": "refusee"}


def test_decision_sur_faute_inconnue(rapport_range):
    rapport_range.post(URL_RAPPORT + "/analyser")
    assert rapport_range.put(URL_RAPPORT, json={"decisions": {"9": "acceptee"}}).status_code == 422
    assert rapport_range.put(URL_RAPPORT, json={"decisions": {"0": "peut-etre"}}).status_code == 422


def test_bareme_cours_inconnu(client):
    assert client.get("/api/francais/bareme/999XXXXX").status_code == 404


def test_claude_en_panne_garde_les_fautes_claude_precedentes(rapport_range, monkeypatch):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    rapport_range.post(URL_RAPPORT + "/analyser")
    rapport_range.put(URL_RAPPORT, json={"decisions": {"1": "acceptee"}})
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse(erreur=ClaudeLimite("limit")))
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    assert [f["texte"] for f in j["fautes"]] == ["mesure", "a manger"]
    assert j["decisions"] == {"1": "acceptee"} and j["claude"]["ok"] is False


def test_extrait_de_claude_mots_entiers(rapport_range, monkeypatch):
    # « mesur » est dans « mesure » mais n'est pas un mot entier du rapport
    monkeypatch.setattr(francais_claude, "obtenir_file",
                        lambda: FileFausse([{"extrait": "tensio", "correction": "x", "message": "m"}]))
    assert [f["texte"] for f in rapport_range.post(URL_RAPPORT + "/analyser").json()["fautes"]] == ["mesure"]


def test_noms_d_etudiants_pas_envoyes_a_claude(client, monkeypatch):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf("Alice Dubé et Marc Gagnon ont mesure la tension."))])
    client_lt = lt_factice("mesure", monkeypatch)
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr", client=None, **kw: _orig(t, client=client_lt, **kw))
    fausse = FileFausse()
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: fausse)
    assert client.post(URL_RAPPORT + "/analyser").status_code == 200
    envoye = fausse.appels[0]
    assert "Dub" not in envoye and "Alice" not in envoye and "Gagnon" not in envoye and "[NOM]" in envoye
