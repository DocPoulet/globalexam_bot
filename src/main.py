from pathlib import Path

from actions import ActivityActions
from browser import BrowserSession
from detector import analyze_page
from diagnostics import save_diagnostics
from logger import setup_logger

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"


def print_analysis(result):
    print("\n=== Analyse GlobalExam ===")
    print(f"Page        : {result['page_kind']}")
    print(f"URL         : {result['url']}")
    print(f"Titre       : {result['title']}")

    if result["page_kind"] != "activity":
        print("Aucun exercice actif sur cette page.")
        return

    print(f"Type        : {result['exercise_type']}")
    print(f"Question    : {result['question'] or 'Non détectée'}")
    print(f"Nb réponses : {len(result['answers'])}")

    if result["answers"]:
        print("\nRéponses / éléments :")
        for i, answer in enumerate(result["answers"], start=1):
            if answer.get("kind") == "select":
                print(f"{i}. <liste déroulante>")
            else:
                print(f"{i}. {answer.get('text', '')} [{answer.get('kind')}]")

    if result["actions"]:
        print("\nActions détectées :")
        for action in result["actions"]:
            print(f"- {action['text']} [{action['kind']}]")


def main():
    logger = setup_logger()
    logger.info("Démarrage GlobalExam Bot v0.6.1")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page
        session.open_global_exam()
        actions = ActivityActions(page)

        print("\n=== GlobalExam Bot v0.6.1 ===")

        if session.is_login_required():
            print("Connexion nécessaire.")
            print("Connecte-toi dans Chromium puis appuie sur Entrée.")
            input("> ")
            session.wait_until_stable()

        while True:
            print("\nCommandes :")
            print("  a                 analyser la page")
            print("  drag X Y          déplacer l'élément X vers Y")
            print("  click X           cliquer sur l'élément draggable X")
            print("  skip              cliquer sur Passer")
            print("  r                 recharger")
            print("  url               afficher l'URL")
            print("  q                 quitter")

            cmd = input("> ").strip()

            if cmd.lower() == "q":
                break

            if cmd.lower() == "url":
                print(page.url)
                continue

            if cmd.lower() == "r":
                page.reload(wait_until="domcontentloaded")
                session.wait_until_stable()
                continue

            if cmd.lower() == "a":
                result = analyze_page(page)
                save_diagnostics(page, result, DIAGNOSTICS_DIR)
                print_analysis(result)
                continue

            if cmd.lower() == "skip":
                if actions.click_action("Passer"):
                    session.wait_until_stable()
                    print("Passer cliqué.")
                else:
                    print("Bouton Passer non trouvé.")
                continue

            if cmd.lower().startswith("click "):
                parts = cmd.split()

                try:
                    index = int(parts[1]) - 1
                except Exception:
                    print("Usage : click 1")
                    continue

                if actions.click_draggable(index):
                    print("Élément cliqué.")
                else:
                    print("Élément introuvable.")
                continue

            if cmd.lower().startswith("drag "):
                parts = cmd.split()

                try:
                    source = int(parts[1]) - 1
                    target = int(parts[2]) - 1
                except Exception:
                    print("Usage : drag 1 3")
                    continue

                try:
                    ok = actions.drag_item(source, target)
                except Exception as exc:
                    print(f"Drag impossible : {exc}")
                    continue

                print("Déplacement effectué." if ok else "Indices invalides.")
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
