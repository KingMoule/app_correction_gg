"""Tests JavaScript de la PWA (audit C2) : lancés avec Node s'il est installé, sinon ignorés avec un message."""
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS = sorted(Path(__file__).parent.glob("test_*.js"))


@pytest.mark.parametrize("fichier", TESTS, ids=lambda f: f.name)
def test_js(fichier):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent : les tests JavaScript de la PWA ne sont pas lancés (installer Node pour les exécuter).")
    r = subprocess.run([node, "--test", str(fichier)], capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
