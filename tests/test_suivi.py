"""Tests du tableau de suivi d'un lab. Bibliothèque fictive seulement."""

import json

from moteur import lot, plagiat
from tests.test_bibliotheque import client, deux_groupes, importer_cours, pdf  # noqa: F401
from tests.test_export_lot import COURS, PAGE_ALICE, ecrire_francais, lab  # noqa: F401


def par_id(d: dict) -> dict:
    return {r["etudiant"]: r for r in d["rapports"]}


def test_suivi_un_seul_appel_pour_tout_le_lab(lab):
    client, tmp = lab
    base = tmp / "bibliotheque" / COURS / "00001/lab-1/martin-luc"
    base.joinpath("annotations.json").write_text(json.dumps({"version": 1, "pages": {"1": [{
        "outil": "crayon", "couleur": "#ff0000", "largeur_min": 1, "largeur_max": 2, "courbe": 1,
        "points": [[1, 1, 0.5]]}]}}), encoding="utf-8")
    d = client.get(f"/api/suivi/{COURS}/lab-1").json()
    assert d["total"] == 3 and d["groupes"] == ["00001", "00002"]
    assert [(r["groupe"], r["nom"]) for r in d["rapports"]] == [("00001", "Martin"), ("00002", "Dubé"), ("00002", "Martin")]
    r = par_id(d)
    alice, zoe, luc = r["dube-alice"], r["martin-zoe"], r["martin-luc"]
    assert alice["equipe"] == ["Anna Bele-Gombos"]
    assert alice["etat"] == "termine" and alice["note"] == "17,5"
    assert alice["francais"] == {"etat": "tranche", "a_trancher": 0, "acceptees": 2, "penalite": 1.5}
    assert alice["plagiat"]["etat"] == "confirmee" and alice["plagiat"]["avec"] == ["Luc Martin"]
    assert zoe["francais"]["etat"] == "a_trancher" and zoe["francais"]["a_trancher"] == 2
    assert zoe["etat"] == "en_cours" and zoe["a_revoir"] and not zoe["annotation"]
    assert luc["annotation"] and luc["ia"] == "moderee" and luc["etat"] == "en_cours"
    assert luc["francais"] == {"etat": "non_analyse"}
    assert luc["plagiat"]["etat"] == "confirmee"
    assert d["compte"] == {"a_corriger": 0, "en_cours": 2, "termine": 1, "a_revoir": 2}


def test_suivi_a_corriger_quand_rien_n_est_fait(client):
    deux_groupes(client)
    importer_cours(client, [("dube_2000001_Rapport.pdf", pdf("Alice")), ("martin_1000002_Rapport.pdf", pdf("Luc"))])
    d = client.get(f"/api/suivi/{COURS}/lab-1").json()
    assert {r["etat"] for r in d["rapports"]} == {"a_corriger"}
    assert all(r["plagiat"] is None and r["ia"] is None and not r["a_revoir"] for r in d["rapports"])


def test_suivi_filtre_groupe_et_plagiat_suspect_ou_ecarte(lab):
    client, _ = lab
    d = client.get(f"/api/suivi/{COURS}/lab-1?groupe=00002").json()
    assert d["groupes"] == ["00002"] and d["total"] == 2
    plagiat._ecrire("decisions.json", {"x-y": {"statut": "ecartee"}})
    r = par_id(client.get(f"/api/suivi/{COURS}/lab-1").json())
    assert r["martin-luc"]["plagiat"]["etat"] == "ecartee" and not r["martin-luc"]["a_revoir"]
    plagiat._ecrire("decisions.json", {})  # sans décision, score 0,5 >= seuil : paire à confirmer
    r = par_id(client.get(f"/api/suivi/{COURS}/lab-1").json())
    assert r["martin-luc"]["plagiat"]["etat"] == "suspecte" and r["martin-luc"]["a_revoir"]


def test_suivi_cours_inconnu(client):
    assert client.get("/api/suivi/ZZZ/lab-1").status_code == 404


def test_analyser_un_seul_rapport(lab, monkeypatch):
    client, _ = lab
    appels = []
    monkeypatch.setattr(lot.francais, "analyser_rapport", lambda *a: appels.append(("fr", a[-1])) or {})
    monkeypatch.setattr(lot.indices_ia, "analyser", lambda *a: appels.append(("ia", a[-1])))
    assert client.post(f"/api/lot/{COURS}/00001/lab-1/martin-luc").status_code == 200
    import time
    for _ in range(100):
        if client.get("/api/lot").json()["statut"] != "en_cours":
            break
        time.sleep(0.05)
    assert appels == [("fr", "martin-luc")]  # l'indice d'IA de Luc existe déjà
    assert client.post(f"/api/lot/{COURS}/00001/lab-1/inconnu").status_code == 404
