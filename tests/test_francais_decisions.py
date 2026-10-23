"""Décisions de français fiables (audit C1) : ids stables, révision, PATCH par faute, migration."""
import json

from moteur import francais_claude
from moteur.export import fautes_acceptees

from tests.test_francais import (  # noqa: F401
    FAUTE_CLAUDE, URL_RAPPORT, FileFausse, charger_classe, client, importer, pdf, rapport_range,
)

AVANT = {"extrait": "etudiants", "correction": "étudiants", "message": "Accent"}  # placé AVANT « mesure » dans le texte


def par_texte(j):
    """Décisions du rapport par texte de faute : indépendant des ids."""
    textes = {f["id"]: f["texte"] for f in j["fautes"]}
    return {textes[i]: d for i, d in j["decisions"].items()}


def fichier_francais(tmp_path):
    return tmp_path / "bibliotheque/202SNURE_A2026/00002/lab-3/dube-alice/francais.json"


def test_ids_stables_d_une_analyse_a_l_autre(rapport_range, monkeypatch):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    ids1 = {f["texte"]: f["id"] for f in rapport_range.post(URL_RAPPORT + "/analyser").json()["fautes"]}
    # Claude trouve en plus une faute AVANT les autres : les ids des fautes inchangées ne bougent pas
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE, AVANT]))
    ids2 = {f["texte"]: f["id"] for f in rapport_range.post(URL_RAPPORT + "/analyser").json()["fautes"]}
    assert list(ids2)[0] == "etudiants" and set(ids1) < set(ids2)
    assert all(ids2[t] == ids1[t] for t in ids1)
    assert len(set(ids2.values())) == 3


def test_scenario_c1_reanalyse_pendant_qu_un_lecteur_garde_d_anciens_ids(rapport_range, monkeypatch):
    """Scénario de l'audit : décisions de l'iPad (« mesure » refusée, « a manger » acceptée), réanalyse qui ajoute
    une faute avant les autres, puis geste de l'iPad avec son état d'avant. Rien ne doit être réattribué."""
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    ipad = rapport_range.post(URL_RAPPORT + "/analyser").json()          # état gardé par le lecteur
    mesure, manger = (f["id"] for f in ipad["fautes"])
    rapport_range.patch(URL_RAPPORT, json={"fautes": {mesure: {"decision": "refusee"}, manger: {"decision": "acceptee"}}})
    ipad = rapport_range.get(URL_RAPPORT).json()
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE, AVANT]))
    rapport_range.post(URL_RAPPORT + "/analyser")                         # le lot repasse le rapport
    # 1. Le PUT d'état complet de l'iPad (révision d'avant la réanalyse) est refusé
    r = rapport_range.put(URL_RAPPORT, json={"revision": ipad["revision"], "decisions": ipad["decisions"],
                                             "choix": ipad["choix"], "masquees": ipad["masquees"],
                                             "decalages": {mesure: [3, 4]}})
    assert r.status_code == 409
    j = rapport_range.get(URL_RAPPORT).json()
    assert par_texte(j) == {"mesure": "refusee", "a manger": "acceptee"} and j["decalages"] == {}
    # 2. Un PATCH avec d'anciens ids vise les mêmes fautes (ids stables) : rien n'est réattribué
    r = rapport_range.patch(URL_RAPPORT, json={"fautes": {mesure: {"decalage": [3, 4]}}})
    assert r.status_code == 200
    j = r.json()
    assert par_texte(j) == {"mesure": "refusee", "a manger": "acceptee"} and j["decalages"] == {mesure: [3, 4]}
    assert j["nb_acceptees"] == 1


def test_put_revision_perimee_409_puis_recharge_ok(rapport_range):
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    fid = j["fautes"][0]["id"]
    ok = rapport_range.put(URL_RAPPORT, json={"revision": j["revision"], "decisions": {fid: "acceptee"}})
    assert ok.status_code == 200 and ok.json()["revision"] == j["revision"] + 1
    perime = rapport_range.put(URL_RAPPORT, json={"revision": j["revision"], "decisions": {fid: "refusee"}})
    assert perime.status_code == 409 and "recharg" in perime.json()["detail"]
    assert rapport_range.get(URL_RAPPORT).json()["decisions"] == {fid: "acceptee"}  # rien d'écrasé
    frais = rapport_range.get(URL_RAPPORT).json()
    assert rapport_range.put(URL_RAPPORT, json={"revision": frais["revision"], "decisions": {fid: "refusee"}}).status_code == 200


