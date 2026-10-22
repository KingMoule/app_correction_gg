"""Existence des références sur Internet : Crossref, OpenAlex, ouverture de la page citée.

Seuls le DOI, l'ISBN, l'URL ou la référence elle-même (titre, auteurs) partent sur le réseau,
jamais un nom d'étudiant ni un passage du rapport. Délais courts, erreurs réseau et mode hors
ligne = « non vérifiable » (jamais un échec). Réponses gardées dans un cache local.

Réglages (variables d'environnement) : `CORRECTION_CONTACT` (adresse jointe au User-Agent,
courtoisie envers Crossref et OpenAlex), `CORRECTION_HORS_LIGNE=1` (aucun accès réseau).
Une URL citée n'est ouverte que si son adresse est publique (jamais l'ordi ou le réseau local).
"""

import html
import ipaddress
import os
import re
import socket
import threading
import unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin, urlparse

import httpx

from . import __version__, stockage
from .config import dossier_donnees

CROSSREF = "https://api.crossref.org"
OPENALEX = "https://api.openalex.org"
DELAI = httpx.Timeout(8.0, connect=5.0)
MAX_PAGE = 300_000  # octets lus d'une page web
MAX_TEXTE = 1500  # caractères gardés comme résumé (résumé d'article ou texte de page)
DUREE_TROUVE = timedelta(days=30)
DUREE_INTROUVABLE = timedelta(days=3)

TRANSPORT: httpx.BaseTransport | None = None  # les tests y mettent un faux réseau
RESOLVEUR = socket.getaddrinfo  # les tests le remplacent (aucun accès DNS)

TROUVEE, INTROUVABLE, DIVERGENTE, NON_VERIFIABLE = "trouvee", "introuvable", "divergente", "non_verifiable"


