"""PR A de la refonte Accueil / Bibliothèque (P1) : lot par lab, comptes du suivi, recherche, « Reprendre ».
Bibliothèque fictive seulement ; Claude et LanguageTool sont simulés."""

import json
import time

from moteur import lot, recherche
from tests.test_bibliotheque import client, deux_groupes, importer_cours, pdf  # noqa: F401
from tests.test_export_lot import COURS, PAGE_ALICE, lab  # noqa: F401


def attendre(client):
    for _ in range(300):
        e = client.get("/api/lot").json()
        if e["statut"] != "en_cours":
            return e
        time.sleep(0.02)
    raise AssertionError("lot trop long")


def espionner(monkeypatch) -> list:
    appels = []
    # un appel noté par rapport (le premier type d'analyse qui lui manque)
    vus = []
    def noter(c, g, l, e):
        if (g, e) not in vus:
            vus.append((g, e))
            appels.append((g, e))
        return {}
    monkeypatch.setattr(lot.francais, "analyser_rapport", noter)
    monkeypatch.setattr(lot.indices_ia, "analyser", lambda c, g, l, e: noter(c, g, l, e) and None)
    monkeypatch.setattr(lot.references, "analyser_rapport", noter)
    return appels


# --- Lot par lab ---------------------------------------------------------------

def test_lot_par_lab_tous_les_groupes_dans_l_ordre_de_correction(lab, monkeypatch):
    client, tmp = lab
    appels = espionner(monkeypatch)
    # Luc (00001) est terminé : le prochain non terminé est Zoé ; ordre du suivi = Luc, Alice, Zoé -> Zoé, Luc, Alice
    client.put(f"/api/bibliotheque/statut/{COURS}/00001/lab-1/martin-luc", json={"termine": True})
    ap = client.get(f"/api/lot/apercu/{COURS}/lab-1?n=2").json()
    assert (ap["total"], ap["a_analyser"], ap["estimation"]["n"]) == (3, 3, 2)
    r = client.post(f"/api/lot/{COURS}/lab-1", json={"n": 2})
    assert r.status_code == 200 and r.json()["total"] == 2 and r.json()["groupe"] is None
    e = attendre(client)
    assert e["statut"] == "termine" and e["fait"] == 2
    assert appels == [("00002", "martin-zoe"), ("00001", "martin-luc")]  # Alice (3e) n'est pas dans le lot de 2


def test_lot_par_lab_un_groupe_et_rien_a_faire(lab, monkeypatch):
    client, _ = lab
    appels = espionner(monkeypatch)
    ap = client.get(f"/api/lot/apercu/{COURS}/lab-1?groupe=00002").json()
    assert ap["total"] == 2 and ap["a_analyser"] == 2
    assert client.post(f"/api/lot/{COURS}/lab-1", json={"groupe": "00002"}).status_code == 200
    assert attendre(client)["groupe"] == "00002"
    assert {g for g, _ in appels} == {"00002"}
    assert client.get(f"/api/lot/apercu/{COURS}/lab-1?groupe=00009").status_code == 404
    assert client.post(f"/api/lot/ZZZ/lab-1").status_code == 404


def test_lot_par_lab_refuse_un_second_lot_et_les_routes_par_groupe_restent(lab, monkeypatch):
    client, _ = lab
    monkeypatch.setattr(lot.francais, "analyser_rapport", lambda *a: time.sleep(0.2) or {})
    monkeypatch.setattr(lot.indices_ia, "analyser", lambda *a: None)
    monkeypatch.setattr(lot.references, "analyser_rapport", lambda *a: {})
    assert client.post(f"/api/lot/{COURS}/lab-1").status_code == 200
    assert client.post(f"/api/lot/{COURS}/lab-1").status_code == 409
    assert client.post(f"/api/lot/{COURS}/00001/lab-1").status_code == 409
    client.post("/api/lot/arreter")
    assert attendre(client)["statut"] == "arrete"
    assert client.get(f"/api/lot/apercu/{COURS}/00001/lab-1").json()["total"] == 1


# --- Suivi : comptes et non remis ---------------------------------------------------

