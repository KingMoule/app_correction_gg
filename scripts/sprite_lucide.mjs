// Génère pwa/vendor/lucide-sprite.svg : les seules icônes Lucide (ISC) utilisées par la PWA.
// Usage : npm i --prefix <dossier-temporaire> lucide-static@1.61.0
//         node scripts/sprite_lucide.mjs <dossier-temporaire>/node_modules/lucide-static
// Pour ajouter une icône : l'ajouter à ICONES, relancer, commiter le sprite.
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ICONES = [
  "house", "library", "upload", "download", "layers", "sparkles", "copy", "settings", "sliders-horizontal", "lock",
  "chevron-left", "chevron-right", "chevron-down", "chevron-up", "check", "x", "circle-check", "circle", "circle-dot",
  "circle-alert", "triangle-alert", "info", "pen", "highlighter", "eraser", "undo-2", "redo-2", "spell-check",
  "file-text", "file-up", "file-check", "file-down", "list", "table", "search", "scan-search", "users", "maximize",
  "ellipsis", "panel-right", "folder", "folder-open", "archive", "refresh-cw", "wifi", "wifi-off", "plus", "clock",
  "log-out", "eye", "arrow-right", "clipboard", "external-link", "share", "key-round", "save", "flag", "trash-2",
  "rotate-ccw", "graduation-cap", "monitor", "play", "flask-conical", "loader", "zoom-in", "inbox", "list-checks",
];

const source = process.argv[2];
if (!source) { console.error("Indique le dossier lucide-static."); process.exit(1); }
const version = JSON.parse(readFileSync(join(source, "package.json"), "utf8")).version;
const symboles = ICONES.map((nom) => {
  const svg = readFileSync(join(source, "icons", nom + ".svg"), "utf8");
  const interieur = svg.slice(svg.indexOf(">", svg.indexOf("<svg")) + 1, svg.lastIndexOf("</svg>")).trim().replace(/\s*\n\s*/g, "");
  return `<symbol id="${nom}" viewBox="0 0 24 24">${interieur}</symbol>`;
});
const sortie = `<svg xmlns="http://www.w3.org/2000/svg">\n<!-- Lucide v${version} (licence ISC : voir lucide-LICENSE.txt). Fichier généré par scripts/sprite_lucide.mjs, ne pas modifier à la main. -->\n${symboles.join("\n")}\n</svg>\n`;
const cible = join(dirname(fileURLToPath(import.meta.url)), "..", "pwa", "vendor", "lucide-sprite.svg");
writeFileSync(cible, sortie);
console.log(`${ICONES.length} icônes, ${sortie.length} octets -> ${cible}`);
