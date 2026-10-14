"""Inspection guidée des résultats GlobalExam V2, sans soumission de réponse.

Un écran /result contient une liste de questions et trois onglets :
Vos réponses, Correction, Explication. Les descriptions de correction sont
persistées comme observations brutes, pas comme réponses validées/apprises.
"""
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from safety_clicks import safe_click, normalize
from .detector import is_globalexam_host, route_without_secrets
from .page_router import kind_from_url
from .snapshot import capture_page, redact_text

RESULT_PATH = re.compile(r"^/activity/[^/]+/result/?$")
EXERCISE_PATH = re.compile(r"^/activity/[^/]+/content/[^/]+/?$")
TABS = ("Vos réponses", "Correction", "Explication")


def is_result(page):
    """L'URL /activity/<id>/result suffit, même si le DOM est incomplet."""
    return kind_from_url(page.url) == "result"


def _body_text(page):
    for selector in ("main", "[role='main']", "body"):
        try:
            loc = page.locator(selector)
            if loc.count():
                txt = loc.first.inner_text(timeout=1500).strip()
                if txt:
                    return redact_text(txt[:18000])
        except Exception:
            pass
    return ""


def _buttons(page, text):
    """Candidats EXACTS, dans l'ordre, même si plusieurs CTA sont dupliqués.

    Certains écrans résultat présentent plusieurs boutons « Rejouer
    l'activité ». Le premier peut être recouvert par un calque et Playwright
    refuser son clic, alors qu'un autre fonctionne. Ne jamais forcer le clic.
    """
    results = []
    try:
        loc = page.get_by_role("button", name=text, exact=True)
        for i in range(min(loc.count(), 12)):
            el = loc.nth(i)
            try:
                if el.is_visible() and el.is_enabled():
                    results.append(el)
            except Exception:
                continue
    except Exception:
        pass
    if results:
        return results

    # Fallback si la page emploie un aria-label ou une structure accessible
    # non standard : comparaison stricte, sans texte partiel.
    try:
        loc = page.locator("button, [role='button']")
        for i in range(min(loc.count(), 160)):
            el = loc.nth(i)
            try:
                labels = (el.inner_text(timeout=500), el.get_attribute('aria-label'),
                          el.get_attribute('title'))
                if (el.is_visible() and el.is_enabled() and
                        any(normalize(v) == normalize(text) for v in labels if v)):
                    results.append(el)
            except Exception:
                continue
    except Exception:
        pass
    return results


def _button(page, text):
    """Premier contrôle exact disponible, pour les onglets et les questions."""
    choices = _buttons(page, text)
    return choices[0] if choices else None


def _question_buttons(page):
    """Lit les boutons 1..N et leur état visuel réel, sans en déduire une note."""
    questions = []
    seen = set()
    try:
        loc = page.locator("button")
        for i in range(min(loc.count(), 200)):
            el = loc.nth(i)
            try:
                if not el.is_visible():
                    continue
                label = (el.inner_text(timeout=650) or "").strip()
                if not re.fullmatch(r"[1-9][0-9]?", label):
                    continue
                number = int(label)
                if number in seen:
                    continue
                css = el.get_attribute("class") or ""
                if re.search(r"(?:^|\s)(?:bg|text|border)-error-", css):
                    state = "incorrect"
                elif re.search(r"(?:^|\s)(?:bg|text|border)-success-", css):
                    state = "correct"
                else:
                    state = "unknown"
                questions.append({"number": number, "indicator": state})
                seen.add(number)
            except Exception:
                continue
    except Exception:
        pass
    return sorted(questions, key=lambda q: q["number"])


def result_overview(page):
    if not is_result(page):
        return {"ok": False, "reason": "not_a_result_screen", "route": route_without_secrets(page.url)}
    text = _body_text(page)
    match = re.search(r"votre\s+score\s*[:\s]*(\d+)\s*/\s*(\d+)", normalize(text), re.I)
    score = {"earned": int(match[1]), "total": int(match[2])} if match else None
    return {
        "ok": True,
        "route": route_without_secrets(page.url),
        "score": score,
        "questions": _question_buttons(page),
        "tabs": [tab for tab in TABS if _button(page, tab) is not None],
    }