def test_deux_appareils_ne_s_ecrasent_pas(rapport_range, monkeypatch):
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    rapport_range.post(URL_RAPPORT + "/analyser")
    a = rapport_range.get(URL_RAPPORT).json()      # iPad et ordi chargent le même état
    b = rapport_range.get(URL_RAPPORT).json()
    mesure, manger = (f["id"] for f in a["fautes"])
    rapport_range.patch(URL_RAPPORT, json={"fautes": {mesure: {"decision": "acceptee", "choix": "mesurent"}}})   # iPad
    rapport_range.patch(URL_RAPPORT, json={"fautes": {manger: {"decision": "refusee"}, mesure: {"masquee": True}}})  # ordi
    j = rapport_range.get(URL_RAPPORT).json()
    assert j["decisions"] == {mesure: "acceptee", manger: "refusee"}
    assert j["choix"] == {mesure: "mesurent"} and j["masquees"] == [mesure]
    # le PUT d'état complet, lui, reste protégé : l'état de départ de `b` est périmé
    assert rapport_range.put(URL_RAPPORT, json={"revision": b["revision"], "decisions": {}}).status_code == 409
    assert j["revision"] == b["revision"] + 2


def test_patch_retours_a_l_origine(rapport_range):
    fid = rapport_range.post(URL_RAPPORT + "/analyser").json()["fautes"][0]["id"]
    rapport_range.patch(URL_RAPPORT, json={"fautes": {fid: {"decision": "acceptee", "choix": "x", "masquee": True,
                                                               "decalage": [1, 2]}}})
    j = rapport_range.patch(URL_RAPPORT, json={"fautes": {fid: {"decision": None, "choix": None, "masquee": False,
                                                                  "decalage": None}}}).json()
    assert j["decisions"] == {} and j["choix"] == {} and j["masquees"] == [] and j["decalages"] == {}


def test_patch_est_tout_ou_rien(rapport_range):
    fid = rapport_range.post(URL_RAPPORT + "/analyser").json()["fautes"][0]["id"]
    r = rapport_range.patch(URL_RAPPORT, json={"fautes": {fid: {"decision": "acceptee"}, "9-9-abc": {"decision": "acceptee"}}})
    assert r.status_code == 409
    assert rapport_range.get(URL_RAPPORT).json()["decisions"] == {}


def test_migration_ancien_francais_json(rapport_range, monkeypatch, tmp_path):
    """Un francais.json d'avant les ids stables (id = rang, sans révision) reste lisible, sans perdre de décision."""
    monkeypatch.setattr(francais_claude, "obtenir_file", lambda: FileFausse([FAUTE_CLAUDE]))
    j = rapport_range.post(URL_RAPPORT + "/analyser").json()
    f = fichier_francais(tmp_path)
    doc = json.loads(f.read_text(encoding="utf-8"))
    ancien = {**doc, "version": 1,
              "fautes": [{**x, "id": i} for i, x in enumerate(doc["fautes"])],
              "decisions": {"0": "refusee", "1": "acceptee"}, "choix": {"1": "a mangé"},
              "masquees": [0], "decalages": {"1": [7.5, -2]}}
    del ancien["revision"]
    f.write_text(json.dumps(ancien), encoding="utf-8")

    lu = rapport_range.get(URL_RAPPORT).json()
    assert [x["id"] for x in lu["fautes"]] == [x["id"] for x in j["fautes"]]
    mesure, manger = (x["id"] for x in lu["fautes"])
    assert lu["decisions"] == {mesure: "refusee", manger: "acceptee"} and lu["choix"] == {manger: "a mangé"}
    assert lu["masquees"] == [mesure] and lu["decalages"] == {manger: [7.5, -2]} and lu["revision"] == 0
    assert lu["nb_acceptees"] == 1
    # les lecteurs du fichier brut (export, suivi) s'y retrouvent aussi, avant comme après la migration
    assert [x["correction"] for x in fautes_acceptees(f)] == ["a mangé"]
    # la première écriture réécrit le fichier au nouveau format ; une réanalyse garde tout
    assert rapport_range.patch(URL_RAPPORT, json={"fautes": {manger: {"decision": "acceptee"}}}).json()["revision"] == 1
    j2 = rapport_range.post(URL_RAPPORT + "/analyser").json()
    assert j2["decisions"] == {mesure: "refusee", manger: "acceptee"} and j2["masquees"] == [mesure]
    assert j2["decalages"] == {manger: [7.5, -2]}
    assert all(isinstance(x["id"], str) for x in json.loads(f.read_text(encoding="utf-8"))["fautes"])
    assert [x["correction"] for x in fautes_acceptees(f)] == ["a mangé"]