def test_suivi_comptes_et_non_remis(lab):
    client, tmp = lab
    base = tmp / "bibliotheque" / COURS
    d = client.get(f"/api/suivi/{COURS}/lab-1").json()
    # inscrits : Anna, Luc, Alice, Zoé ; Anna est dans l'équipe d'Alice : aucun non remis
    assert d["compte"] == {"a_corriger": 0, "en_cours": 2, "termine": 1, "a_revoir": 2,
                           "inscrits": 4, "recus": 3, "analyses": 0, "termines": 1, "non_remis": 0}
    assert d["non_remis"] == []
    # Luc : tout est fait -> analysé
    (base / "00001/lab-1/martin-luc/francais.json").write_text(json.dumps(
        {"fautes": [], "decisions": {}, "claude": {"ok": True}}), encoding="utf-8")
    (base / "00001/lab-1/martin-luc/references.json").write_text(json.dumps({"claude": {"ok": True}}), encoding="utf-8")
    d = client.get(f"/api/suivi/{COURS}/lab-1").json()
    assert d["compte"]["analyses"] == 1
    assert {r["etudiant"]: r["analyse"] for r in d["rapports"]}["martin-luc"] is True


def test_non_remis_exclut_equipe_et_retires(lab):
    client, tmp = lab
    client.post("/api/bibliotheque/import", data={"cours": COURS, "groupe": "", "lab": "Lab 2"},
                files=[("fichiers", ("dube_2000001_L2.pdf", pdf(PAGE_ALICE), "application/pdf"))])
    d = client.get(f"/api/suivi/{COURS}/lab-2").json()
    assert d["non_remis"] == [{"groupe": "00001", "id": "martin-luc", "nom": "Martin", "prenom": "Luc"},
                              {"groupe": "00002", "id": "martin-zoe", "nom": "Martin", "prenom": "Zoé"}]
    assert d["compte"]["non_remis"] == 2 and d["compte"]["inscrits"] == 4 and d["compte"]["recus"] == 1
    # Luc retiré de la liste : plus compté
    fichier = tmp / "bibliotheque" / COURS / "00001" / "classe.json"
    classe = json.loads(fichier.read_text(encoding="utf-8"))
    for e in classe["etudiants"]:
        if e["id"] == "martin-luc":
            e["retire"] = True
    fichier.write_text(json.dumps(classe), encoding="utf-8")
    d = client.get(f"/api/suivi/{COURS}/lab-2").json()
    assert [r["id"] for r in d["non_remis"]] == ["martin-zoe"] and d["compte"]["inscrits"] == 3
    # groupe filtré : l'équipe d'un autre groupe compte encore (Anna est dans l'équipe d'Alice, groupe 00002)
    d = client.get(f"/api/suivi/{COURS}/lab-2?groupe=00001").json()
    assert d["non_remis"] == [] and d["compte"]["inscrits"] == 1


# --- Recherche ---------------------------------------------------------------------

def test_recherche_nom_da_et_lab_sans_accents(lab):
    client, _ = lab
    r = client.get("/api/recherche", params={"q": "DUBE"}).json()
    assert [(e["id"], e["da"], e["cours"], e["groupe"], e["nb_rapports"]) for e in r["etudiants"]] == [
        ("dube-alice", "2000001", COURS, "00002", 1)]
    assert [(x["lab"], x["etat"], x["note"]) for x in r["rapports"]] == [("lab-1", "termine", "17,5")]
    assert [e["id"] for e in client.get("/api/recherche", params={"q": "zoé"}).json()["etudiants"]] == ["martin-zoe"]
    assert [e["id"] for e in client.get("/api/recherche", params={"q": "20000"}).json()["etudiants"]] == [
        "dube-alice", "martin-zoe"]
    assert client.get("/api/recherche", params={"q": "000001"}).json()["etudiants"] == []  # préfixe du DA seulement
    # prénom + nom, dans n'importe quel ordre
    assert [e["id"] for e in client.get("/api/recherche", params={"q": "luc martin"}).json()["etudiants"]] == ["martin-luc"]
    # nom de lab : tous les rapports du lab ; lab + nom restreint
    assert len(client.get("/api/recherche", params={"q": "lab-1"}).json()["rapports"]) == 3
    assert len(client.get("/api/recherche", params={"q": "lab 1 zoe"}).json()["rapports"]) == 1


