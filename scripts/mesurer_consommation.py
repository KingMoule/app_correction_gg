"""Test de consommation : analyse d'UN rapport par Claude (français + indices d'IA).

Usage (sur ton ordi, Claude Code installé et connecté) :
    python scripts/mesurer_consommation.py chemin/du/rapport.pdf
    python scripts/mesurer_consommation.py rapport.txt --modele sonnet

Le rapport peut être un PDF avec texte (nécessite `pip install pypdf`) ou un .txt.
Rien n'est écrit dans le dépôt ; le résumé chiffré va dans donnees/consommation/
(dossier exclu de git). Voir docs/CLAUDE_CLI.md pour lire l'usage dans Claude.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moteur.claude import ClaudeErreur, ClientClaude, FileClaude  # noqa: E402
from moteur.config import dossier_donnees  # noqa: E402

SCHEMA_FRANCAIS = {
    "type": "object",
    "properties": {"erreurs": {"type": "array", "items": {
        "type": "object",
        "properties": {"extrait": {"type": "string"}, "correction": {"type": "string"},
                       "type": {"type": "string"}},
        "required": ["extrait", "correction"]}}},
    "required": ["erreurs"],
}
SCHEMA_IA = {
    "type": "object",
    "properties": {"indice": {"type": "string", "enum": ["faible", "moyen", "fort"]},
                   "raisons": {"type": "array", "items": {"type": "string"}}},
    "required": ["indice", "raisons"],
}
SYSTEME = "Tu aides un enseignant à corriger un rapport de laboratoire. Réponds seulement selon le schéma."
PROMPTS = {
    "francais": ("Relève les fautes d'orthographe, de grammaire et de syntaxe du rapport. "
                 "Donne l'extrait fautif et sa correction.", SCHEMA_FRANCAIS),
    "indices_ia": ("Évalue si le style du rapport évoque un texte généré par IA. "
                   "C'est un indice à revérifier, jamais un verdict.", SCHEMA_IA),
}


def lire_texte(chemin: Path) -> str:
    if chemin.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("Pour un PDF : pip install pypdf (ou donne un fichier .txt).")
        texte = "\n".join(p.extract_text() or "" for p in PdfReader(str(chemin)).pages)
    else:
        texte = chemin.read_text(encoding="utf-8")
    if not texte.strip():
        sys.exit("Aucun texte trouvé (PDF scanné ?).")
    return texte


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rapport", type=Path)
    ap.add_argument("--modele", help="ex. sonnet, haiku (défaut : celui de Claude Code)")
    ap.add_argument("--claude", default="claude", help="chemin de la commande claude")
    a = ap.parse_args()

    texte = lire_texte(a.rapport)
    print(f"Rapport : {len(texte)} caractères. Début du test (1 à 3 minutes)…\n")
    file = FileClaude(ClientClaude(a.claude, modele=a.modele))
    futurs = {nom: file.soumettre(f"{consigne}\n\n<rapport>\n{texte}\n</rapport>", schema, SYSTEME)
              for nom, (consigne, schema) in PROMPTS.items()}

    lignes, total = [], {"entree": 0, "sortie": 0, "cout": 0.0}
    for nom, futur in futurs.items():
        try:
            r = futur.result()
        except ClaudeErreur as e:
            print(f"✗ {nom} : {type(e).__name__} — {e}")
            return 1
        u = r.usage
        entree = (u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                  + u.get("cache_read_input_tokens", 0))
        sortie = u.get("output_tokens", 0)
        cout = r.cout_usd or 0.0
        total["entree"] += entree; total["sortie"] += sortie; total["cout"] += cout
        lignes.append({"analyse": nom, "jetons_entree": entree, "jetons_sortie": sortie,
                       "cout_estime_usd": cout, "duree_s": round((r.duree_ms or 0) / 1000, 1)})
        print(f"✓ {nom:<11} entrée {entree:>7} · sortie {sortie:>6} · ~{cout:.3f} $ (estimation)")
    file.arreter()

    print(f"\nTOTAL       entrée {total['entree']:>7} · sortie {total['sortie']:>6} "
          f"· ~{total['cout']:.3f} $ (équivalent API, pas facturé avec le forfait)")
    print("\nMaintenant, dans Claude Code, tape /usage et note la différence de % "
          "avec la valeur d'avant le test (voir docs/CLAUDE_CLI.md).")

    sortie_dir = dossier_donnees() / "consommation"
    sortie_dir.mkdir(exist_ok=True)
    fichier = sortie_dir / f"test_{time.strftime('%Y%m%d_%H%M%S')}.json"
    fichier.write_text(json.dumps({"caracteres": len(texte), "modele": a.modele,
                                   "analyses": lignes, "total": total},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Résumé enregistré : {fichier}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
