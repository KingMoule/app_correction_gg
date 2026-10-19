"""Client de LanguageTool, serveur local (jamais de texte envoyé sur Internet).

Lancer le serveur (Java requis) :
    java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
L'adresse se change avec la variable LANGUAGETOOL_URL.
"""

import os
from dataclasses import dataclass, field

import httpx

URL_DEFAUT = "http://localhost:8081"


class LanguageToolIndisponible(Exception):
    pass


@dataclass
class Faute:
    debut: int
    fin: int
    texte: str
    message: str
    regle: str
    categorie: str
    suggestions: list[str] = field(default_factory=list)


def url_serveur() -> str:
    return os.environ.get("LANGUAGETOOL_URL", URL_DEFAUT).rstrip("/")


def verifier(texte: str, langue: str = "fr", client: httpx.Client | None = None) -> list[Faute]:
    """Fautes détectées dans `texte`, avec décalages en caractères."""
    try:
        if client is None:
            with httpx.Client(timeout=60) as c:
                r = c.post(f"{url_serveur()}/v2/check", data={"text": texte, "language": langue})
        else:
            r = client.post(f"{url_serveur()}/v2/check", data={"text": texte, "language": langue})
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LanguageToolIndisponible(f"LanguageTool injoignable ({url_serveur()}) : {e}") from e
    fautes = []
    for m in r.json().get("matches", []):
        d, n = m["offset"], m["length"]
        fautes.append(
            Faute(
                debut=d,
                fin=d + n,
                texte=texte[d : d + n],
                message=m.get("message", ""),
                regle=m.get("rule", {}).get("id", ""),
                categorie=m.get("rule", {}).get("category", {}).get("id", ""),
                suggestions=[s["value"] for s in m.get("replacements", [])[:5]],
            )
        )
    return fautes