def test_recherche_minimum_limite_et_cours_passes(lab, monkeypatch):
    client, tmp = lab
    assert client.get("/api/recherche", params={"q": "m"}).status_code == 422
    assert client.get("/api/recherche", params={"q": " "}).status_code == 422
    monkeypatch.setattr(recherche, "MAX_RESULTATS", 1)
    r = client.get("/api/recherche", params={"q": "martin"}).json()
    assert len(r["etudiants"]) == 1 and r["plus"]["etudiants"] is True and r["plus"]["rapports"] is True
    # un cours passé (autre dossier de cours) est couvert aussi
    monkeypatch.setattr(recherche, "MAX_RESULTATS", 30)
    ancien = tmp / "bibliotheque" / "101OLD" / "00001"
    (ancien / "lab-1" / "gagnon-eve").mkdir(parents=True)
    (ancien / "classe.json").write_text(json.dumps({"cours": "101OLD", "groupe": "00001", "etudiants": [
        {"id": "gagnon-eve", "nom": "Gagnon", "prenom": "Ève", "da": "1999999"}]}), encoding="utf-8")
    (ancien / "lab-1" / "gagnon-eve" / "rapport.pdf").write_bytes(pdf("Ève"))
    r = client.get("/api/recherche", params={"q": "eve"}).json()
    assert [(e["cours"], e["nb_rapports"]) for e in r["etudiants"]] == [("101OLD", 1)]
    assert [(x["cours"], x["etat"]) for x in r["rapports"]] == [("101OLD", "a_corriger")]


def test_recherche_fichiers_en_attente(lab):
    client, _ = lab
    res = client.post("/api/bibliotheque/import", data={"cours": COURS, "groupe": "", "lab": "Lab 2"},
                      files=[("fichiers", ("inconnu_Rapport.pdf", pdf("X"), "application/pdf")),
                             ("fichiers", ("autre_9876543.pdf", pdf("Y"), "application/pdf"))]).json()
    assert len(res["en_attente"]) == 2
    r = client.get("/api/recherche", params={"q": "INCONNU"}).json()
    assert [a["fichier"] for a in r["attente"]] == ["inconnu_Rapport.pdf"]
    assert [a["fichier"] for a in client.get("/api/recherche", params={"q": "98765"}).json()["attente"]] == ["autre_9876543.pdf"]


# --- Reprendre ---------------------------------------------------------------------

def test_reprendre_vide_puis_dernier_et_recents_sans_doublon(lab):
    client, tmp = lab
    assert client.get("/api/reprendre").json() == {"dernier": None, "recents": []}
    corps = lambda g, e, **kw: {"cours": COURS, "groupe": g, "lab": "lab-1", "etudiant": e, **kw}  # noqa: E731
    r = client.put("/api/reprendre", json=corps("00002", "dube-alice"),
                   headers={"User-Agent": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)"}).json()
    assert r["dernier"]["appareil"] == "iPad" and r["dernier"]["nom"] == "Dubé" and r["dernier"]["prenom"] == "Alice"
    assert r["dernier"]["date"][:4].isdigit() and r["recents"] == [r["dernier"]]
    client.put("/api/reprendre", json=corps("00001", "martin-luc"), headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0)"})
    r = client.put("/api/reprendre", json=corps("00002", "dube-alice", appareil="PC")).json()  # remonte en tête, sans doublon
    assert [(x["etudiant"], x["appareil"]) for x in r["recents"]] == [("dube-alice", "PC"), ("martin-luc", "PC")]
    assert client.get("/api/reprendre").json() == r
    assert (tmp / "reprendre.json").is_file()
    # appareil inconnu : déduit du User-Agent
    r = client.put("/api/reprendre", json=corps("00001", "martin-luc", appareil="Toaster")).json()
    assert r["dernier"]["appareil"] == "PC"


def test_reprendre_garde_cinq_et_refuse_un_rapport_inconnu(lab):
    client, tmp = lab
    base = tmp / "bibliotheque" / COURS / "00002"
    for i in range(3, 9):
        (base / f"lab-{i}" / "dube-alice").mkdir(parents=True)
        (base / f"lab-{i}" / "dube-alice" / "rapport.pdf").write_bytes(pdf("x"))
        client.put("/api/reprendre", json={"cours": COURS, "groupe": "00002", "lab": f"lab-{i}", "etudiant": "dube-alice"})
    r = client.get("/api/reprendre").json()
    assert [x["lab"] for x in r["recents"]] == ["lab-8", "lab-7", "lab-6", "lab-5", "lab-4"]
    assert r["dernier"]["lab"] == "lab-8"
    assert client.put("/api/reprendre", json={"cours": COURS, "groupe": "00002", "lab": "lab-1", "etudiant": "inconnu"}).status_code == 404
    assert client.put("/api/reprendre", json={"cours": "../x", "groupe": "00002", "lab": "lab-1", "etudiant": "a"}).status_code == 400
