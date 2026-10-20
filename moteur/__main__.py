"""Lancement : `python -m moteur` (écoute sur le Wi-Fi maison, port 8001 par défaut)."""

import argparse
import socket
import sys

import uvicorn


PORT_DEFAUT = 8001


def adresse_reseau() -> str:
    """Adresse de l'ordi sur le réseau local (à saisir sur l'iPad)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))  # aucun paquet n'est envoyé
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def port_libre(hote: str, port: int) -> bool:
    """Vrai si on peut écouter sur ce port (faux s'il est déjà pris)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((hote, port))
        except OSError:
            return False
        return True


def main() -> None:
    p = argparse.ArgumentParser(prog="moteur")
    p.add_argument("--port", type=int, default=PORT_DEFAUT)
    p.add_argument("--local", action="store_true",
                   help="n'écouter que sur cet ordi (pas d'accès iPad)")
    args = p.parse_args()
    hote = "127.0.0.1" if args.local else "0.0.0.0"
    if not port_libre(hote, args.port):
        print(f"Le port {args.port} est déjà utilisé par un autre programme.\n"
              f"Essaie un autre port : python -m moteur --port {args.port + 1}",
              file=sys.stderr)
        sys.exit(1)
    print(f"Sur l'iPad (même Wi-Fi) : http://{adresse_reseau()}:{args.port}")
    uvicorn.run("moteur.app:app", host=hote, port=args.port)


if __name__ == "__main__":
    main()
