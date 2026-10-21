"""Tests de `moteur/stockage.py` : écriture atomique, lecture tolérante, concurrence. Données fictives seulement."""

import json
import logging
import os
import threading
from pathlib import Path

import pytest
from moteur import stockage
from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: F401

COURS, GROUPE, LAB, ETUDIANT = "202SNURE", "00002", "lab-3", "dube-alice"
ANNOT = f"/api/annotations/{COURS}/{GROUPE}/{LAB}/{ETUDIANT}"
TRONQUE = '{"decisions": {"3": "accep'


@pytest.fixture
def rapport(client, tmp_path):
    charger_classe(client)
    importer(client, [("Rapport_DUBE.pdf", pdf())])
    return client, tmp_path / "bibliotheque" / COURS / GROUPE / LAB / ETUDIANT


# --- Écriture et lecture ------------------------------------------------------

def test_aller_retour_utf8(tmp_path):
    f = tmp_path / "a.json"
    stockage.ecrire_json(f, {"nom": "Élève Zoé", "n": [1, 2]})
    assert json.loads(f.read_text(encoding="utf-8")) == {"nom": "Élève Zoé", "n": [1, 2]}
    assert stockage.lire_json(f) == {"nom": "Élève Zoé", "n": [1, 2]}


def test_ecrire_cree_le_dossier_et_ne_laisse_aucun_temporaire(tmp_path):
    f = tmp_path / "x" / "y" / "a.json"
    stockage.ecrire_json(f, [1])
    stockage.ecrire_json(f, [2])
    assert sorted(p.name for p in f.parent.iterdir()) == ["a.json"]


def test_echec_d_ecriture_garde_l_ancien_fichier(tmp_path):
    f = tmp_path / "a.json"
    stockage.ecrire_json(f, {"v": 1})
    with pytest.raises(TypeError):
        stockage.ecrire_json(f, {"v": object()})  # non sérialisable : rien n'est touché
    assert stockage.lire_json(f) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["a.json"]


def test_lecture_absent_tronque_et_vide(tmp_path, caplog):
    assert stockage.lire_json(tmp_path / "absent.json", []) == []
    f = tmp_path / "a.json"
    for contenu in (TRONQUE.encode(), b"", b"\xff\xfe\x00"):
        f.write_bytes(contenu)
        with caplog.at_level(logging.WARNING, logger="moteur.stockage"):
            assert stockage.lire_json(f, {"defaut": True}) == {"defaut": True}
    assert "abîmé" in caplog.text


def test_lecture_accepte_un_bom(tmp_path):
    f = tmp_path / "a.json"
    f.write_bytes(b"\xef\xbb\xbf" + json.dumps({"a": 1}).encode())
    assert stockage.lire_json(f) == {"a": 1}


def test_nouvel_essai_sur_permission_error(tmp_path, monkeypatch):
    """Sous Windows, os.replace échoue tant qu'un lecteur tient le fichier : on réessaie."""
    f = tmp_path / "a.json"
    vrai, appels = os.replace, []

    def capricieux(src, dst):
        appels.append(1)
        if len(appels) < 4:
            raise PermissionError(5, "Accès refusé")
        return vrai(src, dst)

    monkeypatch.setattr(stockage.os, "replace", capricieux)
    monkeypatch.setattr(stockage, "ATTENTE", 0)
    stockage.ecrire_json(f, {"ok": True})
    assert len(appels) == 4 and stockage.lire_json(f) == {"ok": True}


