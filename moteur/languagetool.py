"""Client de LanguageTool, serveur local (jamais de texte envoyé sur Internet).

Lancer le serveur (Java requis) :
    java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
L'adresse se change avec la variable LANGUAGETOOL_URL.
"""

import json
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


def _vers_points(texte: str):
    """Convertit un décalage LanguageTool (unités UTF-16) en indice de caractère Python.

    Les caractères hors du plan de base (certains symboles mathématiques, émojis) comptent
    pour 2 chez LanguageTool et pour 1 en Python : sans conversion, les fautes suivantes sont
    décalées et peuvent même tomber hors du texte."""
    if all(ord(c) <= 0xFFFF for c in texte):
        return lambda u: u
    table = []
    for i, c in enumerate(texte):
        table.extend([i] * (2 if ord(c) > 0xFFFF else 1))
    table.append(len(texte))
    return lambda u: table[min(u, len(table) - 1)]


def verifier(
    texte: str,
    langue: str = "fr",
    client: httpx.Client | None = None,
    parties: list[dict] | None = None,
    regles_off: str = "",
    categories_off: str = "",
) -> list[Faute]:
    """Fautes détectées dans `texte`, avec décalages en caractères.

    `parties` (facultatif) : découpage de `texte` en `{"text": …}` (vérifié) et
    `{"markup": …, "interpretAs": …}` (ignoré, mais compté dans les positions); leur
    concaténation doit redonner `texte`."""
    donnees = {"language": langue}
    if parties is None:
        donnees["text"] = texte
    else:
        donnees["data"] = json.dumps({"annotation": parties}, ensure_ascii=False)
    if regles_off:
        donnees["disabledRules"] = regles_off
    if categories_off:
        donnees["disabledCategories"] = categories_off
    try:
        if client is None:
            with httpx.Client(timeout=60) as c:
                r = c.post(f"{url_serveur()}/v2/check", data=donnees)
        else:
            r = client.post(f"{url_serveur()}/v2/check", data=donnees)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise LanguageToolIndisponible(f"LanguageTool injoignable ({url_serveur()}) : {e}") from e
    point = _vers_points(texte)
    fautes = []
    for m in r.json().get("matches", []):
        d, f = point(m["offset"]), point(m["offset"] + m["length"])
        fautes.append(
            Faute(
                debut=d,
                fin=f,
                texte=texte[d:f],
                message=m.get("message", ""),
                regle=m.get("rule", {}).get("id", ""),
                categorie=m.get("rule", {}).get("category", {}).get("id", ""),
                suggestions=[s["value"] for s in m.get("replacements", [])[:5]],
            )
        )
    return fautes
