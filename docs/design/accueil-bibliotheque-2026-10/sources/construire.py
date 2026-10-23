"""Assemble les maquettes autonomes : CSS de la PWA (jetons, composants, coque) + maquettes.css + police Inter + sprite Lucide,
tout en ligne, pour qu'elles s'ouvrent sans moteur (dépôt, Artifact, iPad). Usage : python construire.py <depot> <sortie>"""
import base64, re, sys
from pathlib import Path

depot, sortie = Path(sys.argv[1]), Path(sys.argv[2])
ici = Path(__file__).parent
pwa = depot / "pwa"
police = base64.b64encode((pwa / "vendor/inter-variable-latin.woff2").read_bytes()).decode()
css = (pwa / "design.css").read_text(encoding="utf-8").replace(
    'url("vendor/inter-variable-latin.woff2")', f'url("data:font/woff2;base64,{police}")')
css += (pwa / "composants.css").read_text(encoding="utf-8") + (pwa / "coque.css").read_text(encoding="utf-8")
css += (ici / "maquettes.css").read_text(encoding="utf-8")
sprite = (pwa / "vendor/lucide-sprite.svg").read_text(encoding="utf-8")
symboles = "".join(re.findall(r"<symbol.*?</symbol>", sprite, re.S))
# Icônes Lucide absentes du sprite (à ajouter à scripts/sprite_lucide.mjs si la maquette est retenue)
EXTRA = {
    "calendar": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
    "user": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "layout-grid": '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "folder-clock": '<circle cx="16" cy="16" r="6"/><path d="M7 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2"/><path d="M16 14v2l1 1"/>',
    "alarm-clock-off": '<path d="M6.87 6.87a8 8 0 1 0 11.26 11.26"/><path d="M19.9 14.25a8 8 0 0 0-9.15-9.15"/><path d="m22 6-3-3"/><path d="M6.26 18.67 4 21"/><path d="m2 2 20 20"/><path d="M4 4 2 6"/>',
    "hourglass": '<path d="M5 22h14"/><path d="M5 2h14"/><path d="M17 22v-4.172a2 2 0 0 0-.586-1.414L12 12l-4.414 4.414A2 2 0 0 0 7 17.828V22"/><path d="M7 2v4.172a2 2 0 0 0 .586 1.414L12 12l4.414-4.414A2 2 0 0 0 17 6.172V2"/>',
}
symboles += "".join(f'<symbol id="{k}" viewBox="0 0 24 24">{v}</symbol>' for k, v in EXTRA.items())
bloc_sprite = f'<svg xmlns="http://www.w3.org/2000/svg" style="display:none" aria-hidden="true">{symboles}</svg>'
sortie.mkdir(parents=True, exist_ok=True)
for src in sorted((ici / "src").glob("*.html")):
    html = src.read_text(encoding="utf-8")
    html = html.replace("<!--STYLES-->", f"<style>\n{css}\n</style>").replace("<!--SPRITE-->", bloc_sprite).replace("<!--SCRIPT-->", "<script>\n" + (ici / "commun.js").read_text(encoding="utf-8") + "</script>")
    manquantes = set(re.findall(r'href="#([a-z0-9-]+)"', html)) - set(re.findall(r'<symbol id="([a-z0-9-]+)"', html))
    manquantes -= set(re.findall(r'id="([a-z0-9-]+)"', html))
    if manquantes:
        print("  icônes ou ancres manquantes dans", src.name, ":", sorted(manquantes))
    (sortie / src.name).write_text(html, encoding="utf-8")
    print(src.name, len(html) // 1024, "Ko")
