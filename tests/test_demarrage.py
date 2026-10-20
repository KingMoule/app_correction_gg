"""Démarrage : message clair quand le port est déjà pris."""

import socket
import sys

import pytest

from moteur import __main__ as demarrage


def test_port_libre_et_pris():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        assert not demarrage.port_libre("127.0.0.1", port)
    assert demarrage.port_libre("127.0.0.1", port)


def test_main_port_pris_message_clair(monkeypatch, capsys):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        monkeypatch.setattr(sys, "argv", ["moteur", "--local", "--port", str(port)])
        monkeypatch.setattr(demarrage.uvicorn, "run",
                            lambda *a, **k: pytest.fail("uvicorn ne doit pas démarrer"))
        with pytest.raises(SystemExit) as e:
            demarrage.main()
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert f"port {port} est déjà utilisé" in err
    assert f"--port {port + 1}" in err
