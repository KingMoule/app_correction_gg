"""Tests des annotations. Données fictives seulement."""

import json
import threading

import pytest
from tests.test_bibliotheque import charger_classe, client, importer, pdf  # noqa: F401

URL = "/api/annotations/202SNURE_A2026/00002/lab-3/dube-alice"

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
    assert r.json() == {"version": 2, "revision": 0, "pages": {}, "supprimes": []}


def test_aller_retour_et_fichier_a_cote_du_rapport(rapport, tmp_path):
    r = rapport.put(URL, json={"version": 2, "revision": 0, "pages": {"1": [{**TRAIT, "id": "t1"}], "2": []}})
    assert r.json() == {"ok": True, "traits": 1, "revision": 1}
    assert rapport.get(URL).json()["pages"] == {"1": [{**TRAIT, "id": "t1"}]}
    assert (tmp_path / "bibliotheque/202SNURE_A2026/00002/lab-3/dube-alice/annotations.json").is_file()


def test_rapport_inconnu(rapport):
    assert rapport.get("/api/annotations/202SNURE_A2026/00002/lab-3/personne").status_code == 404
    assert rapport.put("/api/annotations/202SNURE_A2026/00002/lab-9/dube-alice", json={}).status_code == 404


def test_segment_dangereux(rapport):
    assert rapport.get("/api/annotations/202SNURE_A2026/00002/lab-3/..%2F..").status_code in (400, 404)


@pytest.mark.parametrize("modif", [
    {"couleur": "rouge"}, {"outil": "stylo"}, {"points": []}, {"largeur_min": 0},
])
def test_trait_invalide(rapport, modif):
    r = rapport.put(URL, json={"version": 2, "pages": {"1": [{**TRAIT, **modif}]}})
    assert r.status_code == 422


# --- Révision, fusion entre appareils, migration (audit E2) ----------------------

DOSSIER = "bibliotheque/202SNURE_A2026/00002/lab-3/dube-alice"


def trait(id_, x=10):
    return {**TRAIT, "id": id_, "points": [[x, 20, 0.5]]}


def ids(doc):
    return sorted(t["id"] for traits in doc["pages"].values() for t in traits)


def fusion_comme_le_lecteur(client, local_pages, base_ids):
    """Ce que fait pwa/lecteur.js sur un 409 : union par identifiant moins les gommages, puis renvoi."""
    r = client.get(URL).json()
    deja = set(ids(r))
    presents = {t["id"] for ts in local_pages.values() for t in ts}
    effaces_ici = {i for i in base_ids if i not in presents}
    pages = {k: list(v) for k, v in r["pages"].items()}
    for k, traits in local_pages.items():
        for t in traits:
            if t["id"] not in deja and t["id"] not in r["supprimes"]:
                pages.setdefault(k, []).append(t)
    pages = {k: [t for t in v if t["id"] not in effaces_ici] for k, v in pages.items()}
    return client.put(URL, json={"version": 2, "revision": r["revision"], "pages": pages,
                                 "supprimes": sorted(effaces_ici)})


def test_deux_appareils_meme_page_aucun_trait_perdu(rapport):
    rapport.put(URL, json={"revision": 0, "pages": {"1": [trait("base")]}})
    assert rapport.get(URL).json()["revision"] == 1
    # l'iPad enregistre d'abord
    assert rapport.put(URL, json={"revision": 1, "pages": {"1": [trait("base"), trait("ipad")]}}).status_code == 200
    # le PC, resté à la révision 1, est refusé et reçoit le document actuel
    r = rapport.put(URL, json={"revision": 1, "pages": {"1": [trait("base"), trait("pc")]}})
    assert r.status_code == 409
    assert ids(r.json()["actuel"]) == ["base", "ipad"] and r.json()["actuel"]["revision"] == 2
    # fusion puis renvoi : rien n'est perdu
    assert fusion_comme_le_lecteur(rapport, {"1": [trait("base"), trait("pc")]}, ["base"]).status_code == 200
    final = rapport.get(URL).json()
    assert ids(final) == ["base", "ipad", "pc"] and final["revision"] == 3


def test_gommage_sur_un_appareil_pendant_qu_un_autre_ajoute(rapport):
    rapport.put(URL, json={"revision": 0, "pages": {"1": [trait("a"), trait("b")]}})
    # le PC gomme « a » (enregistré), l'iPad ajoute « c » sans le savoir
    assert rapport.put(URL, json={"revision": 1, "pages": {"1": [trait("b")]}, "supprimes": ["a"]}).status_code == 200
    assert rapport.put(URL, json={"revision": 1, "pages": {"1": [trait("a"), trait("b"), trait("c")]}}).status_code == 409
    assert fusion_comme_le_lecteur(rapport, {"1": [trait("a"), trait("b"), trait("c")]}, ["a", "b"]).status_code == 200
    final = rapport.get(URL).json()
    assert ids(final) == ["b", "c"] and final["supprimes"] == ["a"]  # « a » ne ressuscite pas


def test_gommage_non_enregistre_survit_a_un_ajout_ailleurs(rapport):
    rapport.put(URL, json={"revision": 0, "pages": {"1": [trait("a")]}})
    rapport.put(URL, json={"revision": 1, "pages": {"1": [trait("a"), trait("c")]}})  # l'autre appareil ajoute « c »
    # cet appareil avait gommé « a » : 409, fusion, « a » reste effacé et « c » est gardé
    assert rapport.put(URL, json={"revision": 1, "pages": {}, "supprimes": ["a"]}).status_code == 409
    assert fusion_comme_le_lecteur(rapport, {}, ["a"]).status_code == 200
    assert ids(rapport.get(URL).json()) == ["c"]


