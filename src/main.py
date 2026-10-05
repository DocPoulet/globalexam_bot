from pathlib import Path

from adapter_registry import AdapterRegistry
from browser import BrowserSession
from common_actions import click_common_action, find_actions
from exercise_launcher import ExerciseLauncher
from flow_controller import FlowController
from logger import setup_logger
from state_probe import snapshot, diff

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"


def show_analysis(page, adapter):
    analysis = adapter.analyze()

    print("\n=== Analyse ===")
    print(f"URL        : {page.url}")
    print(f"Adaptateur : {analysis['adapter']}")
    print(f"Type       : {analysis['exercise_type']}")
    print(f"Question   : {analysis.get('question') or 'Non détectée'}")

    answers = analysis.get("answers", [])

    if answers:
        print("\nRéponses / éléments :")
        for i, item in enumerate(answers, start=1):
            if "text" in item:
                print(f"{i}. {item['text']}")
            else:
                print(f"{i}. {item}")

    if analysis.get("placed"):
        print("\nDéjà sélectionnés :")
        for i, item in enumerate(analysis["placed"], start=1):
            print(f"{i}. {item['text']}")

    actions = find_actions(page)

    if actions:
        print("\nActions visibles :")
        for action in actions:
            state = "désactivé" if action["disabled"] else "actif"
            print(f"- {action['text']} [{action['kind']}, {state}]")


def main():
    logger = setup_logger()
    logger.info("Démarrage GlobalExam Bot v0.7.3")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page

        print("\n=== GlobalExam Bot v0.7.3 ===")
        print("Ouverture directe de la liste d'exercices.\n")

        session.open_start_page()

        if session.is_login_required():
            print("Connexion nécessaire.")
            print("Connecte-toi dans Chromium puis appuie sur Entrée.")
            input("> ")

            # Après connexion, on revient explicitement à la liste voulue.
            session.go_to_exercise_list()

        launcher = ExerciseLauncher(page, logger)
        flow = FlowController(page, logger)

        print("Recherche d'un vrai exercice disponible...")

        if launcher.launch_first_available():
            print(f"Exercice lancé : {page.url}")
            result = flow.advance_until_question()
            print(
                f"Progression automatique : "
                f"{result['state']} ({result['steps']} étape(s))"
            )
        else:
            print(
                "Aucun exercice n'a pu être lancé automatiquement.\n"
                "La page de liste reste ouverte. Utilise la commande 'launch' "
                "pour réessayer après avoir vérifié la page."
            )

        registry = AdapterRegistry(page)

        while True:
            print("\nCommandes :")
            print("  a             analyser")
            print("  select X      sélectionner la réponse X")
            print("  fallback X    drag de secours")
            print("  validate      Valider")
            print("  next          Suivant")
            print("  skip          Passer")
            print("  list          revenir à la liste d'exercices")
            print("  launch        lancer le premier exercice disponible")
            print("  blocks        afficher les blocs mb-10 + lg:mb-16")
            print("  menus         afficher les cards de contenu détectées")
            print("  active        afficher le menu actuellement ouvert")
            print("  advance       avancer jusqu’à la prochaine question")
            print("  r             recharger")
            print("  q             quitter")

            cmd = input("> ").strip()
            low = cmd.lower()

            if low == "q":
                break

            if low == "r":
                page.reload(wait_until="domcontentloaded")
                session.wait_until_stable()
                continue

            if low == "list":
                session.go_to_exercise_list()
                print(f"Liste ouverte : {page.url}")
                continue

            if low == "launch":
                if launcher.launch_first_available():
                    print(f"Exercice lancé : {page.url}")
                    result = flow.advance_until_question()
                    print(
                        f"Progression automatique : "
                        f"{result['state']} ({result['steps']} étape(s))"
                    )
                else:
                    print("Aucun vrai exercice détecté/lancé.")
                continue

            if low == "advance":
                result = flow.advance_until_question()
                print(
                    f"Progression automatique : "
                    f"{result['state']} ({result['steps']} étape(s))"
                )
                continue

            if low == "blocks":
                blocks = launcher.describe_blocks()
                print(f"\n{len(blocks)} bloc(s) candidat(s) :")
                for block in blocks:
                    print(
                        f"{block['index']}. "
                        f"{'[visible]' if block['visible'] else '[caché]'} "
                        f"{'[checkpoint] ' if block.get('checkpoint') else ''}"
                        f"{block['text'][:220]}"
                    )
                continue

            if low == "menus":
                menus = launcher.describe_menus()
                print(f"\n{len(menus)} menu(s) de contenu :")
                for menu in menus:
                    print(
                        f"{menu['index']}. "
                        f"{'[visible]' if menu['visible'] else '[caché]'} "
                        f"{'[ouvert] ' if menu.get('expanded') else '[fermé] '}"
                        f"{menu['text'][:220]}"
                    )
                continue

            if low == "active":
                active = launcher._expanded_menu()
                if active is None:
                    print("Aucun menu de contenu ouvert.")
                else:
                    try:
                        text = active.inner_text().strip()
                    except Exception:
                        text = ""
                    print(f"Menu ouvert : {text[:500]}")
                continue

            adapter = registry.detect()

            if not adapter:
                print("Aucun adaptateur.")
                continue

            if low == "a":
                show_analysis(page, adapter)
                continue

            if low in ("validate", "next", "skip"):
                ok = click_common_action(page, low)
                print("OK" if ok else f"Aucun bouton {low} actif trouvé.")
                session.wait_until_stable()

                if ok and low in ("next", "skip"):
                    result = flow.advance_until_question()
                    print(
                        f"Progression automatique : "
                        f"{result['state']} ({result['steps']} étape(s))"
                    )
                continue

            if low.startswith("select "):
                action = adapter.actions().get("select")

                if not action:
                    print("Cet exercice ne gère pas encore select.")
                    continue

                try:
                    index = int(cmd.split()[1]) - 1
                except Exception:
                    print("Usage : select 1")
                    continue

                before = snapshot(page, adapter)

                try:
                    ok = action(index)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                after_adapter = registry.detect()
                after = snapshot(page, after_adapter)

                print("Clic effectué." if ok else "Échec du clic.")

                changes = diff(before, after)

                if changes:
                    print("Changements détectés :")
                    for change in changes:
                        print(f"- {change}")
                else:
                    print("Aucun changement détecté après le clic.")

                if not flow.has_answerable_question():
                    result = flow.advance_until_question()
                    print(
                        f"Progression automatique : "
                        f"{result['state']} ({result['steps']} étape(s))"
                    )

                continue

            if low.startswith("fallback "):
                action = adapter.actions().get("drag_fallback")

                if not action:
                    print("Pas de fallback drag pour cet exercice.")
                    continue

                try:
                    index = int(cmd.split()[1]) - 1
                    ok = action(index)
                except Exception as exc:
                    print(f"Erreur : {exc}")
                    continue

                print("Fallback effectué." if ok else "Échec du fallback.")
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