def sans_accent(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def mots_utiles(t: str) -> set[str]:
    return {m for m in re.findall(r"[a-z0-9]+", sans_accent(t)) if len(m) >= 4}


def ressemblance(titre: str, brut: str) -> float | None:
    """Part des mots (4 lettres et plus) du titre retrouvés dans la référence; None sans titre."""
    mots = mots_utiles(titre)
    return len(mots & mots_utiles(brut)) / len(mots) if mots else None


def _resume_web(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return t[:MAX_TEXTE]


def isbn_valide(chiffres: str) -> bool:
    c = chiffres.upper()
    if len(c) == 10 and re.fullmatch(r"\d{9}[\dX]", c):
        return sum((10 - i) * (10 if x == "X" else int(x)) for i, x in enumerate(c)) % 11 == 0
    if len(c) == 13 and c.isdigit():
        return sum(int(x) * (1 if i % 2 == 0 else 3) for i, x in enumerate(c)) % 10 == 0
    return False


class Reseau:
    """Un contexte de vérification : client HTTP, cache, état « hors ligne »."""

    def __init__(self, rafraichir: bool = False):
        self.rafraichir = rafraichir
        self.hors_ligne = os.environ.get("CORRECTION_HORS_LIGNE", "").strip() in ("1", "oui", "true")
        contact = os.environ.get("CORRECTION_CONTACT", "").strip()
        self.agent = f"CorrectionLabs/{__version__} (usage personnel d'un enseignant" + (f"; mailto:{contact}" if contact else "") + ")"
        self.contact = contact
        self.client = httpx.Client(transport=TRANSPORT, timeout=DELAI, follow_redirects=False,
                                   headers={"User-Agent": self.agent})
        self._verrou = threading.Lock()
        self._cache = stockage.lire_json(self._fichier_cache(), {})
        if not isinstance(self._cache, dict):
            self._cache = {}
        self._sale = False

    @staticmethod
    def _fichier_cache():
        d = dossier_donnees() / "references"
        d.mkdir(parents=True, exist_ok=True)
        return d / "cache.json"

    def fermer(self) -> None:
        self.client.close()
        if self._sale:
            with stockage.verrou(self._fichier_cache().parent):
                actuel = stockage.lire_json(self._fichier_cache(), {})
                actuel = actuel if isinstance(actuel, dict) else {}
                with self._verrou:
                    actuel.update(self._cache)
                self._purger(actuel)
                stockage.ecrire_json(self._fichier_cache(), actuel)

    @staticmethod
    def _purger(cache: dict) -> None:
        maintenant = datetime.now()
        for k in [k for k, v in cache.items() if not _frais(v, maintenant)]:
            del cache[k]

    # --- cache ---
    def _lire(self, cle: str) -> dict | None:
        if self.rafraichir:
            return None
        with self._verrou:
            v = self._cache.get(cle)
        return v["valeur"] if v and _frais(v, datetime.now()) else None

    def _ecrire(self, cle: str, valeur: dict) -> None:
        if valeur["etat"] == NON_VERIFIABLE:
            return
        with self._verrou:
            self._cache[cle] = {"date": datetime.now().isoformat(timespec="seconds"), "valeur": valeur}
            self._sale = True

    # --- accès ---
    def _get(self, url: str, params: dict | None = None, api: bool = True) -> httpx.Response | None:
        """Réponse, ou None si le réseau est inaccessible. Une panne de connexion à une API passe en hors ligne."""
        if self.hors_ligne:
            return None
        try:
            return self.client.get(url, params=params, follow_redirects=api)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError):
            if api:
                self.hors_ligne = True
            return None
        except httpx.HTTPError:
            return None

    def _api(self, url: str, params: dict | None = None):
        """(statut, json) : (None, None) si injoignable."""
        if self.contact:
            params = {**(params or {}), "mailto": self.contact}
        r = self._get(url, params)
        if r is None:
            return None, None
        try:
            return r.status_code, (r.json() if r.status_code == 200 else None)
        except ValueError:
            return r.status_code, None

    # --- DOI ---
    def doi(self, doi: str, brut: str) -> dict:
        cle = "doi:" + doi.lower()
        deja = self._lire(cle)
        if deja:
            return deja
        res = self._doi(doi, brut)
        self._ecrire(cle, res)
        return res

    def _doi(self, doi: str, brut: str) -> dict:
        ch = f"{CROSSREF}/works/{quote(doi, safe='/')}"
        s1, j1 = self._api(ch)
        trouve = None
        if s1 == 200 and isinstance(j1, dict) and isinstance(j1.get("message"), dict):
            trouve = _lire_crossref(j1["message"], "crossref")
        s2 = j2 = None
        if trouve is None or not trouve["resume"]:  # OpenAlex : seconde source, ou résumé manquant chez Crossref
            s2, j2 = self._api(f"{OPENALEX}/works/doi:{quote(doi, safe='/')}")
            if s2 == 200 and isinstance(j2, dict):
                o = _lire_openalex(j2)
                trouve = {**o, "titre": trouve["titre"] or o["titre"], "url": trouve["url"], "source": "crossref"} if trouve else o
        if trouve:
            return _conclure(trouve, brut)
        if s1 == 404 and s2 == 404:  # absent des deux bases : le registre central des DOI tranche
            return self._handle(doi)
        return _non_verifiable(s1, s2)

    def _handle(self, doi: str) -> dict:
        r = self._get(f"https://doi.org/api/handles/{quote(doi, safe='/')}", api=False)
        try:
            code = r.json().get("responseCode") if r is not None else None
        except ValueError:
            code = None
        if code == 1:
            return {"etat": TROUVEE, "source": "doi.org", "titre": "", "resume": "", "url": f"https://doi.org/{doi}",
                    "detail": "DOI enregistré (hors Crossref et OpenAlex) : titre non lu."}
        if code == 100 or (r is not None and r.status_code == 404):
            return {"etat": INTROUVABLE, "source": "doi.org", "detail": "Ce DOI n'existe pas (Crossref, OpenAlex, doi.org)."}
        return _non_verifiable(404, None if r is None else r.status_code)

    # --- ISBN ---
    def isbn(self, isbn: str, brut: str) -> dict:
        if not isbn_valide(isbn):
            return {"etat": INTROUVABLE, "source": None, "detail": "ISBN invalide (somme de contrôle fausse)."}
        cle = "isbn:" + isbn
        deja = self._lire(cle)
        if deja:
            return deja
        s, j = self._api(f"{CROSSREF}/works", {"filter": f"isbn:{isbn}", "rows": 1})
        items = ((j or {}).get("message") or {}).get("items") or []
        if items:
            res = _conclure(_lire_crossref(items[0], "crossref"), brut)
        elif s == 200:
            res = {"etat": NON_VERIFIABLE, "source": None,
                   "detail": "ISBN valide, mais Crossref ne répertorie pas ce livre (cas courant) : non vérifié."}
        else:
            res = _non_verifiable(s, None)
        self._ecrire(cle, res)
        return res

    # --- référence sans identifiant ---
    def recherche(self, brut: str) -> dict:
        cle = "ref:" + sans_accent(re.sub(r"\s+", " ", brut))[:300]
        deja = self._lire(cle)
        if deja:
            return deja
        s, j = self._api(f"{CROSSREF}/works", {"query.bibliographic": brut[:300], "rows": 1})
        items = ((j or {}).get("message") or {}).get("items") or []
        if items:
            c = _lire_crossref(items[0], "crossref")
            r = ressemblance(c["titre"], brut)
            if r is not None and r >= 0.75:
                res = {**c, "etat": TROUVEE, "detail": "Retrouvée dans Crossref à partir du titre (aucun DOI dans l'entrée)."}
                self._ecrire(cle, res)
                return res
        res = {"etat": NON_VERIFIABLE, "source": None,
               "detail": "Aucun DOI, ISBN ni URL, et aucune correspondance sûre dans Crossref : non vérifié."}
        return res

    # --- page web ---
    def page(self, url: str) -> dict:
        cle = "url:" + url
        deja = self._lire(cle)
        if deja:
            return deja
        res = self._page(url)
        self._ecrire(cle, res)
        return res

    def _public(self, hote: str) -> str | None:
        """None si l'hôte est public; sinon la raison pour laquelle on ne l'ouvre pas."""
        try:
            infos = RESOLVEUR(hote, None)
        except OSError:
            try:
                RESOLVEUR("api.crossref.org", None)
            except OSError:
                return "hors ligne"
            return "domaine"
        for i in infos:
            try:
                ip = ipaddress.ip_address(i[4][0].split("%")[0])
            except ValueError:
                return "adresse"
            if not ip.is_global:
                return "adresse"
        return None

    def _page(self, url: str) -> dict:
        if self.hors_ligne:
            return {"etat": NON_VERIFIABLE, "source": None, "detail": "Hors ligne : page non ouverte."}
        courante = url
        for _ in range(5):
            p = urlparse(courante)
            if p.scheme not in ("http", "https") or not p.hostname:
                return {"etat": NON_VERIFIABLE, "source": None, "detail": "Adresse web non reconnue."}
            raison = self._public(p.hostname)
            if raison == "domaine":
                return {"etat": INTROUVABLE, "source": "web", "detail": "Le nom de domaine n'existe pas."}
            if raison == "hors ligne":
                return {"etat": NON_VERIFIABLE, "source": None, "detail": "Hors ligne : page non ouverte."}
            if raison:
                return {"etat": NON_VERIFIABLE, "source": None,
                        "detail": "Adresse locale ou privée : page non ouverte."}
            try:
                with self.client.stream("GET", courante, headers={"Accept": "text/html,application/xhtml+xml"}) as r:
                    if r.is_redirect and r.headers.get("location"):
                        courante = urljoin(courante, r.headers["location"])
                        continue
                    return self._lire_page(r, url)
            except httpx.HTTPError:
                return {"etat": NON_VERIFIABLE, "source": None, "detail": "Le site ne répond pas : page non vérifiée."}
        return {"etat": NON_VERIFIABLE, "source": None, "detail": "Trop de redirections."}

    def _lire_page(self, r: httpx.Response, url: str) -> dict:
        if r.status_code in (404, 410):
            return {"etat": INTROUVABLE, "source": "web", "url": url, "detail": f"La page n'existe pas (erreur {r.status_code})."}
        if r.status_code != 200:
            return {"etat": NON_VERIFIABLE, "source": "web", "url": url,
                    "detail": f"Le site refuse ou ne répond pas (code {r.status_code}) : non vérifié."}
        morceaux, lu = [], 0
        for b in r.iter_bytes():
            morceaux.append(b)
            lu += len(b)
            if lu >= MAX_PAGE:
                break
        type_ = r.headers.get("content-type", "")
        titre, texte = "", ""
        if "html" in type_ or not type_:
            doc = b"".join(morceaux).decode(r.encoding or "utf-8", errors="replace")
            m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
            titre = _resume_web(html.unescape(m.group(1)))[:200] if m else ""
            corps = re.sub(r"(?is)<(script|style|noscript|nav|footer|header)\b.*?</\1>", " ", doc)
            texte = _resume_web(html.unescape(re.sub(r"(?s)<[^>]+>", " ", corps)))
        return {"etat": TROUVEE, "source": "web", "titre": titre, "resume": texte, "url": url,
                "detail": "Page ouverte." if texte else "Page ouverte (contenu non lu : pas du HTML)."}


def _frais(v, maintenant: datetime) -> bool:
    try:
        age = maintenant - datetime.fromisoformat(v["date"])
        return age < (DUREE_INTROUVABLE if v["valeur"]["etat"] == INTROUVABLE else DUREE_TROUVE)
    except (KeyError, TypeError, ValueError):
        return False


def _non_verifiable(*statuts) -> dict:
    if all(s is None for s in statuts):
        return {"etat": NON_VERIFIABLE, "source": None, "detail": "Réseau inaccessible : non vérifié."}
    return {"etat": NON_VERIFIABLE, "source": None, "detail": "Les bases de données ne répondent pas (limite ou panne) : non vérifié."}


def _lire_crossref(m: dict, source: str) -> dict:
    titre = ((m.get("title") or [""])[0] or "").strip()
    resume = re.sub(r"<[^>]+>", " ", m.get("abstract") or "")
    return {"etat": TROUVEE, "source": source, "titre": titre,
            "resume": _resume_web(html.unescape(resume)), "url": m.get("URL") or ""}


def _lire_openalex(m: dict) -> dict:
    inv = m.get("abstract_inverted_index") or {}
    places = {p: mot for mot, ps in inv.items() for p in ps} if isinstance(inv, dict) else {}
    resume = " ".join(places[p] for p in sorted(places))
    return {"etat": TROUVEE, "source": "openalex", "titre": (m.get("title") or m.get("display_name") or "").strip(),
            "resume": _resume_web(resume), "url": m.get("doi") or m.get("id") or ""}


def _conclure(trouve: dict, brut: str) -> dict:
    """Une source trouvée : « divergente » si son titre ne ressemble pas à l'entrée."""
    r = ressemblance(trouve["titre"], brut)
    if r is not None and r < 0.5:
        return {**trouve, "etat": DIVERGENTE,
                "detail": f"L'identifiant existe, mais il désigne « {trouve['titre'][:120]} », qui ne ressemble pas à l'entrée."}
    return {**trouve, "detail": f"Retrouvée dans {'OpenAlex' if trouve['source'] == 'openalex' else 'Crossref'}."}
