"""Tests de l'analyse par lot. Données fictives ; Claude et LanguageTool sont simulés."""

import json
import time
from concurrent.futures import Future

import pytest

from moteur import francais_claude, indices_ia, languagetool, lot
from moteur.claude import ClaudeLimite, ClaudeNonConnecte, Resultat
from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: F401

SORTIE = {"fautes": [], "force": "faible", "resume": "RAS", "signaux": [], "contre_indices": []}
NOMS = ["Rapport_DUBE.pdf", "Rapport_GAGNON_Marc.pdf", "Rapport_GAGNON_Julie.pdf", "Rapport_ROY.pdf"]
LAB = "202SNURE/00002/lab-3"


class FileFausse:
    """Claude simulé : réussit `ok` fois, puis lève `erreur`."""

    def __init__(self, ok=10_000, erreur=None, pause=0.0):
        self.ok, self.erreur, self.appels, self.pause = ok, erreur, 0, pause

    def soumettre(self, prompt, schema=None, systeme=None):
        time.sleep(self.pause)
        self.appels += 1
        f = Future()
        if self.appels > self.ok:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure=SORTIE, usage={}, cout_usd=0.0))
        return f


@pytest.fixture
def labo(client, monkeypatch):
    charger_classe(client)
    d = importer(client, [(n, pdf(f"Texte du rapport {n}.")) for n in NOMS])
    assert len(d["ranges"]) == 4, d
    monkeypatch.setattr(languagetool, "verifier", lambda t, langue="fr", **kw: [])
    lot._etat.clear()
    lot._etat["statut"] = "inactif"
    return client


def brancher(monkeypatch, file):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: file)
    monkeypatch.setattr(indices_ia, "obtenir_file", lambda: file)


def attendre(client):
    for _ in range(300):
        e = client.get("/api/lot").json()
        if e["statut"] != "en_cours":
            return e
        time.sleep(0.02)
    raise AssertionError("lot trop long")


def rapports(client):
    return {e["id"] for c in client.get("/api/bibliotheque").json() for e in c["etudiants"] if e["labs"]}


def test_lot_limite_a_n_et_marque_les_analyses(labo, monkeypatch):
    file = FileFausse()
    brancher(monkeypatch, file)
    ap = labo.get(f"/api/lot/apercu/{LAB}").json()
    assert (ap["total"], ap["a_analyser"], ap["estimation"]["n"]) == (4, 4, 4)
    assert labo.get(f"/api/lot/apercu/{LAB}?n=2").json()["estimation"]["n"] == 2
    assert labo.post(f"/api/lot/{LAB}", json={"n": 3}).status_code == 200
    e = attendre(labo)
    assert e["statut"] == "termine" and e["fait"] == 3 and e["total"] == 3 and e["erreurs"] == []
    assert file.appels == 6  # 2 appels (français + indices d'IA) par rapport
    ap = labo.get(f"/api/lot/apercu/{LAB}").json()
    assert (ap["total"], ap["a_analyser"], ap["estimation"]["n"]) == (4, 1, 1)
    # le lot suivant reprend le reste, sans toucher aux rapports déjà faits
    labo.post(f"/api/lot/{LAB}", json={"n": 10})
    assert attendre(labo)["fait"] == 1 and file.appels == 8
    assert labo.post(f"/api/lot/{LAB}", json={}).status_code == 409  # plus rien à faire


def test_n_par_defaut_10(labo, monkeypatch):
    brancher(monkeypatch, FileFausse())
    labo.post(f"/api/lot/{LAB}")
    assert attendre(labo)["total"] == 4  # 4 rapports < 10
    assert lot.DemandeLot().n == 10


def test_limite_d_usage_garde_les_resultats_et_arrete(labo, monkeypatch):
    # 2 rapports complets (4 appels) puis limite pendant le français du 3e
    file = FileFausse(ok=4, erreur=ClaudeLimite("limit"))
    brancher(monkeypatch, file)
    labo.post(f"/api/lot/{LAB}", json={"n": 4})
    e = attendre(labo)
    assert e["statut"] == "limite" and e["fait"] == 2
    assert "réinitialisation" in e["message"] and e["erreurs"][0]["code"] == 429
    # le rapport interrompu (LanguageTool seul enregistré) reste à refaire, les 2 premiers non
    assert labo.get(f"/api/lot/apercu/{LAB}").json()["a_analyser"] == 2
    # reprise après la réinitialisation
    brancher(monkeypatch, FileFausse())
    labo.post(f"/api/lot/{LAB}", json={"n": 10})
    assert attendre(labo)["statut"] == "termine"
    assert labo.get(f"/api/lot/apercu/{LAB}").json()["a_analyser"] == 0


