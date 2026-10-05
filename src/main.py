from pathlib import Path

from adapter_registry import AdapterRegistry
from browser import BrowserSession
from common_actions import find_actions, click_common_action
from diagnostics import save_analysis
from logger import setup_logger
from page_router import classify_page

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"


def print_analysis(page, adapter, analysis):
    print("\n=== Analyse ===")
    print(f"Page       : {classify_page(page)}")
    print(f"Adaptateur : {analysis['adapter']}")
    print(f"Type       : {analysis['exercise_type']}")
    print(f"Question   : {analysis.get('question') or 'Non détectée'}")

    answers = analysis.get("answers", [])
    print(f"Éléments   : {len(answers)}")

    if answers:
        print("\nContenu détecté :")

        for i, answer in enumerate(answers, start=1):
            if "text" in answer:
                print(f"{i}. {answer['text']}")
            elif "options" in answer:
                print(f"{i}. liste avec {len(answer['options'])} options")
            else:
                print(f"{i}. {answer}")

    actions = find_actions(page)

    if actions:
        print("\nActions communes :")
        for action in actions:
            print(f"- {action['text']} [{action['kind']}]")


def main():
    logger = setup_logger()
    logger.info("Démarrage GlobalExam Bot v0.7")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page
        session.open_global_exam()

        print("\n=== GlobalExam Bot v0.7 ===")
        print("Architecture par adaptateurs.\n")

        if session.is_login_required():
            print("Connexion nécessaire.")
            print("Connecte-toi dans Chromium puis appuie sur Entrée.")
            input("> ")
            session.wait_until_stable()

        registry = AdapterRegistry(page)

        while True:
            print("\nCommandes :")
            print("  a                    analyser")
            print("  adapters             liste des adaptateurs")
            print("  drag X Y             déplacer un draggable")
            print("  choose X             sélectionner un choix QCM")
            print("  select X Y           choisir option Y dans liste X")
            print("  fill X texte         remplir un champ")
            print("  skip                 Passer")
            print("  validate             Valider")
            print("  next                 Suivant")
            print("  r                    recharger")
            print("  q                    quitter")

            cmd = input("> ").strip()

            if cmd.lower() == "q":
                break

            if cmd.lower() == "r":
                page.reload(wait_until="domcontentloaded")
                session.wait_until_stable()
                continue

            if cmd.lower() == "adapters":
                for info in AdapterRegistry.available():
                    print(f"- {info['name']} (priorité {info['priority']})")
                continue

            adapter = registry.detect()

            if not adapter:
                print("Aucun adaptateur disponible.")
                continue

            if cmd.lower() == "a":
                analysis = adapter.analyze()
                save_analysis(page, analysis, DIAGNOSTICS_DIR)
                print_analysis(page, adapter, analysis)
                continue

            if cmd.lower() in ("skip", "validate", "next"):
                if click_common_action(page, cmd.lower()):
                    session.wait_until_stable()
                    print(f"Action {cmd.lower()} effectuée.")
                else:
                    print("Action non trouvée.")
                continue

            if cmd.lower().startswith("drag "):
                action = adapter.actions().get("drag")

                if not action:
                    print("L'adaptateur courant ne gère pas le drag.")
                    continue

                try:
                    _, a, b = cmd.split(maxsplit=2)
                    ok = action(int(a) - 1, int(b) - 1)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                print("OK" if ok else "Échec")
                continue

            if cmd.lower().startswith("choose "):
                action = adapter.actions().get("choose")

                if not action:
                    print("L'adaptateur courant ne gère pas choose.")
                    continue

                try:
                    index = int(cmd.split()[1]) - 1
                    ok = action(index)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                print("OK" if ok else "Échec")
                continue

            if cmd.lower().startswith("select "):
                action = adapter.actions().get("choose_select")

                if not action:
                    print("L'adaptateur courant ne gère pas select.")
                    continue

                try:
                    _, a, b = cmd.split()
                    ok = action(int(a) - 1, int(b) - 1)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                print("OK" if ok else "Échec")
                continue

            if cmd.lower().startswith("fill "):
                action = adapter.actions().get("fill")

                if not action:
                    print("L'adaptateur courant ne gère pas fill.")
                    continue

                try:
                    _, index, value = cmd.split(maxsplit=2)
                    ok = action(int(index) - 1, value)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                print("OK" if ok else "Échec")
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
