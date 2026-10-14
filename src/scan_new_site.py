"""Explorateur interactif de la nouvelle interface GlobalExam (sans autopilot).

Usage : python src/scan_new_site.py [--start-url https://general.global-exam.com/]
"""
import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from site_v2.detector import is_globalexam_host, route_without_secrets
from site_v2.snapshot import capture_page

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profile"
SCANS = ROOT / "diagnostics" / "site_scan"
HOME = "https://general.global-exam.com/"


def _make_zip(folder, session_id):
    """Empaquette seulement les diagnostics de cette session."""
    target = SCANS / f"diagnostic_nouveau_globalexam_{session_id}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, arcname=f"site_scan/{path.relative_to(folder)}")
    return target


def _capture(page, label, session_dir, screenshot=False):
    if not is_globalexam_host(page.url):
        print("Capture ignorée : onglet extérieur à global-exam.com.")
        return None
    if "auth.global-exam.com" in (urlsplit(page.url).hostname or "").lower():
        print("Capture refusée sur la page de connexion. Connecte-toi d'abord.")
        return None
    dest, report = capture_page(page, label, session_dir, with_screenshot=screenshot)
    kind = report["detected"]["kind"]
    confidence = report["detected"]["confidence"]
    print(f"[CAPTURE] {label} → {dest.name}")
    print(f"  Détecté : {kind} (confiance {confidence:.0%})")
    print(f"  {len(report['controls'])} contrôles, "
          f"{len(report['containers'])} conteneurs, "
          f"{len(report['frames'])} frame(s)")
    if screenshot:
        print("  Image enregistrée (pense à masquer tes infos personnelles avant partage).")
    return dest


def _help():
    print("""
COMMANDES (navigue dans Chromium, puis reviens dans ce terminal) :
  1      photographier la structure de l'ACCUEIL
  2      photographier la structure d'un PARCOURS / CATALOGUE
  3      photographier la structure d'un EXERCICE
  4      photographier la structure de la CORRECTION
  5      photographier la structure du RÉSULTAT
  s      photographier la structure de l'écran courant (nom automatique)
  image  capture structure + screenshot de l'écran courant (facultatif)
  url    afficher la route courante (sans paramètres privés)
  h      réafficher les commandes
  q      terminer, créer un ZIP récapitulatif

ATTENTION : cet outil ne clique pas et ne répond pas aux exercices.
          Ne joins jamais le dossier profile/ ou data/ au diagnostic.
""")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reconnaissance du nouveau GlobalExam")
    parser.add_argument("--start-url", default=HOME)
    args = parser.parse_args(argv)
    if not is_globalexam_host(args.start_url):
        parser.error("--start-url doit appartenir à global-exam.com")
    PROFILE.mkdir(parents=True, exist_ok=True)
    SCANS.mkdir(parents=True, exist_ok=True)
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = SCANS / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== GlobalExam Bot v0.10.1 — Reconnaissance du nouveau site ===")
    print("AutoPilot volontairement DÉSACTIVÉ pendant la reconnaissance.")
    print("Le profil navigateur, SQLite et le modèle GGUF sont conservés.")
    print("Ferme l'ancien bot et sa fenêtre Chromium avant de démarrer ce mode.")
    print("\nOuverture du navigateur avec ton profil habituel…")

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            viewport={"width": 1440, "height": 950},
            args=["--start-maximized"],
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(args.start_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                print(f"Ouverture initiale non terminée ({type(exc).__name__}).")
                print("Tu peux naviguer manuellement dans Chromium.")

            _help()
            labels = {
                "1": "accueil", "2": "parcours", "3": "exercice",
                "4": "correction", "5": "resultat",
            }
            captured = 0
            while True:
                try:
                    cmd = input("scan> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if cmd in ("q", "quit", "exit"):
                    break
                if cmd in ("h", "help", "?"):
                    _help()
                    continue
                if cmd == "url":
                    active = context.pages[-1] if context.pages else page
                    print(route_without_secrets(active.url))
                    continue
                if cmd not in (*labels.keys(), "s", "image", ""):
                    print("Commande inconnue. Tape h pour l'aide.")
                    continue
                active = context.pages[-1] if context.pages else page
                if active.is_closed():
                    print("L'onglet est fermé. Ouvre une page dans Chromium.")
                    continue
                label = labels.get(cmd, "auto")
                screenshot = cmd == "image"
                try:
                    result = _capture(active, label, session_dir, screenshot)
                    captured += bool(result)
                except Exception as exc:
                    print(f"Capture impossible : {type(exc).__name__}: {exc}")
            print(f"\n{captured} écran(s) capturé(s).")
        finally:
            context.close()

    if any(p.is_file() for p in session_dir.rglob("*")):
        result = _make_zip(session_dir, session_id)
        print(f"Diagnostic créé : {result}")
        print("Relis les JSON et images avant de partager le ZIP.")
    else:
        print("Aucune capture ; aucun ZIP créé.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Erreur : {type(exc).__name__}: {exc}")
        sys.exit(1)
