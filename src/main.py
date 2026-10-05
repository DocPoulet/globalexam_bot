from pathlib import Path
import json

from browser import BrowserSession
from detector import analyze_page
from diagnostics import save_diagnostics
from logger import setup_logger

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"


def print_summary(result):
    print("\n=== Résumé de détection ===")
    print(f"URL                : {result['url']}")
    print(f"Titre              : {result['title']}")
    print(f"Connexion requise  : {result['login_required']}")
    print(f"Type probable      : {result['exercise_type']}")
    print(f"Question probable  : {result['question'] or 'Non détectée'}")
    print(f"Réponses détectées : {len(result['answers'])}")
    print(f"Boutons détectés   : {len(result['buttons'])}")
    print(f"Inputs détectés    : {len(result['inputs'])}")

    if result["answers"]:
        print("\nRéponses candidates :")
        for i, answer in enumerate(result["answers"][:20], start=1):
            print(f"{i}. {answer}")

    if result["buttons"]:
        print("\nBoutons visibles :")
        for button in result["buttons"][:20]:
            print(f"- {button}")

    print("\nDiagnostics sauvegardés dans le dossier diagnostics/.")


def main():
    logger = setup_logger()
    logger.info("Démarrage de GlobalExam Bot v0.5")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page
        session.open_global_exam()

        print("\n=== GlobalExam Bot v0.5 ===")
        print("URL corrigée : https://general.global-exam.com/")
        print("Le navigateur utilise maintenant un profil Chromium persistant complet.\n")

        if session.is_login_required():
            print("Aucune session valide détectée.")
            print("Connecte-toi manuellement dans Chromium.")
            input("Quand tu es connecté et arrivé sur GlobalExam, appuie sur Entrée... ")
            session.wait_until_stable()
        else:
            print("Session déjà active : aucune reconnexion nécessaire.")

        while True:
            print("\nCommandes :")
            print("  a    = analyser la page")
            print("  url  = afficher l'URL actuelle")
            print("  dump = sauvegarder tous les diagnostics")
            print("  r    = recharger")
            print("  q    = quitter")

            cmd = input("> ").strip().lower()

            if cmd == "q":
                break

            if cmd == "url":
                print(page.url)
                continue

            if cmd == "r":
                page.reload(wait_until="domcontentloaded")
                session.wait_until_stable()
                print("Page rechargée.")
                continue

            if cmd in ("a", "dump"):
                result = analyze_page(page)
                save_diagnostics(page, result, DIAGNOSTICS_DIR)
                print_summary(result)
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
