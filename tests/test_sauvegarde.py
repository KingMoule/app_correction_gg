"""Sauvegarde, rotation et restauration (données fictives seulement)."""

import json
import zipfile
from datetime import datetime, timedelta

import pytest

from moteur import sauvegarde as sv


@pytest.fixture
def donnees(tmp_path):
    d = tmp_path / "donnees"
    (d / "bibliotheque" / "COURS1" / "lab1" / "etudiant1").mkdir(parents=True)
    (d / "bibliotheque" / "COURS1" / "lab1" / "etudiant1" / "rapport.pdf").write_bytes(b"%PDF-fictif")
    (d / "bibliotheque" / "COURS1" / "lab1" / "etudiant1" / "annotations.json").write_text(
        json.dumps({"traits": [1, 2, 3]}), encoding="utf-8")
    (d / "lexique.json").write_text(json.dumps(["mot"]), encoding="utf-8")
    (d / "plagiat" / "textes").mkdir(parents=True)
    (d / "plagiat" / "textes" / "cache.json").write_text("{}", encoding="utf-8")
    (d / "plagiat" / "decisions.json").write_text("{}", encoding="utf-8")
    return d


def noms(archive):
    with zipfile.ZipFile(archive) as z:
        return set(z.namelist())


def test_sauvegarde_contenu_et_exclusions(donnees, tmp_path):
    dest = tmp_path / "sauvegardes"
    archive = sv.sauvegarder(donnees, dest, datetime(2026, 10, 20, 9, 30, 0))
    assert archive.name == "sauvegarde_20261020-093000.zip"
    n = noms(archive)
    assert "lexique.json" in n
    assert "bibliotheque/COURS1/lab1/etudiant1/rapport.pdf" in n
    assert "plagiat/decisions.json" in n
    assert not any(x.startswith("plagiat/textes") for x in n)
    assert not list(dest.glob("*.tmp"))  # fichier temporaire renommé


def test_donnees_intactes_apres_sauvegarde(donnees, tmp_path):
    avant = {p: p.read_bytes() for p in donnees.rglob("*") if p.is_file()}
    sv.sauvegarder(donnees, tmp_path / "s")
    sv.appliquer_rotation(tmp_path / "s")
    assert {p: p.read_bytes() for p in donnees.rglob("*") if p.is_file()} == avant


def test_destination_dans_les_donnees_refusee(donnees):
    with pytest.raises(sv.SauvegardeErreur):
        sv.sauvegarder(donnees, donnees / "sauvegardes")


