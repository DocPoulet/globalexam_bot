import re


ACTION_KEYWORDS = {
    "validate": [
        "valider", "validate", "submit",
        "confirmer", "check",
        "vérifier", "verifier"
    ],
    "next": [
        "suivant", "next", "continuer",
        "continue"
    ],
    "previous": [
        "précédent", "precedent",
        "previous", "back", "retour"
    ],
}


def _clean(text):
    if text is None:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _visible_text(locator):
    results = []

    for i in range(min(locator.count(), 100)):
        item = locator.nth(i)

        try:
            if not item.is_visible():
                continue

            text = _clean(item.inner_text())

            if text:
                results.append({
                    "index": i,
                    "text": text,
                })
        except Exception:
            continue

    return results


def _detect_question(page):
    selectors = [
        "[class*='question']",
        "[class*='Question']",
        "[class*='prompt']",
        "[class*='instruction']",
        "[data-testid*='question']",
        "[aria-label*='question' i]",
        "legend",
        "h1",
        "h2",
        "h3",
    ]

    candidates = []

    for priority, selector in enumerate(
        selectors
    ):
        locator = page.locator(selector)

        for item in _visible_text(locator):
            text = item["text"]

            if len(text) < 5:
                continue

            score = 100 - priority * 8

            if "?" in text:
                score += 20

            if 10 <= len(text) <= 500:
                score += 10

            if len(text) > 1000:
                score -= 30

            candidates.append(
                (score, text, selector)
            )

    if not candidates:
        return None, 0.0, None

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    score, text, selector = candidates[0]

    confidence = min(
        max(score / 130, 0),
        1
    )

    return text, confidence, selector


def _detect_answers(page):
    answers = []
    seen = set()

    labels = page.locator("label")

    for i in range(min(labels.count(), 100)):
        label = labels.nth(i)

        try:
            if not label.is_visible():
                continue

            text = _clean(label.inner_text())

            if not text or text in seen:
                continue

            nested_choice = label.locator(
                "input[type='radio'], "
                "input[type='checkbox']"
            )

            if nested_choice.count() > 0:
                input_type = (
                    nested_choice.first.get_attribute(
                        "type"
                    )
                    or "choice"
                )

                answers.append({
                    "text": text,
                    "kind": input_type,
                    "selector_hint": "label",
                    "label_index": i,
                })

                seen.add(text)

        except Exception:
            continue

    choices = page.locator(
        "input[type='radio'], "
        "input[type='checkbox']"
    )

    for i in range(min(choices.count(), 100)):
        choice = choices.nth(i)

        try:
            if not choice.is_visible():
                continue

            input_type = (
                choice.get_attribute("type")
                or "choice"
            )

            element_id = choice.get_attribute(
                "id"
            )

            text = ""

            if element_id:
                matching_label = page.locator(
                    f"label[for='{element_id}']"
                )

                if matching_label.count() > 0:
                    text = _clean(
                        matching_label.first.inner_text()
                    )

            if not text:
                text = _clean(
                    choice.get_attribute("value")
                )

            if text and text not in seen:
                answers.append({
                    "text": text,
                    "kind": input_type,
                    "selector_hint":
                        f"input[type='{input_type}']",
                    "input_index": i,
                })

                seen.add(text)

        except Exception:
            continue

    buttons = page.locator(
        "[class*='answer'] button, "
        "[class*='option'] button, "
        "[role='option']"
    )

    for i, item in enumerate(
        _visible_text(buttons)
    ):
        text = item["text"]

        if text not in seen:
            answers.append({
                "text": text,
                "kind": "button",
                "selector_hint":
                    "answer/option button",
                "button_index": i,
            })

            seen.add(text)

    return answers


def _detect_actions(page):
    actions = []
    seen = set()

    buttons = page.locator(
        "button, [role='button'], "
        "input[type='submit']"
    )

    for i in range(min(buttons.count(), 100)):
        button = buttons.nth(i)

        try:
            if not button.is_visible():
                continue

            tag_name = button.evaluate(
                "(e) => e.tagName"
            )

            if tag_name == "INPUT":
                text = _clean(
                    button.get_attribute("value")
                )
            else:
                text = _clean(
                    button.inner_text()
                )

            if not text or text in seen:
                continue

            lower = text.lower()
            kind = "other"

            for action_kind, words in (
                ACTION_KEYWORDS.items()
            ):
                if any(
                    word in lower
                    for word in words
                ):
                    kind = action_kind
                    break

            if kind != "other":
                actions.append({
                    "text": text,
                    "kind": kind,
                    "button_index": i,
                })

                seen.add(text)

        except Exception:
            continue

    return actions


def _detect_feedback(page):
    selectors = [
        "[class*='correct']",
        "[class*='incorrect']",
        "[class*='feedback']",
        "[class*='correction']",
        "[role='alert']",
    ]

    texts = []

    for selector in selectors:
        for item in _visible_text(
            page.locator(selector)
        ):
            text = item["text"]

            if text not in texts:
                texts.append(text)

    return texts[:10]


def _detect_type(page, answers):
    radios = page.locator(
        "input[type='radio']"
    ).count()

    checkboxes = page.locator(
        "input[type='checkbox']"
    ).count()

    textareas = page.locator(
        "textarea"
    ).count()

    text_inputs = page.locator(
        "input[type='text'], "
        "input:not([type])"
    ).count()

    if radios > 0:
        return "qcm_single"

    if checkboxes > 0:
        return "qcm_multiple"

    if textareas > 0 or text_inputs > 0:
        return "text_input"

    if answers:
        return "choice_buttons"

    return "unknown"


def detect_exercise(page):
    (
        question,
        question_confidence,
        question_selector
    ) = _detect_question(page)

    answers = _detect_answers(page)
    actions = _detect_actions(page)
    feedback = _detect_feedback(page)

    exercise_type = _detect_type(
        page,
        answers
    )

    answer_confidence = 0.0
    if answers:
        answer_confidence = min(
            0.4 + len(answers) * 0.12,
            1.0
        )

    action_confidence = 0.0
    if actions:
        action_confidence = min(
            0.5 + len(actions) * 0.15,
            1.0
        )

    return {
        "page_title": page.title(),
        "url": page.url,
        "type": exercise_type,
        "question": question,
        "question_selector_hint":
            question_selector,
        "answers": answers,
        "actions": actions,
        "feedback": feedback,
        "confidence": {
            "question":
                question_confidence,
            "answers":
                answer_confidence,
            "actions":
                action_confidence,
        },
        "raw_counts": {
            "buttons":
                page.locator(
                    "button"
                ).count(),
            "inputs":
                page.locator(
                    "input"
                ).count(),
            "radio_inputs":
                page.locator(
                    "input[type='radio']"
                ).count(),
            "checkbox_inputs":
                page.locator(
                    "input[type='checkbox']"
                ).count(),
            "textareas":
                page.locator(
                    "textarea"
                ).count(),
        },
    }