def test_annuler_un_gommage_deja_enregistre_retire_la_pierre_tombale(rapport):
    rapport.put(URL, json={"revision": 0, "pages": {"1": [trait("a")]}})
    rapport.put(URL, json={"revision": 1, "pages": {}, "supprimes": ["a"]})
    assert rapport.get(URL).json()["supprimes"] == ["a"]
    rapport.put(URL, json={"revision": 2, "pages": {"1": [trait("a")]}})  # « annuler » : le trait revient
    doc = rapport.get(URL).json()
    assert ids(doc) == ["a"] and doc["supprimes"] == []


def test_ecritures_simultanees_une_seule_gagne_par_revision(rapport):
    codes = []
    barriere = threading.Barrier(4)

    def ecrire(n):
        barriere.wait()
        codes.append(rapport.put(URL, json={"revision": 0, "pages": {"1": [trait(f"t{n}")]}}).status_code)

    fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(4)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert sorted(codes) == [200, 409, 409, 409]
    assert rapport.get(URL).json()["revision"] == 1


def test_revision_absente_comptee_zero(rapport):
    rapport.put(URL, json={"pages": {"1": [trait("a")]}})
    assert rapport.put(URL, json={"pages": {"1": [trait("b")]}}).status_code == 409  # ancien client : pas d'écrasement


def ecrire_v1(tmp_path, contenu):
    f = tmp_path / DOSSIER / "annotations.json"
    f.write_text(json.dumps(contenu), encoding="utf-8")
    return f


def test_migration_version_1(rapport, tmp_path):
    ecrire_v1(tmp_path, {"version": 1, "pages": {"1": [TRAIT, {**TRAIT, "couleur": "#1976d2"}], "3": [TRAIT]}})
    doc = rapport.get(URL).json()
    assert doc["version"] == 2 and doc["revision"] == 0 and doc["supprimes"] == []
    assert ids(doc) == ["p1-0", "p1-1", "p3-0"]
    assert rapport.get(URL).json() == doc  # identifiants stables d'un chargement à l'autre (deux appareils)
    # le premier enregistrement (révision 0) passe et écrit la version 2
    assert rapport.put(URL, json={"revision": 0, "pages": doc["pages"]}).json()["revision"] == 1
    sur_disque = json.loads((tmp_path / DOSSIER / "annotations.json").read_text("utf-8"))
    assert sur_disque["version"] == 2 and sur_disque["revision"] == 1


def test_export_identique_apres_migration(rapport, tmp_path):
    from tests.test_export import URL_EXPORT, pixels_colores

    ecrire_v1(tmp_path, {"version": 1, "pages": {"1": [TRAIT]}})
    avant = rapport.get(URL_EXPORT).content
    doc = rapport.get(URL).json()
    rapport.put(URL, json={"revision": 0, "pages": doc["pages"]})  # migre le fichier en version 2
    apres = rapport.get(URL_EXPORT).content
    zone = (8, 18, 20, 40)
    assert pixels_colores(avant, zone) and pixels_colores(avant, zone) == pixels_colores(apres, zone)


def morceau(id_, x0, x1):
    return {**TRAIT, "id": id_, "points": [[x0, 20, 0.5], [x1, 20, 0.5]]}


def test_trait_coupe_sur_un_appareil_pendant_qu_un_autre_ajoute(rapport):
    """Gomme partielle : l'original passe en pierre tombale, deux morceaux le remplacent; l'ajout de l'autre appareil reste."""
    rapport.put(URL, json={"revision": 0, "pages": {"1": [morceau("a", 0, 100)]}})
    rapport.put(URL, json={"revision": 1, "pages": {"1": [morceau("a", 0, 100), trait("pc")]}})  # le PC ajoute « pc »
    # l'iPad coupe « a » en « a1 » et « a2 » à partir de la révision 1 : 409, fusion, rien de perdu
    coupe = {"1": [morceau("a1", 0, 40), morceau("a2", 60, 100)]}
    assert rapport.put(URL, json={"revision": 1, "pages": coupe, "supprimes": ["a"]}).status_code == 409
    assert fusion_comme_le_lecteur(rapport, coupe, ["a"]).status_code == 200
    final = rapport.get(URL).json()
    assert ids(final) == ["a1", "a2", "pc"] and final["supprimes"] == ["a"]


def test_trait_coupe_des_deux_cotes_ne_ressuscite_pas_l_original(rapport):
    rapport.put(URL, json={"revision": 0, "pages": {"1": [morceau("a", 0, 100)]}})
    # le PC coupe d'abord (enregistré), puis l'iPad coupe le même trait autrement
    rapport.put(URL, json={"revision": 1, "pages": {"1": [morceau("pc1", 0, 30), morceau("pc2", 50, 100)]}, "supprimes": ["a"]})
    ipad = {"1": [morceau("ip1", 0, 60), morceau("ip2", 80, 100)]}
    assert rapport.put(URL, json={"revision": 1, "pages": ipad, "supprimes": ["a"]}).status_code == 409
    assert fusion_comme_le_lecteur(rapport, ipad, ["a"]).status_code == 200
    final = rapport.get(URL).json()
    assert "a" not in ids(final) and final["supprimes"] == ["a"]
    assert ids(final) == ["ip1", "ip2", "pc1", "pc2"]  # les deux coupes sont gardées, aucun trait perdu
