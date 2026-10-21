"""Avertissement sur le dossier de données (audit M6)."""

from moteur.config import RACINE, chemin_a_risque


def test_dossier_dans_le_depot_est_a_risque():
    assert chemin_a_risque(RACINE / "donnees") == "dans le dépôt Git"


def test_dossier_sous_onedrive_est_a_risque(tmp_path):
    assert chemin_a_risque(tmp_path / "OneDrive" / "donnees") == "dans OneDrive"


def test_dossier_hors_depot_et_hors_onedrive_est_sur(tmp_path):
    assert chemin_a_risque(tmp_path / "correction_donnees") is None
