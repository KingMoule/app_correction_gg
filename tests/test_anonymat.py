"""Tests du masquage des noms avant l'envoi à Claude. Noms fictifs."""

from moteur.anonymat import Anonymiseur


def anon():
    return Anonymiseur({"dube", "alice"}, {"gagnon", "tremblay"}, {"marc", "julie"})


def test_masque_le_nom_de_l_etudiant_sans_accents_ni_casse():
    assert anon().masquer("Rapport de ALICE Dubé : la tension.") == "Rapport de [NOM] [NOM] : la tension."


def test_masque_nom_des_autres_et_prenom_colle():
    t = "Fait avec Marc Gagnon et Tremblay. Marc a mesuré."
    assert anon().masquer(t) == "Fait avec [NOM] [NOM] et [NOM]. Marc a mesuré."


def test_texte_sans_nom_inchange():
    assert anon().masquer("La tension mesurée est stable.") == "La tension mesurée est stable."
