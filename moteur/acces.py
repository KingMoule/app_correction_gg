"""Code d'accès, contrôle de `Host` et d'`Origin` (audit E6).

- Toutes les routes `/api/` exigent une session (cookie `session_correction`), sauf `/api/connexion`
  et `/api/deconnexion`. La PWA statique reste publique (aucune donnée) pour afficher l'écran de saisie.
- Le code est choisi par Guillaume (premier lancement ou `python -m moteur.acces nouveau-code`).
  Seule son empreinte (scrypt + sel) est gardée, dans `<données>/acces.json`, avec un secret qui signe
  les cookies : changer le code change le secret, donc toutes les sessions sont révoquées.
- Session : jeton signé (HMAC) `expiration.nonce.signature`, cookie HttpOnly + SameSite=Strict, posé par
  le serveur, valable un an et renouvelé en continu (glissante).
- DNS rebinding : `Host` doit être `localhost`, une adresse IP (un site de rebinding passe par un nom),
  le nom de l'ordi ou un nom listé dans `CORRECTION_HOTES` (séparés par des virgules).
- CSRF : sur les requêtes qui modifient, `Origin` (sinon `Referer`) doit être celui de la page elle-même.
- Limite d'essais du code par adresse, avec un blocage qui double à chaque échec au-delà de 4.
- Mode `--local` : pas de code (`CORRECTION_SANS_CODE=1` posé par `python -m moteur`), mais `Host` et
  `Origin` restent contrôlés.
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import sys
import threading
import time
from http.cookies import SimpleCookie
from ipaddress import ip_address
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import dossier_donnees
from .stockage import ecrire_json, lire_json

NOM_COOKIE = "session_correction"
DUREE_SESSION = 365 * 24 * 3600
LONGUEUR_MIN = 8
LONGUEUR_MAX = 200
PUBLIQUES = frozenset({"/api/connexion", "/api/deconnexion"})
METHODES_SURES = frozenset({"GET", "HEAD", "OPTIONS"})
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


# ----- code et jetons -----

def _fichier():
    return dossier_donnees() / "acces.json"


_cache: dict = {}


def _config() -> dict | None:
    """Contenu de acces.json (relu seulement si le fichier a changé), ou None s'il n'y a pas de code."""
    chemin = _fichier()
    try:
        st = chemin.stat()
    except OSError:
        return None
    cle = (str(chemin), st.st_mtime_ns, st.st_size)
    if _cache.get("cle") != cle:
        c = lire_json(chemin, None)
        valide = isinstance(c, dict) and all(isinstance(c.get(k), str) for k in ("sel", "empreinte", "secret"))
        _cache.update(cle=cle, valeur=c if valide else None)
    return _cache["valeur"]


def est_configure() -> bool:
    return _config() is not None


def exige_code() -> bool:
    return os.environ.get("CORRECTION_SANS_CODE") != "1"


def _empreinte(code: str, sel: bytes) -> bytes:
    return hashlib.scrypt(code.encode("utf-8"), salt=sel, **SCRYPT)


def code_acceptable(code: str) -> str | None:
    """Pourquoi ce code est refusé, ou None."""
    if len(code) < LONGUEUR_MIN:
        return f"Le code doit avoir au moins {LONGUEUR_MIN} caractères."
    if len(code) > LONGUEUR_MAX:
        return f"Le code ne peut pas dépasser {LONGUEUR_MAX} caractères."
    return None


def definir_code(code: str) -> None:
    """Enregistre le code (empreinte seulement) et révoque toutes les sessions (nouveau secret)."""
    raison = code_acceptable(code)
    if raison:
        raise ValueError(raison)
    sel = secrets.token_bytes(16)
    ecrire_json(_fichier(), {
        "version": 1, "sel": sel.hex(), "empreinte": _empreinte(code, sel).hex(),
        "secret": secrets.token_hex(32),
    })


def verifier_code(code: str) -> bool:
    c = _config()
    if c is None or len(code) > LONGUEUR_MAX:
        return False
    try:
        attendu = bytes.fromhex(c["empreinte"])
        sel = bytes.fromhex(c["sel"])
    except ValueError:
        return False
    return hmac.compare_digest(_empreinte(code, sel), attendu)


def _signature(secret: str, corps: str) -> str:
    return hmac.new(secret.encode(), corps.encode(), hashlib.sha256).hexdigest()


def creer_jeton(maintenant: float | None = None) -> str:
    c = _config()
    assert c is not None
    expiration = int((time.time() if maintenant is None else maintenant) + DUREE_SESSION)
    corps = f"{expiration}.{secrets.token_hex(8)}"
    return f"{corps}.{_signature(c['secret'], corps)}"


def jeton_valide(jeton: str | None, maintenant: float | None = None) -> tuple[bool, bool]:
    """(valide, à renouveler). Renouvelé quand il reste moins de la moitié de la durée."""
    c = _config()
    if not jeton or c is None:
        return False, False
    corps, _, signature = jeton.rpartition(".")
    if not hmac.compare_digest(signature, _signature(c["secret"], corps)):
        return False, False
    try:
        reste = int(corps.split(".")[0]) - (time.time() if maintenant is None else maintenant)
    except ValueError:
        return False, False
    return reste > 0, 0 < reste < DUREE_SESSION / 2


def entete_cookie(jeton: str, duree: int = DUREE_SESSION) -> str:
    return f"{NOM_COOKIE}={jeton}; Max-Age={duree}; Path=/; HttpOnly; SameSite=Strict"


# ----- limite d'essais -----

class LimiteEssais:
    """Échecs par adresse : libres jusqu'à 4, puis blocage de 30 s qui double (15 min au plus)."""

    LIBRES = 4
    BASE = 30
    MAXIMUM = 900

    def __init__(self, horloge=time.monotonic):
        self.horloge = horloge
        self._verrou = threading.Lock()
        self._etat: dict[str, list[float]] = {}  # adresse -> [échecs, bloqué jusqu'à, dernier échec]

    def reinitialiser(self) -> None:
        with self._verrou:
            self._etat.clear()

    def attente(self, adresse: str) -> int:
        """Secondes à attendre avant un nouvel essai (0 = permis)."""
        with self._verrou:
            e = self._etat.get(adresse)
            return max(0, int(e[1] - self.horloge() + 0.999)) if e else 0

    def echec(self, adresse: str) -> None:
        with self._verrou:
            maintenant = self.horloge()
            if len(self._etat) > 1000:  # borne la mémoire : on oublie les vieux échecs
                for a in [a for a, e in self._etat.items() if maintenant - e[2] > 3600]:
                    del self._etat[a]
            e = self._etat.setdefault(adresse, [0, 0.0, maintenant])
            e[0] += 1
            e[2] = maintenant
            if e[0] > self.LIBRES:
                e[1] = maintenant + min(self.MAXIMUM, self.BASE * 2 ** (e[0] - self.LIBRES - 1))

    def succes(self, adresse: str) -> None:
        with self._verrou:
            self._etat.pop(adresse, None)


