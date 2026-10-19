"""Tests de moteur/claude.py avec un faux exécutable `claude` (aucun appel réel)."""

import json
import sys
import time

import pytest

from moteur.claude import (
    ClaudeDelai,
    ClaudeEchec,
    ClaudeIntrouvable,
    ClaudeLimite,
    ClaudeNonConnecte,
    ClaudeSortieInvalide,
    ClientClaude,
    FileClaude,
)

FAUX = """#!{python}
import json, os, sys, time
mode = os.environ.get("FAUX_MODE", "ok")
entree = sys.stdin.read()
args = sys.argv[1:]
if mode == "ok":
    d = {{"type": "result", "is_error": False, "result": "recu:" + entree,
         "usage": {{"input_tokens": 10, "output_tokens": 5}}, "total_cost_usd": 0.01,
         "duration_ms": 12, "session_id": "s1", "args": args,
         "cle_api_presente": "ANTHROPIC_API_KEY" in os.environ}}
    if "--json-schema" in args:
        d["structured_output"] = {{"erreurs": []}}
    print(json.dumps(d))
elif mode == "deconnecte":
    print(json.dumps({{"type": "result", "is_error": True, "result": "Not logged in · Please run /login"}}))
    sys.exit(1)
elif mode == "limite":
    print(json.dumps({{"type": "result", "is_error": True, "result": "5-hour usage limit reached"}}))
    sys.exit(1)
elif mode == "autre":
    print(json.dumps({{"type": "result", "is_error": True, "result": "boum"}}))
    sys.exit(1)
elif mode == "texte":
    print("pas du json")
elif mode == "stderr":
    sys.stderr.write("Invalid API key")
    sys.exit(1)
elif mode == "lent":
    time.sleep(5)
elif mode == "ordre":
    time.sleep(0.2 if "premier" in entree else 0)
    print(json.dumps({{"type": "result", "is_error": False, "result": entree}}))
"""


@pytest.fixture
def faux(tmp_path, monkeypatch):
    chemin = tmp_path / "claude_faux"
    chemin.write_text(FAUX.format(python=sys.executable))
    chemin.chmod(0o755)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    return ClientClaude(executable=str(chemin), delai=3)


def test_succes_json(faux):
    r = faux.executer("bonjour", schema={"type": "object"}, systeme="sois bref")
    assert r.texte == "recu:bonjour"  # prompt passé par stdin
    assert r.structure == {"erreurs": []}
    assert r.usage["output_tokens"] == 5 and r.cout_usd == 0.01 and r.session_id == "s1"
    args = r.brut["args"]
    assert args[:3] == ["-p", "--output-format", "json"]
    assert "--bare" not in args and "--json-schema" in args and "--append-system-prompt" in args
    assert r.brut["cle_api_presente"] is False  # le forfait, pas l'API


@pytest.mark.parametrize("mode,exc", [
    ("deconnecte", ClaudeNonConnecte),
    ("stderr", ClaudeNonConnecte),
    ("limite", ClaudeLimite),
    ("autre", ClaudeEchec),
    ("texte", ClaudeSortieInvalide),
])
def test_erreurs(faux, monkeypatch, mode, exc):
    monkeypatch.setenv("FAUX_MODE", mode)
    with pytest.raises(exc):
        faux.executer("x")


def test_introuvable():
    with pytest.raises(ClaudeIntrouvable):
        ClientClaude(executable="/nexiste/pas/claude").executer("x")


def test_delai(faux, monkeypatch):
    monkeypatch.setenv("FAUX_MODE", "lent")
    faux.delai = 0.5
    with pytest.raises(ClaudeDelai):
        faux.executer("x")


def test_file_une_tache_a_la_fois_dans_l_ordre(faux, monkeypatch):
    monkeypatch.setenv("FAUX_MODE", "ordre")
    file = FileClaude(faux)
    futurs = [file.soumettre("premier"), file.soumettre("deuxieme")]
    assert [f.result(timeout=10).texte for f in futurs] == ["premier", "deuxieme"]
    file.arreter()


def test_file_survit_a_une_erreur(faux, monkeypatch):
    file = FileClaude(faux)
    monkeypatch.setenv("FAUX_MODE", "limite")
    f1 = file.soumettre("a")
    with pytest.raises(ClaudeLimite):
        f1.result(timeout=10)
    monkeypatch.setenv("FAUX_MODE", "ok")
    assert file.soumettre("b").result(timeout=10).texte == "recu:b"
    file.arreter()
