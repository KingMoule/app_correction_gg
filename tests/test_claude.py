"""Tests de moteur/claude.py avec un faux exécutable `claude` (aucun appel réel)."""

import json
import os
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
    """Client dont « claude » est un script Python, lancé par l'interpréteur courant.

    Portable (Windows ne sait pas exécuter un script à shebang) : on remplace seulement
    le premier élément de la commande; les arguments, l'entrée standard et l'environnement
    sont ceux d'un vrai appel.
    """
    script = tmp_path / "claude_faux.py"
    script.write_text(FAUX.format(python=sys.executable), encoding="utf-8")
    original = ClientClaude.commande

    def commande(self, schema=None, systeme=None):
        return [sys.executable, str(script)] + original(self, schema, systeme)[1:]

    monkeypatch.setattr(ClientClaude, "_resoudre_executable", lambda self: "claude")
    monkeypatch.setattr(ClientClaude, "commande", commande)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    return ClientClaude(delai=3)


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


def test_introuvable_message_renvoie_aux_docs():
    with pytest.raises(ClaudeIntrouvable, match="CLAUDE_CLI.md"):
        ClientClaude(executable="claude_qui_n_existe_pas").executer("x")


@pytest.mark.skipif(os.name == "nt", reason="script à shebang : Linux/macOS seulement")
def test_executable_reel_via_path(tmp_path, monkeypatch):
    chemin = tmp_path / "claude"
    chemin.write_text(FAUX.format(python=sys.executable))
    chemin.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert ClientClaude(delai=3).executer("salut").texte == "recu:salut"


@pytest.mark.skipif(os.name != "nt", reason="spécifique à Windows (.cmd npm)")
def test_cmd_sans_binaire_natif_erreur_claire(tmp_path, monkeypatch):
    (tmp_path / "claude.cmd").write_text("@echo off\r\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    with pytest.raises(ClaudeIntrouvable, match="Installer le Claude Code natif"):
        ClientClaude().executer("x")


@pytest.mark.skipif(os.name != "nt", reason="spécifique à Windows (.cmd npm)")
def test_cmd_npm_utilise_le_binaire_natif(tmp_path, monkeypatch):
    natif = tmp_path / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    natif.parent.mkdir(parents=True)
    natif.write_bytes(b"")
    (tmp_path / "claude.cmd").write_text("@echo off\r\n")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])
    assert ClientClaude()._resoudre_executable() == str(natif)


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
