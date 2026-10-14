"""Contrôleur de migration de la nouvelle interface, en mode guidé.

Les interactions sont déclenchées explicitement par l'utilisateur. Ne lance
aucune tentative automatiquement ; permet de tester le nouveau DOM et la
lecture des corrections sans exécuter l'ancienne boucle AutoPilot.
"""
import re
import sys
import zipfile
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright
from browser import START_URL
from correction_learner import CorrectionLearner
from question_engine import QuestionEngine
from logger import setup_logger
from safety_clicks import safe_click, normalize
from site_v2.snapshot import capture_page
from site_v2.module_probe import save_module_probe
from site_v2.catalog import list_activities, ensure_module_open
from site_v2.activity_probe import open_capture_completed
from site_v2.result_probe import result_overview, capture_result_review, replay_capture, ResultReviewStore
from site_v2.intro_probe import advance_intro_and_capture
from site_v2.detector import classify_page, route_without_secrets
from site_v2.page_router import (
    kind_from_url, initial_page, needs_initial_navigation,
    page_for_kind, tab_inventory,
)

ROOT = Path(__file__).resolve().parent.parent.parent
PROFILE = ROOT / "profile"
DIAGNOSTICS = ROOT / "diagnostics" / "v2_guided"


def content_route(url):
    match = re.search(r"(/activity/[^/]+/content/[^/?#]+)", url or "")
    return match.group(1) if match else None


def quick_snapshot(page):
    path = route_without_secrets(page.url)
    controls = []
    for button in page.locator("button").all()[:120]:
        try:
            if button.is_visible():
                text = (button.inner_text() or button.get_attribute("aria-label") or "").strip()
                if text:
                    controls.append({"label": text})
        except Exception:
            pass
    return {
        "route": path,
        "document": {"visible_text": ""},
        "headings": [{"text": (h.inner_text() or "")} for h in page.locator("h1,h2").all()[:10]],
        "controls": controls,
        "links": [], "containers": [],
        "dom_counts": {"radio_inputs": page.locator("input[type=radio]").count(),
                       "draggables": page.locator(".draggable-item").count()},
    }


def modules(page):
    result = []
    for button in page.locator("button").all()[:250]:
        try:
            if not button.is_visible():
                continue
            text = (button.inner_text() or "").strip()
            match = re.match(r"MODULE\s+(\d+)\b", normalize(text), re.I)
            if match:
                result.append((int(match.group(1)), text.replace("\n", " ")[:140], button))
        except Exception:
            continue
    return result


def _result_page_in_context(current_page, context):
    """URL en priorité; le résultat peut être ouvert manuellement dans un onglet."""
    return page_for_kind(current_page, context, "result")


def _show_tabs(context, page):
    tabs = tab_inventory(context, page)
    if not tabs:
        print("Aucun onglet Playwright visible.")
        return tabs
    print(f"{len(tabs)} onglet(s) connu(s) de ce Chromium :")
    for item in tabs:
        mark = "*" if item["selected"] else " "
        focus = " [focus]" if item["focused"] else ""
        print(f" {mark} {item['index']}. [{item['kind']}] {item['route']}{focus}")
    return tabs


