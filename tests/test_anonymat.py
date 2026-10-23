"""Tests de l'anonymiseur du cours entier. Noms et DA fictifs."""

import json

import pytest

from moteur.anonymat import Anonymiseur

COURS = "202SNURE_A2026"
GROUPE1 = [
    {"id": "bouchard-simon", "nom": "Bouchard", "prenom": "Simon", "da": "1000001"},
    {"id": "wu-li", "nom": "Wu", "prenom": "Li", "da": "1000002"},
    {"id": "roy-zoe", "nom": "Roy", "prenom": "Zoé", "da": "1000003"},
]
GROUPE2 = [
    {"id": "dube-alice", "nom": "Dubé", "prenom": "Alice", "da": "2000001"},
    {"id": "tremblay-cote-jean-francois", "nom": "Tremblay-Côté", "prenom": "Jean-François", "da": "2000002"},
    {"id": "levesque-lea", "nom": "Lévesque", "prenom": "Léa", "da": "2000003", "retire": True},
]


@pytest.fixture
def anon(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    for groupe, etudiants in (("00001", GROUPE1), ("00002", GROUPE2)):
        d = tmp_path / "bibliotheque" / COURS / groupe
        d.mkdir(parents=True)
        (d / "classe.json").write_text(json.dumps({"cours": COURS, "groupe": groupe, "etudiants": etudiants}),
                                       encoding="utf-8")
    # coéquipier absent des listes (équipe.json seulement)
    e = tmp_path / "bibliotheque" / COURS / "00002" / "lab1" / "dube-alice"
    e.mkdir(parents=True)
    (e / "equipe.json").write_text(json.dumps([{"id": "fortin-eloise", "groupe": "00003",
                                                "nom": "Fortin", "prenom": "Éloïse"}]), encoding="utf-8")
    return Anonymiseur.pour(COURS)


@pytest.mark.parametrize("texte, attendu", [
    # noms et prénoms de tous les groupes, accents, casse, composés
    ("Rapport de ALICE Dubé : la tension.", "Rapport de [PRÉNOM] [NOM] : la tension."),
    ("fait avec Simon Bouchard et BOUCHARD", "fait avec [PRÉNOM] [NOM] et [NOM]"),
    ("Jean-François Tremblay-Côté", "[PRÉNOM]-[PRÉNOM] [NOM]-[NOM]"),
    ("tremblay cote et Tremblay", "[NOM] [NOM] et [NOM]"),
    ("Lévesque (retirée) et Fortin, Éloïse", "[NOM] (retirée) et [NOM], [PRÉNOM]"),
    # sans séparateurs
    ("AliceDubé_SimonBouchard.pdf", "[PRÉNOM][NOM]_[PRÉNOM][NOM].pdf"),
    ("dube_alice et bouchardsimon", "[NOM]_[PRÉNOM] et [NOM][PRÉNOM]"),
    # DA connus et suites de 6 à 9 chiffres; les autres nombres restent
    ("DA 2000001, matricule 123456789, mesure 12345, 1234567890", "DA [DA], matricule [DA], mesure 12345, 1234567890"),
    # noms courts : majuscule et mot entier
    ("Roy a mesuré, ROY aussi, le roy de la tension", "[NOM] a mesuré, [NOM] aussi, le roy de la tension"),
    ("Royer et Zoé Roy", "Royer et [PRÉNOM] [NOM]"),
    # 2 lettres : seulement collé à un autre nom
    ("Wu Li a mesuré; Li, Wu aussi", "[NOM] [PRÉNOM] a mesuré; [PRÉNOM], [NOM] aussi"),
    ("Le lithium Li et le tungstène Wu sont distincts", "Le lithium Li et le tungstène Wu sont distincts"),
    # mots ordinaires intacts
    ("La tension mesurée est stable. Le de du la Roya", "La tension mesurée est stable. Le de du la Roya"),
])
def test_masquage(anon, texte, attendu):
    assert anon.masquer(texte) == attendu


def test_sans_liste_ne_masque_que_les_da(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    assert Anonymiseur.pour("999INCONNU").masquer("Alice 1234567") == "Alice [DA]"


def test_plusieurs_cours(tmp_path, monkeypatch, anon):
    d = tmp_path / "bibliotheque" / "203AUTRE" / "00001"
    d.mkdir(parents=True)
    (d / "classe.json").write_text(json.dumps({"cours": "203AUTRE", "groupe": "00001", "etudiants": [
        {"id": "x", "nom": "Ancien", "prenom": "Pierre"}]}), encoding="utf-8")
    a = Anonymiseur.pour(COURS, "203AUTRE")
    assert a.masquer("Pierre Ancien et Alice Dubé") == "[PRÉNOM] [NOM] et [PRÉNOM] [NOM]"
    assert anon.masquer("Pierre Ancien") == "Pierre Ancien"  # le cours seul ne connaît pas l'autre


def test_texte_vide_et_texte_original_intact(anon):
    original = "Alice Dubé"
    assert anon.masquer("") == ""
    anon.masquer(original)
    assert original == "Alice Dubé"
