from pathlib import Path

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
    print(f"Frames inspectés   : {result['frame_count']}")
    print(f"Type probable      : {result['exercise_type']}")
    print(f"Question probable  : {result['question'] or 'Non détectée'}")
    print(f"Réponses détectées : {len(result['answers'])}")
    print(f"Boutons détectés   : {len(result['buttons'])}")
    print(f"Inputs détectés    : {len(result['inputs'])}")

    if result["answers"]:
        print("\nRéponses candidates :")
        for i, answer in enumerate(result["answers"][:20], start=1):
            print(f"{i}. {answer['text']} [{answer['kind']}]")

    if result["buttons"]:
        print("\nBoutons visibles :")
        for button in result["buttons"][:20]:
            print(f"- {button['text']}")

    print("\nDiagnostics sauvegardés dans diagnostics/.")


def main():
    logger = setup_logger()
    logger.info("Démarrage de GlobalExam Bot v0.6")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page
        session.open_global_exam()

        print("\n=== GlobalExam Bot v0.6 ===")
        print("https://general.global-exam.com/")
        print("Profil Chromium persistant + détection multi-frame.\n")

        if session.is_login_required():
            print("Connexion nécessaire.")
            print("Connecte-toi dans la fenêtre Chromium.")
            input("Une fois connecté, appuie sur Entrée... ")
            session.wait_for_login()

            if session.is_login_required():
                print("Attention : le bot pense que la connexion n'est toujours pas terminée.")
            else:
                print("Connexion détectée.")
        else:
            print("Session restaurée automatiquement.")

        while True:
            print("\nCommandes :")
            print("  a      analyser + sauvegarder les diagnostics")
            print("  frames afficher les frames/iframes")
            print("  url    afficher l'URL")
            print("  r      recharger")
            print("  q      quitter")

            cmd = input("> ").strip().lower()

            if cmd == "q":
                break

            if cmd == "url":
                print(page.url)
                continue

            if cmd == "frames":
                print("\nFrames détectés :")
                for i, frame in enumerate(page.frames):
                    print(f"{i}: {frame.url}")
                continue

            if cmd == "r":
                page.reload(wait_until="domcontentloaded")
                session.wait_until_stable()
                print("Page rechargée.")
                continue

            if cmd == "a":
                result = analyze_page(page)
                save_diagnostics(page, result, DIAGNOSTICS_DIR)
                print_summary(result)
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
