"""Les tests existants appellent l'API sans session : par défaut, le code d'accès est désactivé et l'hôte
`testserver` du TestClient est permis. `tests/test_acces.py` remet le vrai comportement (fixture `avec_code`)."""
import pytest

from moteur import acces


@pytest.fixture(autouse=True)
def _sans_code_par_defaut(monkeypatch):
    monkeypatch.setenv("CORRECTION_SANS_CODE", "1")
    monkeypatch.setenv("CORRECTION_HOTES", "testserver")
    monkeypatch.setenv("CORRECTION_SESSION", "A2026")  # session par défaut des listes importées sans session
    acces.limiteur.reinitialiser()
    yield
    acces.limiteur.reinitialiser()
