from pathlib import Path
import json

from autopilot import AutoPilot
from browser import BrowserSession
from common_actions import click_common_action
from correction_learner import CorrectionLearner
from exercise_launcher import ExerciseLauncher
from flow_controller import FlowController
from logger import setup_logger
from question_diagnostics import QuestionDiagnostics
from question_engine import QuestionEngine

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_DIR = BASE_DIR / "profile"
DIAGNOSTICS_DIR = BASE_DIR / "diagnostics"
DATA_DIR = BASE_DIR / "data"


def print_question(analysis):
    print("\n=== Question ===")
    print(f"Type       : {analysis.get('exercise_type')}")
    print(f"Adaptateur : {analysis.get('adapter')}")
    print(f"Consigne   : {analysis.get('question') or 'Non détectée'}")

    answers = analysis.get("answers", [])

    if analysis.get("exercise_type") == "select":
        for field in answers:
            print(f"\nChamp {field['index'] + 1} :")
            for option in field["options"]:
                marker = " *" if str(option.get("value")) == str(field.get("value")) else ""
                print(
                    f"  {option['index'] + 1}. "
                    f"{option['text']} [{option.get('value')}]"
                    f"{marker}"
                )

    elif analysis.get("exercise_type") == "text_input":
        for field in answers:
            print(
                f"{field['index'] + 1}. "
                f"placeholder={field['placeholder']!r} "
                f"value={field['value']!r}"
            )

    else:
        for i, item in enumerate(answers, start=1):
            flags = []
            if item.get("selected"):
                flags.append("sélectionné")
            if item.get("state"):
                flags.append(str(item["state"]))

            suffix = f" [{' / '.join(flags)}]" if flags else ""
            print(f"{i}. {item.get('text', item)}{suffix}")

        placed = analysis.get("placed", [])
        if placed:
            print("\nOrdre déjà placé :")
            for i, item in enumerate(placed, start=1):
                print(f"{i}. {item['text']}")

    actions = analysis.get("actions", [])
    if actions:
        print("\nActions :")
        for action in actions:
            state = "désactivé" if action["disabled"] else "actif"
            print(f"- {action['kind']}: {action['text']} ({state})")


def print_help():
    print("\nCommandes :")
    print("  question / a       analyser la question")
    print("  packet             afficher le paquet JSON pour l'IA")
    print("  savepacket         sauvegarder ce paquet JSON")
    print("  learnstats         statistiques de la mémoire locale")
    print("  history N          N dernières tentatives mémorisées")
    print("  known              réponse déjà apprise pour cette question")
    print("  select X           sélectionner/clicker la réponse X")
    print("  choose F O         champ select F -> option O")
    print("  fill F TEXTE       remplir le champ texte F")
    print("  validate           valider puis avancer")
    print("  auto               relancer le pilote autonome")
    print("  autoq              auto local si Passer/Validate, clique Suivant si présent")
    print("  fallback X         drag de secours pour classement")
    print("  advance            avancer hors-question")
    print("  controls           afficher les contrôles visibles du flow")
    print("  screen             afficher le type d\'écran détecté")
    print("  next / skip        action manuelle + progression")
    print("  list               revenir à la liste")
    print("  launch             lancer un exercice")
    print("  menus              afficher les menus de contenu")
    print("  active             menu actuellement ouvert")
    print("  blocks             exercices du menu actif")
    print("  r                  recharger")
    print("  q                  quitter")


def auto_handle_passer_questions(questions, flow, max_questions=50):
    """
    Boucle autonome de transition/question.

    Règles :
    - si "Suivant" apparaît : cliquer immédiatement dessus ;
    - si "Passer" OU Validate/Valider apparaît : traiter la question ;
    - attendre brièvement après l'arrivée sur une nouvelle question pour
      laisser le DOM finir de rendre les actions.
    """
    handled_count = 0
    transition_count = 0

    while handled_count < max_questions and transition_count < 100:
        marker = questions.wait_for_auto_marker_or_next()

        if marker == "next":
            if not click_common_action(questions.page, "next"):
                break

            transition_count += 1
            result = flow.advance_until_question()

            print(
                f"AutoQ transition : Suivant -> "
                f"{result.get('state')} ({result.get('steps', 0)} étape(s))"
            )

            if result.get("state") != "question":
                break

            continue

        if marker != "question":
            break

        result = questions.auto_answer_passer_exercise()

        if not result.get("handled"):
            break

        handled_count += 1

        print(
            f"AutoQ #{handled_count} : "
            f"action={result.get('action')} "
            f"x{result.get('action_steps', 0)} -> "
            f"{result.get('finish_action')}"
        )

        flow_result = result.get("flow")

        if not flow_result:
            break

        if flow_result.get("state") != "question":
            break

        transition_count += 1

    return handled_count