def test_aucune_donnee(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    with pytest.raises(sv.SauvegardeErreur):
        sv.sauvegarder(vide, tmp_path / "s")


def test_echec_ne_laisse_pas_de_fichier_partiel(donnees, tmp_path, monkeypatch):
    dest = tmp_path / "s"

    def casse(self, *a, **k):
        raise OSError("disque plein")
    monkeypatch.setattr(zipfile.ZipFile, "writestr", casse)
    with pytest.raises(sv.SauvegardeErreur):
        sv.sauvegarder(donnees, dest)
    assert list(dest.iterdir()) == []


def test_json_a_moitie_ecrit_est_relu(tmp_path, monkeypatch):
    f = tmp_path / "a.json"
    f.write_text('{"x": ', encoding="utf-8")
    monkeypatch.setattr(sv.time, "sleep", lambda s: f.write_text('{"x": 1}', encoding="utf-8"))
    assert json.loads(sv._lire_coherent(f)) == {"x": 1}


def test_meme_seconde_ne_remplace_pas(donnees, tmp_path):
    t = datetime(2026, 10, 20, 9, 30, 0)
    a = sv.sauvegarder(donnees, tmp_path / "s", t)
    b = sv.sauvegarder(donnees, tmp_path / "s", t)
    assert a != b and a.exists() and b.exists()


def test_rotation_10_recentes_plus_une_par_semaine(tmp_path):
    dest = tmp_path / "s"
    dest.mkdir()
    debut = datetime(2026, 1, 5, 8, 0)  # un lundi
    # 3 archives par jour pendant 120 jours
    for j in range(120):
        for h in range(3):
            t = debut + timedelta(days=j, hours=h)
            (dest / f"sauvegarde_{t:%Y%m%d-%H%M%S}.zip").write_bytes(b"x")
    autre = dest / "notes_perso.zip"
    autre.write_bytes(b"x")
    sv.appliquer_rotation(dest)
    restes = sv.lister(dest)
    assert len(restes) <= sv.GARDER_RECENTES + sv.GARDER_SEMAINES
    assert len(restes) >= sv.GARDER_RECENTES
    dates = [d for d, _ in restes]
    assert dates[0] == debut + timedelta(days=119, hours=2)  # la plus récente est gardée
    semaines = {d.isocalendar()[:2] for d in dates}
    assert len(semaines) >= sv.GARDER_SEMAINES  # une archive pour chacune des 8 dernières semaines
    assert autre.exists()  # un fichier qui n'est pas une sauvegarde n'est jamais touché


def test_rotation_peu_d_archives_rien_retire(tmp_path):
    dest = tmp_path / "s"
    dest.mkdir()
    for j in range(5):
        (dest / f"sauvegarde_2026010{j + 1}-080000.zip").write_bytes(b"x")
    assert sv.appliquer_rotation(dest) == []


def test_restauration_dossier_neuf(donnees, tmp_path):
    archive = sv.sauvegarder(donnees, tmp_path / "s")
    cible = tmp_path / "restaure"
    assert sv.restaurer(archive, cible) is None
    assert (cible / "lexique.json").read_bytes() == (donnees / "lexique.json").read_bytes()
    assert (cible / "bibliotheque/COURS1/lab1/etudiant1/rapport.pdf").read_bytes() == b"%PDF-fictif"
    assert not (cible / "plagiat" / "textes").exists()


def test_restauration_sans_ecraser(donnees, tmp_path):
    archive = sv.sauvegarder(donnees, tmp_path / "s")
    with pytest.raises(FileExistsError):
        sv.restaurer(archive, donnees)  # sans confirmation : refus
    assert (donnees / "lexique.json").exists()


def test_restauration_met_l_actuel_de_cote(donnees, tmp_path):
    archive = sv.sauvegarder(donnees, tmp_path / "s")
    (donnees / "lexique.json").write_text('["nouveau"]', encoding="utf-8")
    ancien = sv.restaurer(archive, donnees, remplacer=True)
    assert json.loads((donnees / "lexique.json").read_text(encoding="utf-8")) == ["mot"]
    assert ancien.exists() and "_avant_restauration_" in ancien.name
    assert json.loads((ancien / "lexique.json").read_text(encoding="utf-8")) == ["nouveau"]


def test_restauration_refuse_chemin_hors_dossier(tmp_path):
    mauvaise = tmp_path / "mauvaise.zip"
    with zipfile.ZipFile(mauvaise, "w") as z:
        z.writestr("../evade.txt", "x")
    with pytest.raises(sv.SauvegardeErreur):
        sv.restaurer(mauvaise, tmp_path / "cible")
    assert not (tmp_path / "evade.txt").exists()
    assert not (tmp_path / "cible").exists()
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".restauration")]


def test_dossier_sauvegardes_par_defaut_et_variable(tmp_path, monkeypatch):
    monkeypatch.delenv("CORRECTION_SAUVEGARDES", raising=False)
    assert sv.dossier_sauvegardes(tmp_path / "correction_donnees") == tmp_path / "correction_donnees_sauvegardes"
    monkeypatch.setenv("CORRECTION_SAUVEGARDES", str(tmp_path / "ailleurs"))
    assert sv.dossier_sauvegardes(tmp_path / "x") == tmp_path / "ailleurs"


def test_commande_auto_et_statut(donnees, tmp_path, capsys):
    dest = tmp_path / "s"
    assert sv.main(["auto", "--donnees", str(donnees), "--destination", str(dest)]) == 0
    sortie = capsys.readouterr().out
    assert "Sauvegarde faite" in sortie and "Dernière sauvegarde" in sortie
    assert sv.derniere_sauvegarde(dest) is not None


def test_commande_auto_ne_bloque_pas_si_echec(donnees, tmp_path, capsys):
    fichier = tmp_path / "pas_un_dossier"
    fichier.write_text("x")
    assert sv.main(["auto", "--donnees", str(donnees), "--destination", str(fichier / "sous")]) == 0
    assert "SAUVEGARDE ECHOUEE" in capsys.readouterr().err


def test_commande_restaurer_refuse_sans_confirmation(donnees, tmp_path, monkeypatch, capsys):
    dest = tmp_path / "s"
    sv.sauvegarder(donnees, dest)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    code = sv.main(["restaurer", "--destination", str(dest), "--cible", str(donnees)])
    assert code == 1 and "annulée" in capsys.readouterr().out
    assert (donnees / "lexique.json").exists()