def test_limite_pendant_les_indices_d_ia(labo, monkeypatch):
    class Une(FileFausse):  # français réussit, indices d'IA : limite
        def soumettre(self, prompt, schema=None, systeme=None):
            if "force" in (schema or {}).get("properties", {}):
                f = Future()
                f.set_exception(ClaudeLimite("limit"))
                return f
            return super().soumettre(prompt, schema, systeme)

    brancher(monkeypatch, Une())
    labo.post(f"/api/lot/{LAB}")
    e = attendre(labo)
    assert e["statut"] == "limite" and e["fait"] == 0


def test_claude_non_connecte_arrete_le_lot(labo, monkeypatch):
    brancher(monkeypatch, FileFausse(ok=0, erreur=ClaudeNonConnecte("login")))
    labo.post(f"/api/lot/{LAB}")
    e = attendre(labo)
    assert e["statut"] == "erreur" and e["erreurs"][0]["code"] == 503


def test_arret_demande_apres_le_rapport_en_cours(labo, monkeypatch):
    file = FileFausse(pause=0.1)
    brancher(monkeypatch, file)
    labo.post(f"/api/lot/{LAB}")
    assert labo.post("/api/lot/arreter").status_code == 200
    e = attendre(labo)
    assert e["statut"] == "arrete" and e["fait"] < 4 and "demande" in e["message"]
    assert labo.get(f"/api/lot/apercu/{LAB}").json()["a_analyser"] == 4 - e["fait"]


def test_un_seul_lot_a_la_fois(labo, monkeypatch):
    brancher(monkeypatch, FileFausse(pause=0.1))
    assert labo.post(f"/api/lot/{LAB}").status_code == 200
    assert labo.post(f"/api/lot/{LAB}").status_code == 409
    labo.post("/api/lot/arreter")
    attendre(labo)


def test_analyses_et_decisions_jamais_ecrasees(labo, monkeypatch):
    brancher(monkeypatch, FileFausse())
    eleve = next(iter(rapports(labo)))
    dossier = lot._dossier_lab("202SNURE", "00002", "lab-3") / eleve
    # un rapport déjà analysé, avec une décision de Guillaume
    francais_json = {"version": 1, "fautes": [], "decisions": {"0": "acceptee"}, "choix": {}, "masquees": [],
                     "claude": {"ok": True, "erreur": None, "ajoutees": 0}}
    (dossier / "francais.json").write_text(json.dumps(francais_json), encoding="utf-8")
    (dossier / "indices_ia.json").write_text('{"force":"marquee"}', encoding="utf-8")
    (dossier / "references.json").write_text('{"claude":{"ok":true},"entrees":[]}', encoding="utf-8")
    noms = ("francais.json", "indices_ia.json", "references.json")
    avant = [(dossier / n).read_bytes() for n in noms]
    labo.post(f"/api/lot/{LAB}")
    assert attendre(labo)["fait"] == 3
    assert avant == [(dossier / n).read_bytes() for n in noms]


def test_le_lot_verifie_aussi_les_references(labo, monkeypatch):
    brancher(monkeypatch, FileFausse())
    labo.post(f"/api/lot/{LAB}")
    assert attendre(labo)["fait"] == 4
    for e in rapports(labo):
        doc = json.loads((lot._dossier_lab("202SNURE", "00002", "lab-3") / e / "references.json").read_text(encoding="utf-8"))
        assert doc["section"]["trouvee"] is False and doc["claude"]["ok"] is True  # rapport sans section : rien à envoyer


def test_refaire_retraite_tous_les_rapports(labo, monkeypatch):
    brancher(monkeypatch, FileFausse())
    labo.post(f"/api/lot/{LAB}")
    attendre(labo)
    eleve = next(iter(rapports(labo)))
    chemin = lot._dossier_lab("202SNURE", "00002", "lab-3") / eleve / "francais.json"
    doc = json.loads(chemin.read_text(encoding="utf-8"))
    doc["decisions"] = {"7": "refusee"}
    chemin.write_text(json.dumps(doc), encoding="utf-8")
    assert labo.get(f"/api/lot/apercu/{LAB}").json()["a_analyser"] == 0
    assert labo.get(f"/api/lot/apercu/{LAB}?refaire=true").json()["a_analyser"] == 4
    assert labo.post(f"/api/lot/{LAB}", json={"n": 4, "refaire": True}).status_code == 200
    assert attendre(labo)["fait"] == 4
    assert json.loads(chemin.read_text(encoding="utf-8"))["claude"]["ok"] is True


def test_lab_inconnu_et_n_invalide(labo):
    assert labo.post("/api/lot/202SNURE/00002/inconnu").status_code == 404
    assert labo.post(f"/api/lot/{LAB}", json={"n": 0}).status_code == 422