def main():
    PROFILE.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS.mkdir(parents=True, exist_ok=True)
    logger = setup_logger()
    print("\nGlobalExam v0.10.9 | Navigation guidée (aucun AutoPilot)")
    print("Ferme toute autre instance Chromium utilisant le même profil.")
    with sync_playwright() as play:
        context = play.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE), headless=False,
            viewport={"width": 1440, "height": 950},
            args=["--start-maximized"],
        )
        try:
            page = initial_page(context)
            if needs_initial_navigation(page):
                try:
                    page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    print("Ouverture :", type(exc).__name__, "— navigue manuellement.")
            else:
                print("Onglet existant conservé :", kind_from_url(page.url),
                      route_without_secrets(page.url))
            questions = QuestionEngine(page, logger)
            learner = CorrectionLearner(ROOT / "data", logger)
            captured = {}
            last_capture_dir = None
            help_msg = (
                "Commandes : status, onglets, onglet N, modules, module N, activities N, voir N M, "
                "inspectmodule [N], capture, captureimage, export, "
                "resultat, review, rejouer, suivantcapture, question, correction, parcours, stats, q"
            )
            print(help_msg)
            print("Tu peux aussi cliquer manuellement dans Chromium entre deux commandes.")
            while True:
                try:
                    cmd = input("v2> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if cmd.lower() in ("q", "quit", "exit"):
                    break
                if cmd.lower() in ("onglets", "tabs", "url", "urls"):
                    _show_tabs(context, page)
                    continue
                if re.fullmatch(r"(?:onglet|tab)\s+\d+", cmd.lower()):
                    index = int(cmd.split()[-1])
                    available = tab_inventory(context, page)
                    if not 1 <= index <= len(available):
                        print("Numéro d'onglet invalide ; tape 'onglets'.")
                        continue
                    page = available[index - 1]["page"]
                    questions = QuestionEngine(page, logger)
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                    print("Onglet sélectionné :", kind_from_url(page.url),
                          route_without_secrets(page.url))
                    continue
                if cmd.lower() in ("status", "s"):
                    print("URL courante :", route_without_secrets(page.url))
                    print("Détection URL :", kind_from_url(page.url))
                    snap = quick_snapshot(page)
                    print("Détection DOM :", classify_page(snap))
                elif cmd.lower() == "parcours":
                    page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
                    print("Parcours :", route_without_secrets(page.url))
                elif cmd.lower() == "modules":
                    found = modules(page)
                    if not found:
                        print("Aucun bouton MODULE visible. Ouvre le parcours.")
                    for num, label, _ in found:
                        print(f"  {num:02d} : {label}")
                elif re.fullmatch(r"module\s+\d+", cmd.lower()):
                    num = int(cmd.split()[-1])
                    chosen = next((x for x in modules(page) if x[0] == num), None)
                    if chosen:
                        expanded = chosen[2].get_attribute("aria-expanded") == "true"
                        if expanded:
                            print("Module déjà ouvert (aucun clic supplémentaire) :", chosen[1])
                        elif safe_click(chosen[2]):
                            page.wait_for_timeout(950)
                            print("Module ouvert :", chosen[1])
                        else:
                            print("Impossible d'ouvrir le module.")
                        print("Utilise 'inspectmodule' pour voir les activités internes.")
                    else:
                        print("Module non trouvé ou inaccessible.")
                elif re.fullmatch(r"(?:activities|activites)\s+\d+", cmd.lower()):
                    num = int(cmd.split()[-1])
                    if not ensure_module_open(page, num):
                        print("Impossible d'ouvrir ce module ; aucun clic d'activité effectué.")
                        continue
                    result = list_activities(page, num)
                    if not result.get("ok"):
                        print("Inspection indisponible :", result.get("reason"))
                        continue
                    labels = {"completed": "Terminée / Voir",
                              "locked": "À débloquer",
                              "special": "Spéciale (non lancée)",
                              "unverified": "Statut inconnu (non lancée)",
                              "in_progress": "En cours / Continuer"}
                    print(f"Module {num} : {len(result['activities'])} cartes détectées")
                    for item in result["activities"]:
                        print(f" {item['index']:2d}. [{labels[item['state']]}] {item['title']}")
                    print("Pour ouvrir une activité normale (Terminée ou En cours) : voir", num, "NUMERO")
                elif re.fullmatch(r"(?:voir|view|voircapture)\s+\d+\s+\d+", cmd.lower()):
                    _, mod, idx = cmd.split()
                    try:
                        trace = open_capture_completed(
                            page, context, int(mod), int(idx), DIAGNOSTICS
                        )
                        page = trace["page"]
                        questions = QuestionEngine(page, logger)
                        last_capture_dir = trace["directory"]
                        if trace["action"]["ok"]:
                            print("Activité OUVERTE et VÉRIFIÉE :", trace["action"].get("title"))
                        elif trace["action"]["clicked"]:
                            print("Clic sur la carte, mais OUVERTURE NON CONFIRMÉE.")
                        else:
                            print("Aucun clic effectué :", trace["action"].get("reason"))
                        print("Écran obtenu :", trace["screen_kind"])
                        print("URL initiale :", trace["initial_route"])
                        print("URL pré-clic :", trace["ready_route"])
                        print("URL après :", trace["after_route"])
                        print("Preuve d'activité :", trace["activity_evidence"])
                        print("Changement visible :", trace["visible_structure_changed"])
                        if trace["new_tab"]:
                            print("Nouvel onglet détecté et sélectionné.")
                        if trace["diagnostic_note"]:
                            print("Attention :", trace["diagnostic_note"])
                        print("ZIP diagnostic créé automatiquement :", trace["archive"])
                        print("Vérifie son contenu avant de le partager.")
                    except Exception as exc:
                        print("Inspection après Voir impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() in ("resultat", "result", "score"):
                    selected_result = _result_page_in_context(page, context)
                    if selected_result is None:
                        print("Aucun résultat /activity/.../result détecté par URL.")
                        _show_tabs(context, page)
                        print("Ouvre le résultat dans le Chromium lancé par run_v2.bat.")
                        continue
                    page = selected_result
                    print("Résultat détecté par URL :", route_without_secrets(page.url))
                    info = result_overview(page)
                    print("Résultat :", info.get("score"), "|", info["route"])
                    print("Questions :", len(info["questions"]))
                    for question in info["questions"]:
                        print(f"  {question['number']:2d}. {question['indicator']}")
                    print("Onglets disponibles :", ", ".join(info["tabs"]))
                    print("Commande 'review' : relire les onglets et sauvegarder dans SQLite.")
                elif cmd.lower() in ("review", "revisions", "correctionsresultat"):
                    selected_result = _result_page_in_context(page, context)
                    if selected_result is None:
                        print("Aucun résultat /activity/.../result trouvé par URL pour 'review'.")
                        _show_tabs(context, page)
                        continue
                    page = selected_result
                    print("Révision sur :", route_without_secrets(page.url))
                    try:
                        result = capture_result_review(
                            page, DIAGNOSTICS, db_path=ROOT / "data" / "knowledge.sqlite3"
                        )
                        if result.get("ok"):
                            last_capture_dir = result["directory"]
                            print("Questions relevées :", result["questions_inspected"], "/", result["questions_requested"])
                            print("Observations enregistrées en SQLite :", result["database_saved"])
                            print("Réponses apprises : inchangées (sans preuve de correspondance).")
                            if result.get("database_error"):
                                print("Erreur SQLite :", result["database_error"])
                            print("ZIP diagnostique :", result["archive"])
                            print("Vérifie son contenu avant de l'envoyer.")
                        else:
                            print("Lecture impossible :", result.get("reason"))
                    except Exception as exc:
                        print("Relevé du résultat impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() in ("rejouer", "replay"):
                    selected_result = _result_page_in_context(page, context)
                    if selected_result is None:
                        print("Aucun résultat /activity/.../result trouvé par URL pour 'rejouer'.")
                        _show_tabs(context, page)
                        print("Si tu as ouvert un autre navigateur, il n'est pas contrôlé par ce bot.")
                        continue
                    page = selected_result
                    print("Rejouer depuis l'URL :", route_without_secrets(page.url))
                    try:
                        trace = replay_capture(page, context, DIAGNOSTICS)
                        if trace.get("clicked"):
                            page = trace["page"]
                            questions = QuestionEngine(page, logger)
                            last_capture_dir = trace["directory"]
                            print("Rejouer :", "exercice confirmé" if trace["ok"] else "ouverture non confirmée")
                            print("Avant :", trace["before_route"])
                            print("Après :", trace["after_route"])
                            print("Boutons Rejouer trouvés :", trace.get("candidate_count"))
                            print("Tentatives :", trace.get("click_attempts"))
                            print("Diagnostic ZIP :", trace["archive"])
                            print("Aucune réponse n'a été soumise.")
                        else:
                            last_capture_dir = trace.get("directory")
                            print("Aucun clic :", trace.get("reason"))
                            print("Boutons Rejouer trouvés :", trace.get("candidate_count"))
                            print("Tentatives :", trace.get("click_attempts"))
                            print("Diagnostic ZIP :", trace.get("archive"))
                    except Exception as exc:
                        print("Rejouer impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() in ("suivantcapture", "suivantintro", "nextcapture"):
                    if kind_from_url(page.url) != "exercise":
                        manual_exercise = page_for_kind(page, context, "exercise")
                        if manual_exercise is not None:
                            page = manual_exercise
                    try:
                        trace = advance_intro_and_capture(page, DIAGNOSTICS)
                        if not trace.get("clicked"):
                            print("Aucun clic :", trace.get("reason"))
                            print("Cette commande n'agit que sur une introduction sans réponses.")
                        else:
                            last_capture_dir = trace["directory"]
                            print("Passage depuis l'introduction :", "confirmé" if trace["ok"] else "non confirmé")
                            print("Écran :", trace.get("screen_kind"))
                            print("Contrôles de réponse détectés :", trace.get("has_answer_controls"))
                            print("Labels détectés :", trace.get("labels_detected"))
                            print("Trace :", trace.get("before_route"), "→", trace.get("after_route"))
                            print("ZIP diagnostic :", trace["archive"])
                            print("Aucune réponse n'a été choisie ni validée.")
                    except Exception as exc:
                        print("Capture après Introduction impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() == "question":
                    if classify_page(quick_snapshot(page))["kind"] != "exercise":
                        print("Ouvre une question avant cette commande.")
                        continue
                    try:
                        packet = questions.extract_packet()
                        route = content_route(page.url)
                        if route:
                            captured[route] = packet
                        print("Question :", packet.get("instruction"))
                        print("Type :", packet.get("exercise_type"), "ID :", packet.get("question_id"))
                        for choice in packet.get("choices", []):
                            print("  ", choice.get("index"), choice.get("text"))
                        print("Question mémorisée pour comparaison avec sa correction.")
                    except Exception as exc:
                        print("Extraction impossible :", type(exc).__name__, str(exc)[:200])
                elif cmd.lower() == "correction":
                    if classify_page(quick_snapshot(page))["kind"] != "correction":
                        print("Ouvre d'abord la page /correction de cet exercice.")
                        continue
                    tab = page.get_by_role("button", name="Correction", exact=True)
                    if tab.count() and tab.first.is_visible():
                        if not safe_click(tab.first):
                            print("Impossible d'ouvrir l'onglet Correction.")
                            continue
                        page.wait_for_timeout(600)
                    route = content_route(page.url)
                    original = captured.get(route)
                    if original is None:
                        print("Question d'origine absente : utilise 'question' AVANT de valider.")
                        print("La correction peut toujours être capturée avec 'capture'.")
                        continue
                    try:
                        result = learner.record_explicit_correction(
                            page, original, original, standalone=True)
                        print("Correction enregistrée :", result.get("correction_saved"))
                        print("Solution structurée apprise :", result.get("learned"))
                        print("Verdict : inconnu (l'onglet Correction ne prouve pas une erreur)")
                    except Exception as exc:
                        print("Enregistrement impossible :", type(exc).__name__, str(exc)[:250])
                elif re.fullmatch(r"(?:inspectmodule|moduleinspect)(?:\s+\d+)?", cmd.lower()):
                    parts = cmd.split()
                    chosen_num = int(parts[1]) if len(parts) > 1 else None
                    if chosen_num:
                        chosen = next((x for x in modules(page) if x[0] == chosen_num), None)
                        if chosen is None:
                            print("Module absent :", chosen_num)
                            continue
                        if chosen[2].get_attribute("aria-expanded") != "true":
                            try:
                                chosen[2].scroll_into_view_if_needed(timeout=2500)
                            except Exception:
                                pass
                            if not safe_click(chosen[2]):
                                print("Impossible d'ouvrir le module :", chosen_num)
                                continue
                        page.wait_for_timeout(1050)
                    try:
                        path, _ = capture_page(page, "module_detail", DIAGNOSTICS)
                        details = save_module_probe(page, path, chosen_num)
                        last_capture_dir = path
                        print("Diagnostic détaillé :", path)
                        print("Module :", details.get("selected_module"),
                              "ouvert :", details.get("is_expanded"))
                        print("Nœuds :", details.get("section_nodes_seen"),
                              "cliquables :", len(details.get("section_clickables", [])),
                              "lignes texte :", len(details.get("section_text", [])))
                        for item in details.get("section_text", [])[:18]:
                            print("  •", item.get("text", "")[:140])
                        for warn in details.get("warnings", []):
                            print("Attention :", warn)
                        print("Utilise 'export' pour créer un ZIP de CE diagnostic.")
                    except Exception as exc:
                        print("Inspection impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() in ("capture", "captureimage"):
                    kind = classify_page(quick_snapshot(page))["kind"]
                    label = "module_ouvert" if kind == "catalog" else "ecran"
                    try:
                        path, _ = capture_page(
                            page, label, DIAGNOSTICS,
                            with_screenshot=(cmd.lower() == "captureimage"))
                        last_capture_dir = path
                        if kind == "catalog":
                            details = save_module_probe(page, path)
                            print("Module détecté :", details.get("selected_module"),
                                  "nœuds :", details.get("section_nodes_seen"),
                                  "cartes cliquables :", len(details.get("section_clickables", [])))
                        print("Diagnostic :", path)
                        if kind == "catalog":
                            print("Attention : c'est toujours le catalogue, pas l'écran d'activité.")
                            print("Pour ouvrir et capturer une carte terminée : voir 5 1")
                        print("Relis les fichiers avant de les partager (informations personnelles possibles).")
                        print("Utilise 'export' pour créer un ZIP de CE diagnostic.")
                    except Exception as exc:
                        print("Capture impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() == "export":
                    if last_capture_dir is None:
                        print("Commence par 'inspectmodule 5' ou 'capture'.")
                        continue
                    archive = last_capture_dir.with_suffix(".zip")
                    try:
                        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                            for file in last_capture_dir.iterdir():
                                if file.is_file():
                                    z.write(file, file.name)
                        print("Archive créée :", archive)
                        print("Vérifie son contenu avant de l'envoyer.")
                    except Exception as exc:
                        print("Export impossible :", type(exc).__name__, str(exc)[:250])
                elif cmd.lower() in ("help", "aide", "?"):
                    print(help_msg)
                elif cmd.lower() == "stats":
                    stats = learner.stats()
                    try:
                        stats["result_reviews"] = ResultReviewStore(ROOT / "data" / "knowledge.sqlite3").count()
                    except Exception:
                        pass
                    print(stats)
                else:
                    print(help_msg)
        finally:
            context.close()


if __name__ == "__main__":
    main()
