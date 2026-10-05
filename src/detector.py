import re


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def classify_page(page):
    """Classe la page avant toute tentative d'analyse d'exercice."""
    url = page.url.lower()

    if "auth.global-exam.com" in url:
        return "login"

    if "/activity/" in url and "/content/" in url:
        return "activity"

    if url.rstrip("/") == "https://general.global-exam.com":
        return "home"

    return "other"


def _visible(locator):
    items = []

    for i in range(locator.count()):
        el = locator.nth(i)

        try:
            if el.is_visible():
                items.append(el)
        except Exception:
            continue

    return items


def _question_text(page):
    """
    GlobalExam affiche la consigne principale de l'activité dans un h2
    sur les diagnostics observés.
    """
    for selector in (
        "main h2",
        "h2",
        "[class*='question']",
        "[data-testid*='question']",
        "legend",
    ):
        locator = page.locator(selector)

        for el in _visible(locator):
            try:
                text = clean_text(el.inner_text())
            except Exception:
                continue

            if len(text) >= 5:
                return text

    return None


def _draggable_answers(page):
    """
    Détecte les éléments de classement observés dans les diagnostics
    GlobalExam : button.draggable-item.
    """
    locator = page.locator("button.draggable-item")
    answers = []

    for i in range(locator.count()):
        el = locator.nth(i)

        try:
            if not el.is_visible():
                continue

            text = clean_text(el.inner_text())
        except Exception:
            continue

        if text:
            answers.append({
                "index": i,
                "text": text,
                "kind": "draggable",
                "selector": "button.draggable-item",
            })

    return answers


def _radio_answers(page):
    answers = []

    radios = page.locator("input[type='radio']")

    for i in range(radios.count()):
        radio = radios.nth(i)

        try:
            if not radio.is_visible():
                continue
        except Exception:
            continue

        element_id = radio.get_attribute("id")
        text = ""

        if element_id:
            label = page.locator(f"label[for='{element_id}']")
            if label.count():
                try:
                    text = clean_text(label.first.inner_text())
                except Exception:
                    pass

        if not text:
            text = clean_text(radio.get_attribute("value"))

        answers.append({
            "index": i,
            "text": text,
            "kind": "radio",
            "selector": "input[type='radio']",
        })

    return answers


def _checkbox_answers(page):
    answers = []

    checks = page.locator("input[type='checkbox']")

    for i in range(checks.count()):
        check = checks.nth(i)

        try:
            if not check.is_visible():
                continue
        except Exception:
            continue

        element_id = check.get_attribute("id")
        text = ""

        if element_id:
            label = page.locator(f"label[for='{element_id}']")
            if label.count():
                try:
                    text = clean_text(label.first.inner_text())
                except Exception:
                    pass

        answers.append({
            "index": i,
            "text": text,
            "kind": "checkbox",
            "selector": "input[type='checkbox']",
        })

    return answers


def _selects(page):
    result = []
    selects = page.locator("select")

    for i in range(selects.count()):
        select = selects.nth(i)

        try:
            if not select.is_visible():
                continue
        except Exception:
            continue

        options = []
        option_locator = select.locator("option")

        for j in range(option_locator.count()):
            option = option_locator.nth(j)
            options.append({
                "text": clean_text(option.inner_text()),
                "value": option.get_attribute("value"),
            })

        result.append({
            "index": i,
            "kind": "select",
            "options": options,
        })

    return result


def _text_fields(page):
    fields = []
    locator = page.locator(
        "textarea, input[type='text'], input:not([type])"
    )

    for i in range(locator.count()):
        el = locator.nth(i)

        try:
            if not el.is_visible():
                continue
        except Exception:
            continue

        fields.append({
            "index": i,
            "kind": "text",
            "placeholder": clean_text(el.get_attribute("placeholder")),
            "name": clean_text(el.get_attribute("name")),
        })

    return fields


def _action_buttons(page):
    actions = []
    seen = set()

    locator = page.locator("button")

    mappings = {
        "skip": ("passer", "skip"),
        "validate": ("valider", "validate", "vérifier", "verifier", "confirmer"),
        "next": ("suivant", "next", "continuer", "continue"),
        "previous": ("précédent", "precedent", "previous", "retour"),
    }

    for i in range(locator.count()):
        el = locator.nth(i)

        try:
            if not el.is_visible():
                continue

            text = clean_text(el.inner_text()) or clean_text(el.get_attribute("aria-label"))
        except Exception:
            continue

        if not text:
            continue

        lowered = text.lower()
        kind = None

        for action_kind, words in mappings.items():
            if any(word in lowered for word in words):
                kind = action_kind
                break

        if not kind:
            continue

        key = (kind, text.casefold())
        if key in seen:
            continue

        seen.add(key)
        actions.append({
            "index": i,
            "text": text,
            "kind": kind,
        })

    return actions


def analyze_activity(page):
    question = _question_text(page)

    draggable = _draggable_answers(page)
    radios = _radio_answers(page)
    checks = _checkbox_answers(page)
    selects = _selects(page)
    text_fields = _text_fields(page)

    if draggable:
        exercise_type = "ordering_dragdrop"
        answers = draggable
    elif radios:
        exercise_type = "qcm_single"
        answers = radios
    elif checks:
        exercise_type = "qcm_multiple"
        answers = checks
    elif selects:
        exercise_type = "select"
        answers = selects
    elif text_fields:
        exercise_type = "text_input"
        answers = text_fields
    else:
        exercise_type = "unknown"
        answers = []

    return {
        "page_kind": "activity",
        "url": page.url,
        "title": page.title(),
        "exercise_type": exercise_type,
        "question": question,
        "answers": answers,
        "actions": _action_buttons(page),
        "specific": {
            "draggable_count": len(draggable),
            "radio_count": len(radios),
            "checkbox_count": len(checks),
            "select_count": len(selects),
            "text_field_count": len(text_fields),
        },
    }


def analyze_page(page):
    page_kind = classify_page(page)

    if page_kind == "login":
        return {
            "page_kind": "login",
            "url": page.url,
            "title": page.title(),
            "exercise_type": None,
            "question": None,
            "answers": [],
            "actions": [],
        }

    if page_kind == "home":
        return {
            "page_kind": "home",
            "url": page.url,
            "title": page.title(),
            "exercise_type": None,
            "question": None,
            "answers": [],
            "actions": [],
        }

    if page_kind == "activity":
        return analyze_activity(page)

    return {
        "page_kind": page_kind,
        "url": page.url,
        "title": page.title(),
        "exercise_type": "unknown",
        "question": None,
        "answers": [],
        "actions": _action_buttons(page),
    }