limiteur = LimiteEssais()


# ----- Host et Origin -----

def _nom_hote(netloc: str) -> str:
    """Nom sans port ni crochets : `[::1]:8001` -> `::1`, `Localhost:8001` -> `localhost`."""
    netloc = netloc.strip().lower()
    if netloc.startswith("["):
        return netloc[1:].split("]")[0]
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def hote_autorise(host: str | None) -> bool:
    if not host:
        return False
    nom = _nom_hote(host)
    try:
        ip_address(nom)
        return True  # une adresse IP n'est pas un nom de domaine qu'un site pourrait détourner
    except ValueError:
        pass
    if nom == "localhost" or nom.endswith(".localhost"):
        return True
    permis = {socket.gethostname().lower()}
    permis.update(n.strip().lower() for n in os.environ.get("CORRECTION_HOTES", "").split(",") if n.strip())
    return nom in permis


def origine_autorisee(en_tetes: dict[str, str]) -> bool:
    """Pour une requête qui modifie : `Origin` (sinon `Referer`), s'il est présent, doit être celui du `Host`."""
    host = en_tetes.get("host", "").strip().lower()
    for nom in ("origin", "referer"):
        valeur = en_tetes.get(nom)
        if valeur is not None:
            return urlsplit(valeur).netloc.lower() == host and urlsplit(valeur).scheme in ("http", "https")
    return True  # ni l'un ni l'autre : client hors navigateur (il lui faut tout de même la session)


# ----- intergiciel -----

def _en_api(chemin: str) -> bool:
    return chemin == "/api" or chemin.startswith("/api/")