def test_permission_error_persistante_remonte_et_nettoie(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    monkeypatch.setattr(stockage.os, "replace", lambda *a: (_ for _ in ()).throw(PermissionError(5, "refusé")))
    monkeypatch.setattr(stockage, "ATTENTE", 0)
    with pytest.raises(PermissionError):
        stockage.ecrire_json(f, {"ok": True})
    assert list(tmp_path.iterdir()) == []


def test_verrou_par_dossier_est_reentrant_et_partage(tmp_path):
    assert stockage.verrou(tmp_path) is stockage.verrou(str(tmp_path))
    assert stockage.verrou(tmp_path) is not stockage.verrou(tmp_path / "autre")
    with stockage.verrou(tmp_path), stockage.verrou(tmp_path):
        stockage.ecrire_json(tmp_path / "a.json", 1)


# --- Concurrence --------------------------------------------------------------

def lancer(fils: int, travail) -> list[BaseException]:
    erreurs: list[BaseException] = []

    def corps(n):
        try:
            travail(n)
        except BaseException as e:  # noqa: BLE001
            erreurs.append(e)

    ts = [threading.Thread(target=corps, args=(n,)) for n in range(fils)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return erreurs


def test_ecritures_et_lectures_simultanees_du_meme_fichier(tmp_path):
    """Scénario de l'audit (E1) : 4 fils × 30 écritures, avec des lecteurs en parallèle."""
    f = tmp_path / "annotations.json"
    stockage.ecrire_json(f, {"n": -1, "bourrage": "é" * 5000})
    arret = threading.Event()
    lus = []

    def lecteur():
        while not arret.is_set():
            lus.append(stockage.lire_json(f, "ABIME"))

    lect = [threading.Thread(target=lecteur) for _ in range(2)]
    [t.start() for t in lect]
    erreurs = lancer(4, lambda n: [stockage.ecrire_json(f, {"n": n * 100 + i, "bourrage": "é" * 5000})
                                   for i in range(30)])
    arret.set()
    [t.join() for t in lect]
    assert erreurs == []
    assert lus and "ABIME" not in lus  # jamais de fichier à moitié écrit
    assert stockage.lire_json(f)["n"] in {n * 100 + 29 for n in range(4)}
    assert [p.name for p in tmp_path.iterdir()] == ["annotations.json"]


def test_modifier_json_ne_perd_aucun_ajout(tmp_path):
    """Lecture-modification-écriture : 8 fils ajoutent chacun 10 mots, aucun n'est perdu (F5)."""
    f = tmp_path / "lexique.json"
    erreurs = lancer(8, lambda n: [stockage.modifier_json(f, lambda m: m + [f"m{n}-{i}"], []) for i in range(10)])
    assert erreurs == []
    assert len(stockage.lire_json(f)) == 80


def test_lexique_sans_perte_en_parallele(client):
    from moteur import francais_filtre
    erreurs = lancer(6, lambda n: [client.post("/api/francais/lexique", json={"mot": f"mot{n}x{i}"}) for i in range(5)])
    assert erreurs == []
    assert len(francais_filtre.lire_lexique()) == 30


def test_put_annotations_concurrents_sans_erreur(rapport):
    """4 fils × 30 PUT d'annotations pendant des GET : aucune erreur 500 (E1)."""
    client, _ = rapport
    trait = {"outil": "crayon", "couleur": "#d32f2f", "largeur_min": 0.6, "largeur_max": 3.8,
             "courbe": 1, "points": [[1, 2, 0.5]]}
    statuts = []

    def travail(n):
        for i in range(30):
            statuts.append(client.put(ANNOT, json={"version": 1, "pages": {"1": [trait] * (n + 1)}}).status_code)
            statuts.append(client.get(ANNOT).status_code)

    assert lancer(4, travail) == []
    assert len(statuts) == 240 and set(statuts) == {200}


def test_statut_et_note_concurrents(rapport):
    client, _ = rapport
    url = f"/api/bibliotheque/statut/{COURS}/{GROUPE}/{LAB}/{ETUDIANT}"
    client.put(url, json={"termine": False, "note": "17/20"})
    codes = []
    assert lancer(4, lambda n: [codes.append(client.put(url, json={"termine": bool(i % 2)}).status_code)
                                for i in range(20)]) == []
    assert set(codes) == {200}
    assert client.put(url, json={"termine": True}).json()["note"] == "17/20"  # la note n'a pas été perdue


# --- Fichier tronqué pour chaque lecteur (E3) ----------------------------------

def abimer(f: Path) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(TRONQUE, encoding="utf-8")


def test_annotations_tronquees(rapport):
    client, d = rapport
    abimer(d / "annotations.json")
    assert client.get(ANNOT).json() == {"version": 1, "pages": {}}


def test_francais_tronque(rapport):
    client, d = rapport
    abimer(d / "francais.json")
    r = client.get(f"/api/francais/rapport/{COURS}/{GROUPE}/{LAB}/{ETUDIANT}")
    assert r.status_code == 200 and r.json()["analyse"] is False
    r = client.put(f"/api/francais/rapport/{COURS}/{GROUPE}/{LAB}/{ETUDIANT}", json={})
    assert r.status_code == 409  # à réanalyser, pas de 500


def test_bareme_et_lexique_tronques(rapport, tmp_path):
    client, _ = rapport
    abimer(tmp_path / "bibliotheque" / COURS / "bareme.json")
    assert client.get(f"/api/francais/bareme/{COURS}").status_code == 200
    from moteur import francais_filtre
    abimer(francais_filtre.fichier_lexique())
    assert client.get("/api/francais/lexique").json() == {"mots": []}


def test_indices_ia_tronque(rapport):
    client, d = rapport
    abimer(d / "indices_ia.json")
    r = client.get(f"/api/indices-ia/resultat/{COURS}/{GROUPE}/{LAB}/{ETUDIANT}")
    assert r.status_code == 200 and r.json() is None


@pytest.mark.parametrize("nom", ["statut.json", "equipe.json", "origine.json", "francais.json", "indices_ia.json"])
def test_fichiers_du_rapport_tronques_ne_cassent_ni_arbre_ni_suivi_ni_export(rapport, nom):
    client, d = rapport
    abimer(d / nom)
    assert client.get("/api/bibliotheque").status_code == 200
    assert client.get(f"/api/suivi/{COURS}/{LAB}").status_code == 200
    assert client.get(f"/api/export-lot/apercu/{COURS}/{LAB}").status_code == 200
    assert client.get(f"/api/export-lot/tableau/{COURS}/{LAB}").status_code in (200, 404, 409)


@pytest.mark.parametrize("nom", ["decisions.json", "paires.json", "reglages.json"])
def test_fichiers_plagiat_tronques(rapport, tmp_path, nom):
    client, _ = rapport
    abimer(tmp_path / "plagiat" / nom)
    assert client.get("/api/plagiat/paires").status_code == 200
    assert client.get("/api/plagiat/reglages").status_code == 200
    assert client.get(f"/api/suivi/{COURS}/{LAB}").status_code == 200
    assert client.get(f"/api/export-lot/apercu/{COURS}/{LAB}").status_code == 200


def test_classe_tronquee_ne_casse_pas_l_arbre(rapport, tmp_path):
    client, _ = rapport
    abimer(tmp_path / "bibliotheque" / COURS / GROUPE / "classe.json")
    assert client.get("/api/bibliotheque").status_code == 200
    assert client.get(f"/api/suivi/{COURS}/{LAB}").status_code == 404  # groupe introuvable : message clair, pas de 500
    from moteur import bibliotheque
    with pytest.raises(bibliotheque.HTTPException) as e:
        bibliotheque.charger_classe(COURS, GROUPE)
    assert e.value.status_code == 422 and "réimporter" in e.value.detail


def test_fiche_en_attente_tronquee(rapport, tmp_path):
    client, _ = rapport
    dossier = tmp_path / "bibliotheque" / "_attente"
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "abc.pdf").write_bytes(pdf())
    abimer(dossier / "abc.json")
    assert client.get("/api/bibliotheque/attente").json() == []
    r = client.post("/api/bibliotheque/trancher/abc", json={})
    assert r.status_code in (404, 405, 422)