def _panel_snapshot(page):
    """Collecte la vue active et les marqueurs DOM, sans données de session."""
    body = _body_text(page)
    headings = []
    try:
        loc = page.locator("h1,h2,h3")
        for i in range(min(loc.count(), 30)):
            el = loc.nth(i)
            if el.is_visible():
                headings.append(redact_text((el.inner_text(timeout=650) or "")[:300]))
    except Exception:
        pass
    zones = []
    try:
        loc = page.locator("[data-name='user-answer-container'],.ordering-drop-zone")
        seen = set()
        for i in range(min(loc.count(), 20)):
            el = loc.nth(i)
            if not el.is_visible():
                continue
            content = redact_text((el.inner_text(timeout=800) or "")[:5000])
            if content and content not in seen:
                zones.append(content)
                seen.add(content)
    except Exception:
        pass
    choices = []
    try:
        loc = page.locator("[data-state='correct'],[data-correct='true'],[class~='correct'],[class*='correct-answer']")
        seen = set()
        for i in range(min(loc.count(), 90)):
            el = loc.nth(i)
            if not el.is_visible():
                continue
            content = redact_text((el.inner_text(timeout=800) or "")[:600])
            if content and content not in seen:
                choices.append(content)
                seen.add(content)
    except Exception:
        pass
    return {
        "route": route_without_secrets(page.url),
        "text": body,
        "headings": headings,
        "answer_zones": zones,
        "explicit_correct_markers": choices[:30],
    }