class ControleAcces:
    """Intergiciel ASGI pur (pas de BaseHTTPMiddleware : les téléchargements en flux restent intacts)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        en_tetes = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        chemin, methode = scope["path"], scope["method"]

        if not hote_autorise(en_tetes.get("host")):
            await self._refuser(send, 403, "Hôte non autorisé.")
            return
        if methode not in METHODES_SURES and not origine_autorisee(en_tetes):
            await self._refuser(send, 403, "Origine non autorisée.")
            return

        renouveler = None
        if _en_api(chemin) and chemin not in PUBLIQUES and exige_code():
            cookies = SimpleCookie(en_tetes.get("cookie", ""))
            jeton = cookies[NOM_COOKIE].value if NOM_COOKIE in cookies else None
            valide, a_renouveler = jeton_valide(jeton)
            if not valide:
                navigation = (methode == "GET" and en_tetes.get("sec-fetch-mode") == "navigate"
                              and "text/html" in en_tetes.get("accept", ""))
                if navigation:  # lien ou téléchargement ouvert directement : écran de saisie, puis retour
                    suite = chemin + (("?" + scope["query_string"].decode("latin-1")) if scope["query_string"] else "")
                    await self._reponse(send, 303, b"", [(b"location", f"/acces.html?suite={quote(suite, safe='')}".encode())])
                else:
                    await self._refuser(send, 401, "Code d'accès requis.")
                return
            renouveler = jeton if a_renouveler else None

        if renouveler is None:
            await self.app(scope, receive, send)
            return

        async def envoyer(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []),
                                                  (b"set-cookie", entete_cookie(creer_jeton()).encode())]}
            await send(message)

        await self.app(scope, receive, envoyer)

    async def _refuser(self, send, statut: int, detail: str):
        corps = json.dumps({"detail": detail}, ensure_ascii=False).encode()
        await self._reponse(send, statut, corps, [(b"content-type", b"application/json")])

    @staticmethod
    async def _reponse(send, statut: int, corps: bytes, en_tetes: list[tuple[bytes, bytes]]):
        await send({"type": "http.response.start", "status": statut,
                    "headers": [*en_tetes, (b"content-length", str(len(corps)).encode()),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": corps})


# ----- routes de connexion -----

router = APIRouter(prefix="/api")


class Connexion(BaseModel):
    code: str = Field(max_length=LONGUEUR_MAX)


@router.get("/connexion")
def etat_connexion(request: Request) -> dict:
    """État pour l'écran de saisie : un code est-il requis, est-il défini, cette session est-elle valide ?"""
    jeton = request.cookies.get(NOM_COOKIE)
    return {"requis": exige_code(), "configure": est_configure(),
            "connecte": (not exige_code()) or jeton_valide(jeton)[0]}


@router.post("/connexion")
def connexion(corps: Connexion, request: Request):
    if not exige_code():
        return {"ok": True}
    if not est_configure():
        return JSONResponse({"detail": "Aucun code d'accès n'est défini. Sur l'ordi : python -m moteur.acces nouveau-code"},
                            status_code=503)
    adresse = request.client.host if request.client else "?"
    attente = limiteur.attente(adresse)
    if attente:
        return JSONResponse({"detail": f"Trop d'essais. Réessaie dans {attente} s.", "attente": attente},
                            status_code=429, headers={"Retry-After": str(attente)})
    if not verifier_code(corps.code):
        limiteur.echec(adresse)
        attente = limiteur.attente(adresse)
        detail = "Code incorrect." + (f" Réessaie dans {attente} s." if attente else "")
        return JSONResponse({"detail": detail, "attente": attente}, status_code=401)
    limiteur.succes(adresse)
    reponse = JSONResponse({"ok": True})
    reponse.headers["set-cookie"] = entete_cookie(creer_jeton())
    return reponse


@router.post("/deconnexion")
def deconnexion():
    """Efface le cookie de cet appareil (les autres appareils restent connectés)."""
    reponse = JSONResponse({"ok": True})
    reponse.headers["set-cookie"] = entete_cookie("", 0)
    return reponse


# ----- ligne de commande -----

def demander_nouveau_code() -> None:
    """Demande un code (deux fois, sans l'afficher) et l'enregistre. Quitte s'il n'y a pas de terminal."""
    if not sys.stdin.isatty():
        print("Aucun code d'accès défini et aucun terminal pour le saisir.\n"
              "Lance : python -m moteur.acces nouveau-code", file=sys.stderr)
        sys.exit(1)
    while True:
        code = getpass.getpass(f"Choisis le code d'accès ({LONGUEUR_MIN} caractères au moins; rien ne s'affiche) : ")
        raison = code_acceptable(code)
        if raison:
            print(raison)
        elif getpass.getpass("Retape le code : ") != code:
            print("Les deux saisies ne sont pas identiques.")
        else:
            break
    definir_code(code)
    print("Code enregistré. Les appareils connectés devront le ressaisir.")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args[:1] == ["nouveau-code"]:
        demander_nouveau_code()
    elif args[:1] == ["etat"]:
        print("Code d'accès défini." if est_configure() else "Aucun code d'accès défini.")
    else:
        print("Usage : python -m moteur.acces nouveau-code | etat", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
