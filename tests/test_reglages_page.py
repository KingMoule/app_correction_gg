"""Garde-fou de la page Réglages : la page est servie, ses identifiants existent et la barre latérale y mène."""
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moteur.app import creer_app

PWA = Path(__file__).resolve().parent.parent / "pwa"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    return TestClient(creer_app())


def test_page_servie_et_identifiants_presents(client):
    r = client.get("/reglages.html")
    assert r.status_code == 200
    for ident in set(re.findall(r'el\("([\w-]+)"\)', (PWA / "reglages.js").read_text(encoding="utf-8"))):
        assert f'id="{ident}"' in r.text, ident


def test_lien_reglages_actif_dans_la_coque():
    coque = (PWA / "coque.js").read_text(encoding="utf-8")
    assert 'reglages.href = "reglages.html"' in coque
    assert "aria-disabled" not in coque
