from fastapi.testclient import TestClient

from moteur.app import creer_app


def test_etat(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path / "donnees"))
    r = TestClient(creer_app()).get("/api/etat")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (tmp_path / "donnees").is_dir()


def test_pwa_servie():
    c = TestClient(creer_app())
    assert "Correction de labs" in c.get("/").text
    assert c.get("/manifest.webmanifest").status_code == 200