def main():
    logger = setup_logger()
    logger.info("Démarrage GlobalExam Bot v0.9.1")

    with BrowserSession(PROFILE_DIR, logger) as session:
        page = session.page

        print("\n=== GlobalExam Bot v0.9.1 ===")
        print("Moteur de questions multi-format.\n")

        session.open_start_page()

        if session.is_login_required():
            print("Connexion nécessaire.")
            print("Connecte-toi dans Chromium puis appuie sur Entrée.")
            input("> ")
            session.go_to_exercise_list()

        launcher = ExerciseLauncher(page, logger)
        flow = FlowController(page, logger)
        diagnostics = QuestionDiagnostics(DIAGNOSTICS_DIR, logger)
        learner = CorrectionLearner(DATA_DIR, logger)
        questions = QuestionEngine(
            page,
            logger,
            diagnostics=diagnostics,
            flow=flow,
            learner=learner,
        )
        autopilot = AutoPilot(
            page,
            logger,
            launcher,
            flow,
            questions,
        )

        print("Pilote autonome démarré...")
        auto_result = autopilot.run()

        print(
            f"\nPilote autonome arrêté : {auto_result['state']} "
            f"après {auto_result['cycles']} cycle(s)."
        )
        if auto_result.get("diagnostic"):
            print(f"Diagnostic : {auto_result['diagnostic']}")
        print("Les commandes manuelles restent disponibles pour le debug.")

        while True:
            print_help()
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
                    print(f"Écran exercice/résultat atteint : {page.url}")
                    result = autopilot.run()
                    print(
                        f"Pilote autonome arrêté : {result['state']} "
                        f"après {result['cycles']} cycle(s)."
                    )
                else:
                    print("Aucun exercice détecté/lancé.")
                continue

            if low == "advance":
                result = flow.advance_until_question()
                print(
                    f"Progression : {result['state']} "
                    f"({result['steps']} étape(s))"
                )
                if result["state"] == "question":
                    print_question(questions.inspect())
                continue

            if low == "controls":
                controls = flow.debug_controls()
                print(f"\n{len(controls)} contrôle(s) visible(s) :")
                for item in controls:
                    print(f"- {item['text']} | frame={item['frame']}")
                continue

            if low == "screen":
                print(f"Écran détecté : {flow.detect_screen_kind()}")
                continue

            if low == "auto":
                result = autopilot.run()
                print(
                    f"Pilote autonome arrêté : {result['state']} "
                    f"après {result['cycles']} cycle(s)."
                )
                if result.get("diagnostic"):
                    print(f"Diagnostic : {result['diagnostic']}")
                continue

            if low == "autoq":
                count = auto_handle_passer_questions(questions, flow)
                print(f"{count} question(s) traitée(s) automatiquement.")
                if flow.detect_screen_kind() == "exercise":
                    print_question(questions.inspect())
                continue

            if low in ("question", "a"):
                print_question(questions.inspect())
                continue

            if low == "packet":
                packet = questions.extract_packet()
                print("\n=== Question packet v1.0 ===")
                print(json.dumps(packet, ensure_ascii=False, indent=2))
                continue

            if low == "savepacket":
                packet = questions.extract_packet()
                path = diagnostics.save_packet(packet)
                print(f"Packet sauvegardé : {path}")
                continue

            if low == "learnstats":
                stats = learner.stats()
                print("\n=== Mémoire locale ===")
                print(f"Questions       : {stats['questions']}")
                print(f"Tentatives      : {stats['attempts']}")
                print(f"Réponses apprises : {stats['learned_answers']}")
                print(f"Résultats       : {stats['outcomes']}")
                print(f"Base            : {stats['database']}")
                continue

            if low.startswith("history"):
                parts = cmd.split()
                limit = 10
                if len(parts) >= 2:
                    try:
                        limit = int(parts[1])
                    except ValueError:
                        print("Usage : history 10")
                        continue

                rows = learner.recent_attempts(limit)
                print(f"\n=== {len(rows)} tentative(s) récente(s) ===")
                for row in rows:
                    instruction = (row.get('instruction') or '').replace('\n', ' ')
                    print(
                        f"#{row['id']} {row['outcome']} "
                        f"[{row['exercise_type']}] "
                        f"{instruction[:100]}"
                    )
                continue

            if low == "known":
                known = questions.learned_answer_for_current()
                if known is None:
                    print("Aucune réponse apprise pour cette question.")
                else:
                    print(json.dumps(known, ensure_ascii=False, indent=2))
                continue

            if low == "menus":
                menus = launcher.describe_menus()
                print(f"\n{len(menus)} menu(s) :")
                for menu in menus:
                    print(
                        f"{menu['index']}. "
                        f"{'[ouvert]' if menu.get('expanded') else '[fermé]'} "
                        f"{menu['text'][:220]}"
                    )
                continue

            if low == "active":
                active = launcher._expanded_menu()
                if active is None:
                    print("Aucun menu ouvert.")
                else:
                    try:
                        text = active.inner_text().strip()
                    except Exception:
                        text = ""
                    print(f"Menu ouvert : {text[:500]}")
                continue

            if low == "blocks":
                blocks = launcher.describe_blocks()
                print(f"\n{len(blocks)} exercice(s) :")
                for block in blocks:
                    print(
                        f"{block['index']}. "
                        f"{'[checkpoint] ' if block.get('checkpoint') else ''}"
                        f"{block['text'][:220]}"
                    )
                continue

            if low.startswith("select "):
                try:
                    index = int(cmd.split()[1]) - 1
                except Exception:
                    print("Usage : select 1")
                    continue

                result = questions.select(index)
                print("Sélection OK." if result["ok"] else f"Échec : {result['reason']}")
                print_question(questions.inspect())
                continue

            if low.startswith("choose "):
                parts = cmd.split()
                if len(parts) != 3:
                    print("Usage : choose 1 2")
                    continue

                try:
                    field_index = int(parts[1]) - 1
                    option_index = int(parts[2]) - 1
                except ValueError:
                    print("Usage : choose 1 2")
                    continue

                result = questions.choose(field_index, option_index)
                print("Choix OK." if result["ok"] else f"Échec : {result['reason']}")
                print_question(questions.inspect())
                continue

            if low.startswith("fill "):
                parts = cmd.split(maxsplit=2)
                if len(parts) < 3:
                    print("Usage : fill 1 texte à saisir")
                    continue

                try:
                    field_index = int(parts[1]) - 1
                except ValueError:
                    print("Usage : fill 1 texte à saisir")
                    continue

                result = questions.fill(field_index, parts[2])
                print("Texte saisi." if result["ok"] else f"Échec : {result['reason']}")
                print_question(questions.inspect())
                continue

            if low == "validate":
                result = questions.validate()

                if not result["ok"]:
                    print(f"Échec : {result['reason']}")
                else:
                    print("Validation effectuée.")
                    learning = result.get("learning")
                    if learning:
                        print(
                            "Mémoire : "
                            f"{learning.get('outcome')} | "
                            f"apprise={learning.get('learned', False)}"
                        )
                    flow_result = result.get("flow")
                    if flow_result:
                        print(
                            f"Progression : {flow_result['state']} "
                            f"({flow_result['steps']} étape(s))"
                        )
                        if flow_result["state"] == "question":
                            print_question(questions.inspect())
                continue

            if low == "skip":
                skip_result = questions.skip()
                if not skip_result["ok"]:
                    print("Aucun bouton skip actif trouvé.")
                else:
                    print("Skip effectué et mémorisé.")
                    result = skip_result.get("flow")
                    if result:
                        print(
                            f"Progression : {result['state']} "
                            f"({result['steps']} étape(s))"
                        )
                        if result["state"] == "question":
                            print_question(questions.inspect())
                continue

            if low == "next":
                ok = click_common_action(page, "next")
                print("OK" if ok else "Aucun bouton next actif trouvé.")

                if ok:
                    result = flow.advance_until_question()
                    print(
                        f"Progression : {result['state']} "
                        f"({result['steps']} étape(s))"
                    )
                    if result["state"] == "question":
                        print_question(questions.inspect())
                continue

            if low.startswith("fallback "):
                try:
                    index = int(cmd.split()[1]) - 1
                except Exception:
                    print("Usage : fallback 1")
                    continue

                result = questions.fallback(index)
                print(
                    "Fallback effectué."
                    if result["ok"]
                    else f"Échec : {result['reason']}"
                )
                print_question(questions.inspect())
                continue

            print("Commande inconnue.")


if __name__ == "__main__":
    main()
