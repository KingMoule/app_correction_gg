"""Fiche d'un étudiant (`GET /api/etudiant/<cours>/<groupe>/<id>`). Bibliothèque fictive seulement."""

import json

from tests.test_bibliotheque import client  # noqa: F401
from tests.test_export_lot import COURS, lab  # noqa: F401


def test_fiche_rapports_etat_note_et_equipe(lab):
    client, _ = lab
    f = client.get(f"/api/etudiant/{COURS}/00002/dube-alice").json()
    assert (f["nom"], f["prenom"], f["da"], f["cours"], f["groupe"], f["retire"]) == ("Dubé", "Alice", "2000001", COURS, "00002", False)
    (r,) = f["rapports"]
    assert (r["lab"], r["etat"], r["note"], r["par_equipe"]) == ("lab-1", "termine", "17,5", False)
    assert [(m["id"], m["groupe"]) for m in r["equipe"]] == [("bele-gombos-anna", "00001")]
    assert f["historique"] == {"remplaces": [], "ecartes": []}


def test_fiche_d_un_coequipier_couvert_par_le_rapport_d_un_autre(lab):
    client, _ = lab
    f = client.get(f"/api/etudiant/{COURS}/00001/bele-gombos-anna").json()
    (r,) = f["rapports"]
    assert (r["lab"], r["par_equipe"], r["etudiant"], r["groupe"]) == ("lab-1", True, "dube-alice", "00002")
    assert r["note"] == "17,5" and r["etat"] == "termine"
    assert [m["id"] for m in r["equipe"]] == ["dube-alice"]


def test_fiche_sans_rapport_et_etudiant_inconnu(lab):
    client, _ = lab
    assert client.get(f"/api/etudiant/{COURS}/00001/bele-gombos-anna").status_code == 200
    assert client.get(f"/api/etudiant/{COURS}/00001/personne").status_code == 404
    assert client.get(f"/api/etudiant/{COURS}/00009/dube-alice").status_code == 404
    assert client.get(f"/api/etudiant/{COURS}/00002/..%2Fx").status_code in (400, 404)


def test_historique_remplaces_et_ecartes(lab):
    client, tmp = lab
    biblio = tmp / "bibliotheque"
    (biblio / "_remplaces" / f"{COURS}_00002_lab-1_dube-alice_20261009-142530").mkdir(parents=True)
    (biblio / "_remplaces" / f"{COURS}_00002_lab-1_dube-alice_20261010-101010-2").mkdir()
    (biblio / "_remplaces" / f"{COURS}_00002_lab-2_martin-zoe_20261009-142530").mkdir()  # une autre personne
    (biblio / "_ecartes").mkdir()
    (biblio / "_ecartes" / "a1.json").write_text(json.dumps({"id": "a1", "fichier": "Dube_Rapport.pdf", "cours": COURS, "groupe": None,
        "lab": "lab-2", "raison": "ambigu", "da": None, "candidats": [{"id": "dube-alice", "groupe": "00002"}]}), encoding="utf-8")
    (biblio / "_ecartes" / "a2.json").write_text(json.dumps({"id": "a2", "fichier": "autre.pdf", "cours": COURS, "da": "2000001",
        "lab": "lab-3", "candidats": []}), encoding="utf-8")
    (biblio / "_ecartes" / "a3.json").write_text(json.dumps({"id": "a3", "fichier": "zoe.pdf", "cours": COURS, "da": "2000002",
        "lab": "lab-3", "candidats": []}), encoding="utf-8")
    h = client.get(f"/api/etudiant/{COURS}/00002/dube-alice").json()["historique"]
    assert [(x["lab"], x["date"]) for x in h["remplaces"]] == [("lab-1", "2026-10-09T14:25:30"), ("lab-1", "2026-10-10T10:10:10")]
    assert sorted(x["fichier"] for x in h["ecartes"]) == ["Dube_Rapport.pdf", "autre.pdf"]
    assert client.get(f"/api/etudiant/{COURS}/00002/martin-zoe").json()["historique"]["remplaces"] == [{"lab": "lab-2", "date": "2026-10-09T14:25:30"}]
