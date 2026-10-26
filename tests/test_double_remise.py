"""Double remise d'une équipe : détection (import et labs déjà importés), choix, copie récupérable.

Étudiants, DA et PDF fictifs."""
import io

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur.app import creer_app
from moteur.double_remise import date_de_remise

COURS = "202SNURE_A2026"
G = "00002"
ALICE, MARIE, LUC, ANNA = "dube-alice", "roy-marie", "martin-luc", "ouellet-anna"
API = "/api/bibliotheque"


def pdf(lignes, pages=1):
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    for _ in range(pages):
        y = 780
        for ligne in lignes:
            c.drawString(72, y, ligne)
            y -= 20
        c.showPage()
    c.save()
    return tampon.getvalue()


TITRE_SEUL = ["Rapport de laboratoire", "Par Alice Dubé"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    c = TestClient(creer_app())
    texte = "No de DA;Nom de l'étudiant;Prénom de l'étudiant\r\n" + "\r\n".join(
        f'="{da}";="{n}";="{p}"' for da, n, p in [("2000001", "Dubé", "Alice"), ("2000002", "Roy", "Marie"),
                                                  ("2000003", "Martin", "Luc"), ("2000004", "Ouellet", "Anna")])
    r = c.post(f"{API}/classes", files={"fichier": (f"ListeEtudiants_cours{COURS.split('_')[0]}_gr{G}.csv", texte.encode("cp1252"))})
    assert r.status_code == 200, r.text
    c.donnees = tmp_path
    return c


def importer(client, da, nom, lignes, lab="Lab 1", remis="2026-09-18_17h43m16s"):
    fichier = f"{nom}_{da}_Rapport_Remis_le_{remis}.pdf"
    return client.post(f"{API}/import", data={"cours": COURS, "groupe": "", "lab": lab},
                       files=[("fichiers", (fichier, pdf(lignes), "application/pdf"))]).json()


def alice(client, lignes=("Rapport", "Par Alice Dubé"), **kw):
    return importer(client, "2000001", "Dube", list(lignes), **kw)


def marie(client, lignes=("Rapport", "Par Marie Roy"), **kw):
    return importer(client, "2000002", "Roy", list(lignes), **kw)


def dossier(tmp, etu, lab="lab-1"):
    return tmp / "bibliotheque" / COURS / G / lab / etu


def suivi(client, lab="lab-1"):
    return client.get(f"/api/suivi/{COURS}/{lab}").json()


def attente(client):
    return client.get(f"{API}/attente").json()


def api_attente(client, ident, choix, confirmer=True):
    return client.post(f"{API}/attente/{ident}/double", json={"choix": choix, "confirmer": confirmer})


# --- Détection à l'import -------------------------------------------------------

def test_le_nouveau_nomme_l_existant(client):
    assert len(marie(client)["ranges"]) == 1
    res = alice(client, ["Rapport", "Par Alice Dubé et Marie Roy"])
    assert res["ranges"] == [] and res["en_attente"][0]["raison"] == "double_remise"
    d = res["en_attente"][0]["double"]
    assert d["nommage"] == "nouveau_nomme" and d["existant"]["id"] == MARIE
    assert not dossier(client.donnees, ALICE).exists()  # la seconde copie n'est pas rangée


def test_l_existant_nomme_le_nouveau(client):
    assert len(alice(client, ["Rapport", "Par Alice Dubé et Marie Roy"])["ranges"]) == 1
    res = marie(client)
    assert res["en_attente"][0]["raison"] == "double_remise"
    assert res["en_attente"][0]["double"]["nommage"] == "existant_nomme"
    assert res["en_attente"][0]["double"]["existant"]["id"] == ALICE


def test_les_deux_se_nomment(client):
    alice(client, ["Rapport", "Par Alice Dubé et Marie Roy"])
    res = marie(client, ["Rapport", "Par Marie Roy et Alice Dubé"])
    assert res["en_attente"][0]["double"]["nommage"] == "mutuel"


def test_double_dans_un_meme_lot(client):
    fichiers = [("fichiers", ("Dube_2000001_Remis_le_2026-09-18_17h43m16s.pdf", pdf(["Par Alice Dubé et Marie Roy"]), "application/pdf")),
                ("fichiers", ("Roy_2000002_Remis_le_2026-09-18_18h01m02s.pdf", pdf(["Par Marie Roy"]), "application/pdf"))]
    res = client.post(f"{API}/import", data={"cours": COURS, "groupe": "", "lab": "Lab 1"}, files=fichiers).json()
    assert len(res["ranges"]) == 1 and res["en_attente"][0]["raison"] == "double_remise"


def test_aucun_faux_positif(client):
    # Deux équipes différentes (A+M, L+N) dans le même lab : aucune double remise.
    assert len(alice(client, ["Par Alice Dubé et Marie Roy"])["ranges"]) == 1
    assert len(importer(client, "2000003", "Martin", ["Par Luc Martin et Anna Ouellet"])["ranges"]) == 1
    # Un même étudiant dans deux labs, et un coéquipier nommé au lab 1 qui dépose au lab 2.
    assert len(alice(client, ["Par Alice Dubé"], lab="Lab 2")["ranges"]) == 1
    assert len(marie(client, lab="Lab 3")["ranges"]) == 1
    assert suivi(client)["doubles"] == [] and attente(client) == []


def test_sans_nom_de_coequipier_pas_de_double(client):
    assert len(alice(client)["ranges"]) == 1
    assert len(marie(client)["ranges"]) == 1  # aucun des deux n'en nomme un autre : deux rapports distincts
    assert suivi(client)["doubles"] == []


# --- Labs déjà importés ------------------------------------------------------------

def double_existante(client):
    alice(client)
    marie(client)
    r = client.put(f"{API}/equipe/{COURS}/{G}/lab-1/{ALICE}", json={"equipe": [{"groupe": G, "id": MARIE}]})
    assert r.status_code == 200
    # un peu de travail sur la copie de Marie
    d = dossier(client.donnees, MARIE)
    (d / "annotations.json").write_text('{"version": 2, "revision": 1, "pages": {"1": [{"id": "t1"}]}, "supprimes": []}', encoding="utf-8")
    (d / "statut.json").write_text('{"termine": true, "note": "17/20"}', encoding="utf-8")


def test_verification_des_labs_existants_et_bannière(client):
    double_existante(client)
    s = suivi(client)
    assert len(s["doubles"]) == 1
    d = s["doubles"][0]
    assert {d["a"]["id"], d["b"]["id"]} == {ALICE, MARIE} and d["nommage"] in ("a_nomme_b", "b_nomme_a")


def url_cmp(a=ALICE, b=MARIE):
    return f"{API}/double/{COURS}/lab-1/{G}/{a}/{G}/{b}"


def test_comparaison_cote_a_cote(client):
    double_existante(client)
    r = client.get(url_cmp()).json()
    alice_c, marie_c = r["copies"]
    assert (alice_c["id"], marie_c["id"]) == (ALICE, MARIE)
    assert alice_c["remis_le"] == "2026-09-18T17:43:16" and alice_c["pages"] == 1
    assert alice_c["fichier"].startswith("Dube_2000001") and alice_c["travail"]["vide"] is True
    t = marie_c["travail"]
    assert t["traits"] == 1 and t["termine"] is True and t["note"] == "17/20" and t["vide"] is False
    assert client.get(alice_c["pdf"]).status_code == 200
    # paire sans lien ou sans rapport : 404
    assert client.get(f"{API}/double/{COURS}/lab-1/{G}/{ALICE}/{G}/{LUC}").status_code == 404


def test_garder_a_marie_ecartee_mais_recuperable_et_rattachee(client):
    double_existante(client)
    r = client.post(f"{API}/double/{COURS}/lab-1", json={"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE}, "choix": "a"})
    assert r.status_code == 409 and "_remplaces" in r.json()["detail"] and "Marie Roy" in r.json()["detail"]
    assert (dossier(client.donnees, MARIE) / "rapport.pdf").is_file()  # rien n'a bougé sans confirmation
    r = client.post(f"{API}/double/{COURS}/lab-1", json={"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE},
                                                         "choix": "a", "confirmer": True})
    assert r.status_code == 200, r.text
    assert not dossier(client.donnees, MARIE).exists() and (dossier(client.donnees, ALICE) / "rapport.pdf").is_file()
    # copie récupérable avec son travail
    mis = client.donnees / "bibliotheque" / "_remplaces" / r.json()["mis_de_cote"]
    assert (mis / "rapport.pdf").is_file() and (mis / "annotations.json").is_file()
    assert '"17/20"' in (mis / "statut.json").read_text(encoding="utf-8") and (mis / "double_remise.json").is_file()
    # suivi, non remis, export, plagiat
    s = suivi(client)
    assert s["total"] == 1 and s["doubles"] == [] and s["compte"]["non_remis"] == 2  # Luc et Anna seulement
    assert MARIE not in [n["id"] for n in s["non_remis"]] and s["rapports"][0]["equipe"] == ["Marie Roy"]
    tableau = client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content.decode("utf-8-sig")
    assert ";Roy;Marie;" in tableau and ";Dubé;Alice;" in tableau


def test_garder_b_alice_ecartee_marie_garde_alice_comme_coequipiere(client):
    double_existante(client)
    corps = {"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE}, "choix": "b", "confirmer": True}
    assert client.post(f"{API}/double/{COURS}/lab-1", json=corps).status_code == 200
    assert not dossier(client.donnees, ALICE).exists()
    s = suivi(client)
    assert [r["etudiant"] for r in s["rapports"]] == [MARIE] and s["rapports"][0]["equipe"] == ["Alice Dubé"]
    assert ALICE not in [n["id"] for n in s["non_remis"]]
    assert s["rapports"][0]["termine"] is True  # le travail de la copie gardée est intact
    tableau = client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content.decode("utf-8-sig")
    assert ";Dubé;Alice;" in tableau and ";Roy;Marie;" in tableau


def test_garder_les_deux_retire_le_lien(client):
    double_existante(client)
    corps = {"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE}, "choix": "les_deux"}
    assert client.post(f"{API}/double/{COURS}/lab-1", json=corps).status_code == 200  # rien n'est mis de côté : pas de confirmation
    s = suivi(client)
    assert s["total"] == 2 and s["doubles"] == [] and all(r["equipe"] == [] for r in s["rapports"])
    assert (dossier(client.donnees, ALICE) / "rapport.pdf").is_file() and (dossier(client.donnees, MARIE) / "rapport.pdf").is_file()
    assert not (client.donnees / "bibliotheque" / "_remplaces").exists()
    # la paire n'existe plus : un second choix est refusé
    assert client.post(f"{API}/double/{COURS}/lab-1", json={**corps, "choix": "a", "confirmer": True}).status_code == 404


def test_choix_invalide(client):
    double_existante(client)
    corps = {"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE}, "choix": "n_importe_quoi", "confirmer": True}
    assert client.post(f"{API}/double/{COURS}/lab-1", json=corps).status_code == 400


# --- Choix à l'import ----------------------------------------------------------------

def double_a_l_import(client):
    marie(client)
    (dossier(client.donnees, MARIE) / "annotations.json").write_text('{"pages": {"1": [{"id": "t"}, {"id": "u"}]}}', encoding="utf-8")
    return alice(client, ["Rapport", "Par Alice Dubé et Marie Roy"], remis="2026-09-19_08h00m00s")["en_attente"][0]["id"]


def test_comparaison_a_l_import(client):
    ident = double_a_l_import(client)
    r = client.get(f"{API}/attente/{ident}/double").json()
    existante, nouvelle = r["copies"]
    assert existante["id"] == MARIE and existante["travail"]["traits"] == 2
    assert nouvelle["id"] == ALICE and nouvelle["source"] == "attente" and nouvelle["remis_le"] == "2026-09-19T08:00:00"
    assert client.get(nouvelle["pdf"]).status_code == 200 and client.get(f"{API}/attente/inconnu/double").status_code == 404


def test_import_garder_l_existante(client):
    ident = double_a_l_import(client)
    assert api_attente(client, ident, "existante", confirmer=False).status_code == 409
    assert len(attente(client)) == 1
    assert api_attente(client, ident, "existante").status_code == 200
    assert attente(client) == [] and (client.donnees / "bibliotheque" / "_ecartes" / f"{ident}.pdf").is_file()
    s = suivi(client)
    assert [r["etudiant"] for r in s["rapports"]] == [MARIE] and s["rapports"][0]["equipe"] == ["Alice Dubé"]
    assert ALICE not in [n["id"] for n in s["non_remis"]] and s["doubles"] == []


def test_import_garder_la_nouvelle(client):
    ident = double_a_l_import(client)
    assert api_attente(client, ident, "nouvelle", confirmer=False).status_code == 409
    assert (dossier(client.donnees, MARIE) / "annotations.json").is_file()
    r = api_attente(client, ident, "nouvelle")
    assert r.status_code == 200, r.text
    assert not dossier(client.donnees, MARIE).exists() and (dossier(client.donnees, ALICE) / "rapport.pdf").is_file()
    mis = list((client.donnees / "bibliotheque" / "_remplaces").glob(f"{COURS}_{G}_lab-1_{MARIE}_*"))
    assert len(mis) == 1 and (mis[0] / "annotations.json").is_file()  # le travail de l'ancienne copie est récupérable
    s = suivi(client)
    assert [r["etudiant"] for r in s["rapports"]] == [ALICE] and s["rapports"][0]["equipe"] == ["Marie Roy"]
    assert MARIE not in [n["id"] for n in s["non_remis"]] and attente(client) == [] and s["doubles"] == []
    assert (dossier(client.donnees, ALICE) / "origine.json").is_file()


def test_import_garder_les_deux(client):
    ident = double_a_l_import(client)
    assert api_attente(client, ident, "les_deux", confirmer=False).status_code == 200  # rien n'est mis de côté
    s = suivi(client)
    assert sorted(r["etudiant"] for r in s["rapports"]) == [ALICE, MARIE] and all(r["equipe"] == [] for r in s["rapports"])
    assert s["doubles"] == [] and attente(client) == []
    assert not (client.donnees / "bibliotheque" / "_remplaces").exists()


def test_import_la_copie_existante_a_disparu(client):
    ident = double_a_l_import(client)
    import shutil
    shutil.rmtree(dossier(client.donnees, MARIE))
    assert api_attente(client, ident, "nouvelle").status_code == 409


def test_trancher_ordinaire_ne_range_pas_une_double_en_silence(client):
    marie(client)
    # un fichier au nom illisible, qui nomme Marie sur sa page titre, attribué à Alice à la main
    res = client.post(f"{API}/import", data={"cours": COURS, "groupe": "", "lab": "Lab 1"},
                      files=[("fichiers", ("scan_inconnu.pdf", pdf(["Par Alice Dubé et Marie Roy"]), "application/pdf"))]).json()
    ident = res["en_attente"][0]["id"]
    assert res["en_attente"][0]["raison"] == "aucune_correspondance"
    r = client.post(f"{API}/attente/{ident}", json={"etudiant": ALICE, "groupe": G})
    assert r.status_code == 200 and r.json().get("double") is True
    assert not dossier(client.donnees, ALICE).exists()
    fiche = attente(client)[0]
    assert fiche["raison"] == "double_remise" and fiche["double"]["existant"]["id"] == MARIE


def test_date_de_remise():
    assert date_de_remise("nom_2626310_Rapport_Remis_le_2026-09-18_17h43m16s.pdf") == "2026-09-18T17:43:16"
    assert date_de_remise("rapport.pdf") is None and date_de_remise(None) is None


def test_plagiat_ignore_toujours_l_equipe_apres_garder_les_deux_puis_se_compare(client):
    """Garder les deux retire le lien : le plagiat compare désormais les deux copies (deux rapports distincts)."""
    from moteur.plagiat import _meme_etudiant
    double_existante(client)
    x = {"cours": COURS, "groupe": G, "etudiant": ALICE, "lab": "lab-1", "equipe": [f"{G}/{MARIE}"]}
    y = {"cours": COURS, "groupe": G, "etudiant": MARIE, "lab": "lab-1"}
    assert _meme_etudiant(x, y)
    client.post(f"{API}/double/{COURS}/lab-1", json={"a": {"groupe": G, "id": ALICE}, "b": {"groupe": G, "id": MARIE}, "choix": "les_deux"})
    from moteur import plagiat
    rapports, _ = plagiat.charger_rapports()
    assert all(not r.ident.get("equipe") for r in rapports)