def _archive(directory):
    out = Path(str(directory) + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(directory.iterdir()):
            if f.is_file():
                z.write(f, f.name)
    return out


class ResultReviewStore:
    """Table séparée de learned_answers : une observation n'est pas une solution sûre."""

    def __init__(self, database):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS result_reviews (
                activity_route TEXT NOT NULL,
                question_number INTEGER NOT NULL,
                indicator TEXT NOT NULL,
                your_answers_text TEXT,
                correction_text TEXT,
                explanation_text TEXT,
                snapshot_json TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                PRIMARY KEY (activity_route, question_number)
            )""")

    def save_review(self, overview, entries):
        """Sauvegarde chaque question lue, sans écraser learned_answers."""
        count = 0
        with sqlite3.connect(self.database) as con:
            for item in entries:
                if not item.get("tabs"):
                    continue
                tabs = item["tabs"]
                con.execute("""INSERT INTO result_reviews (
                   activity_route, question_number, indicator,
                   your_answers_text, correction_text, explanation_text,
                   snapshot_json, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_route, question_number) DO UPDATE SET
                  indicator=excluded.indicator,
                  your_answers_text=excluded.your_answers_text,
                  correction_text=excluded.correction_text,
                  explanation_text=excluded.explanation_text,
                  snapshot_json=excluded.snapshot_json,
                  captured_at=excluded.captured_at""", (
                    overview["route"], item["number"], item["indicator"],
                    (tabs.get("Vos réponses") or {}).get("text"),
                    (tabs.get("Correction") or {}).get("text"),
                    (tabs.get("Explication") or {}).get("text"),
                    json.dumps(item, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ))
                count += 1
        return count

    def count(self):
        with sqlite3.connect(self.database) as con:
            return con.execute("SELECT COUNT(*) FROM result_reviews").fetchone()[0]


def _selected_question_number(page):
    """Identifie la question active via son fond (les autres ont un contour).

    D'après les captures, la question active utilise bg-error-800 alors que
    les autres affichent border-error-400 ; ne jamais inférer via le score.
    """
    try:
        loc = page.locator("button")
        for i in range(min(loc.count(), 200)):
            el = loc.nth(i)
            if not el.is_visible():
                continue
            label = (el.inner_text(timeout=650) or "").strip()
            if not re.fullmatch(r"[1-9][0-9]?", label):
                continue
            classes = el.get_attribute("class") or ""
            if re.search(r"(?:^|\s)bg-(?:error|success|primary)-[0-9]+(?:\s|$)", classes):
                return int(label)
    except Exception:
        pass
    return None


def capture_result_review(page, destination, *, db_path=None, max_questions=30):
    """Parcourt les onglets des questions d'un résultat déjà atteint.

    N'ouvre pas Rejouer, ne clique ni Suivant ni Valider, ne soumet rien.
    Si les boutons font quitter le résultat, arrête pour ne pas naviguer à
    l'aveugle. Chaque entrée conserve la preuve de ce qui a été lu.
    """
    overview = result_overview(page)
    if not overview["ok"]:
        return {"ok": False, "reason": overview["reason"]}

    directory, _ = capture_page(page, "resultat_avant_revision", destination)
    entries = []
    for question in overview["questions"][:max_questions]:
        if not is_result(page):
            break
        number = question["number"]
        item = {**question, "tabs": {}, "errors": []}
        # La question actuellement affichée n'exige aucun clic. Cela évite
        # le faux échec de la Q1 vu sur la nouvelle interface (fond bg-error).
        if _selected_question_number(page) != number:
            selector = _button(page, str(number))
            if selector is None or not safe_click(selector):
                item["errors"].append("question_button_not_clickable")
                entries.append(item)
                continue
            page.wait_for_timeout(400)
        for tab_name in TABS:
            if not is_result(page):
                item["errors"].append("left_result_screen")
                break
            tab = _button(page, tab_name)
            if tab is None:
                item["errors"].append(f"missing_tab:{tab_name}")
                continue
            if not safe_click(tab):
                item["errors"].append(f"tab_click_failed:{tab_name}")
                continue
            page.wait_for_timeout(350)
            item["tabs"][tab_name] = _panel_snapshot(page)
        entries.append(item)
    review = {
        "schema": "globalexam_result_review_v1",
        "source": "result_tabs_only",
        "note": "Observations de corrections, non assimilées à des réponses apprises.",
        "overview": overview,
        "questions": entries,
        "questions_requested": len(overview["questions"]),
        "questions_inspected": sum(bool(x["tabs"]) for x in entries),
    }
    (directory / "result_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [f"Route: {overview['route']}", f"Score: {overview['score']}",
               f"Questions: {len(overview['questions'])}",
               f"Avec relevé: {review['questions_inspected']}",
               "Pas de soumission ; pas d'ajout à learned_answers."]
    summary.extend(f"Question {x['number']}: {x['indicator']} | onglets: {', '.join(x['tabs'])} | erreurs: {', '.join(x['errors']) or 'aucune'}" for x in entries)
    (directory / "review_resume.txt").write_text("\n".join(summary), encoding="utf-8")
    review["database_saved"] = 0
    review["database_error"] = None
    if db_path is not None:
        try:
            store = ResultReviewStore(db_path)
            review["database_saved"] = store.save_review(overview, entries)
        except Exception as exc:
            review["database_error"] = type(exc).__name__ + ": " + str(exc)[:200]
    review["directory"] = directory
    review["archive"] = _archive(directory)
    return {"ok": True, **review}


def _replay_target(page, context, prior_pages):
    """Vraie page activité nouvelle, jamais un ancien onglet préexistant."""
    try:
        candidates = list(context.pages)
    except Exception:
        candidates = [page]
    for candidate in candidates:
        try:
            if candidate.is_closed():
                continue
            if candidate is not page and id(candidate) in prior_pages:
                continue
            if not is_globalexam_host(candidate.url):
                continue
            if EXERCISE_PATH.fullmatch(urlsplit(candidate.url).path):
                return candidate
        except Exception:
            continue
    return None


def _visible_replay_state(page):
    """Empreinte légère pour ne pas retenter un clic si un dialogue s'ouvre."""
    try:
        return (_body_text(page) or "")[:3000]
    except Exception:
        return ""


def replay_capture(page, context, destination, *, wait_ms=7000):
    """Rejoue sur demande seulement ; contrôle l'issue du clic.

    En présence de doublons, essaie le suivant uniquement si le premier
    n'a produit *aucune* ouverture ni modification visible. Les clics ne sont
    jamais forcés. En cas d'échec, la trace est exportée systématiquement.
    """
    before = route_without_secrets(page.url)
    if not is_result(page):
        return {"ok": False, "clicked": False, "reason": "not_a_result_screen"}

    controls = _buttons(page, "Rejouer l'activité")
    before_state = _visible_replay_state(page)
    prior_pages = {id(x) for x in context.pages}
    attempts = []
    clicked = False
    found = False
    target = page
    action_reason = None

    for index, control in enumerate(controls, 1):
        if not is_result(page):
            break
        try:
            success = safe_click(control, timeout=1500)
        except Exception as exc:
            success = False
            attempts.append({"candidate": index, "clicked": False,
                             "error": type(exc).__name__})
        else:
            attempts.append({"candidate": index, "clicked": success})
        if not success:
            continue
        clicked = True

        # Chaque clic a sa fenêtre d'attente pour ne pas rater une SPA lente.
        # Le dernier contrôle bénéficie de la fenêtre maximale demandée.
        delay_ms = min(wait_ms, 2200) if index < len(controls) else wait_ms
        for _ in range(max(1, delay_ms // 200)):
            reached = _replay_target(page, context, prior_pages)
            if reached is not None:
                target = reached
                found = True
                break
            page.wait_for_timeout(200)
        if found:
            break

        if not is_result(page):
            action_reason = "route_changed_but_exercise_not_confirmed"
            break

        try:
            new_pages = [item for item in context.pages
                         if id(item) not in prior_pages and not item.is_closed()]
        except Exception:
            new_pages = []
        if new_pages:
            # Ne pas cliquer un deuxième bouton lorsqu'un premier clic
            # a déjà ouvert un onglet encore en chargement.
            action_reason = "new_tab_opened_but_exercise_not_yet_confirmed"
            break

        if _visible_replay_state(page) != before_state:
            # Un dialogue de confirmation peut être apparu : ne pas cliquer
            # d'autres boutons et ne pas accepter la confirmation à l'aveugle.
            action_reason = "result_screen_changed_after_click"
            break

        attempts[-1]["result"] = "no_navigation_or_visible_change"
        # Première copie de Rejouer sans effet : essayer la suivante.

    if not found and clicked:
        # Un délai de transition tardif peut encore mener à l'exercice.
        for _ in range(8):
            reached = _replay_target(page, context, prior_pages)
            if reached is not None:
                target = reached
                found = True
                break
            page.wait_for_timeout(200)

    if not found:
        try:
            new_pages = [candidate for candidate in context.pages
                         if id(candidate) not in prior_pages and not candidate.is_closed()]
            if new_pages:
                target = new_pages[-1]
        except Exception:
            pass

    if not clicked:
        reason = "replay_button_missing" if not controls else "replay_button_click_failed"
    elif found:
        reason = None
    else:
        reason = action_reason or "exercise_opening_not_confirmed"

    label = "apres_rejouer" if clicked else "rejouer_echec_clic"
    directory, report = capture_page(target, label, destination)
    trace = {
        "schema": "globalexam_replay_trace_v2",
        "clicked": clicked,
        "ok": found,
        "reason": reason,
        "before_route": before,
        "after_route": route_without_secrets(target.url),
        "candidate_count": len(controls),
        "click_attempts": attempts,
        "new_tab": target is not page,
        "screen_kind": (report.get("detected") or {}).get("kind"),
    }
    (directory / "replay_trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**trace, "page": target, "directory": directory,
            "archive": _archive(directory)}
