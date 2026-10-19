import httpx
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur import languagetool, pdf_texte
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
        texte = dict(x.split("=", 1) for x in request.content.decode().split("&"))["text"]
        import urllib.parse

        texte = urllib.parse.unquote_plus(texte)
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
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr": _orig(t, client=client_lt))
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


@pytest.fixture
def rapport_range(client, monkeypatch):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf("Les etudiants mesure la tension."))])
    client_lt = lt_factice("mesure", monkeypatch)
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr": _orig(t, client=client_lt))
    return client


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
