"""Lance les tests JS de la fusion des annotations avec Node (ignorés si Node est absent)."""

import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node absent")
def test_fusion_lecteur_node():
    dossier = Path(__file__).parent / "js"
    r = subprocess.run([NODE, "--test", str(dossier / "annotations-fusion.test.js")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
