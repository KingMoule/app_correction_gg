"""Tests des annotations. Données fictives seulement."""

import pytest
from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: F401

URL = "/api/annotations/202SNURE/00002/lab-3/dube-alice"

TRAIT = {
    "outil": "crayon", "couleur": "#d32f2f", "largeur_min": 0.6, "largeur_max": 3.8,
    "courbe": 1, "points": [[10, 20, 0.3], [12.5, 22, 0.6], [15, 30, 0.9]],
}


@pytest.fixture
def rapport(client):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf())])
    return client


def test_vide_par_defaut(rapport):
    r = rapport.get(URL)
    assert r.status_code == 200
    assert r.json() == {"version": 1, "pages": {}}


def test_aller_retour_et_fichier_a_cote_du_rapport(rapport, tmp_path):
    r = rapport.put(URL, json={"version": 1, "pages": {"1": [TRAIT], "2": []}})
    assert r.json() == {"ok": True, "traits": 1}
    assert rapport.get(URL).json()["pages"] == {"1": [TRAIT]}
    assert (tmp_path / "bibliotheque/202SNURE/00002/lab-3/dube-alice/annotations.json").is_file()


def test_rapport_inconnu(rapport):
    assert rapport.get("/api/annotations/202SNURE/00002/lab-3/personne").status_code == 404
    assert rapport.put("/api/annotations/202SNURE/00002/lab-9/dube-alice", json={}).status_code == 404


def test_segment_dangereux(rapport):
    assert rapport.get("/api/annotations/202SNURE/00002/lab-3/..%2F..").status_code in (400, 404)


@pytest.mark.parametrize("modif", [
    {"couleur": "rouge"}, {"outil": "stylo"}, {"points": []}, {"largeur_min": 0},
])
def test_trait_invalide(rapport, modif):
    r = rapport.put(URL, json={"version": 1, "pages": {"1": [{**TRAIT, **modif}]}})
    assert r.status_code == 422
