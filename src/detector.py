import re


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _dom_snapshot(page):
    """
    Extrait une photographie structurée du DOM visible.
    Cela évite de dépendre uniquement de quelques sélecteurs supposés.
    """

    return page.evaluate(
        """
        () => {
            const visible = (el) => {
                const style = window.getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                return (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    Number(style.opacity || 1) !== 0 &&
                    rect.width > 0 &&
                    rect.height > 0
                );
            };

            const textOf = (el) =>
                (el.innerText || el.textContent || '')
                    .replace(/\\s+/g, ' ')
                    .trim();

            const nodes = [];

            for (const el of document.querySelectorAll('body *')) {
                if (!visible(el)) continue;

                const tag = el.tagName.toLowerCase();
                const text = textOf(el);

                if (!text && !['input', 'select', 'textarea', 'button'].includes(tag)) {
                    continue;
                }

                nodes.push({
                    tag,
                    text: text.slice(0, 1500),
                    id: el.id || '',
                    className: typeof el.className === 'string' ? el.className : '',
                    role: el.getAttribute('role') || '',
                    type: el.getAttribute('type') || '',
                    name: el.getAttribute('name') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    dataTestId: el.getAttribute('data-testid') || ''
                });

                if (nodes.length >= 2000) break;
            }

            return nodes;
        }
        """
    )


def _score_question(node):
    text = clean_text(node.get("text"))

    if len(text) < 8 or len(text) > 1200:
        return -999

    blob = " ".join([
        node.get("id", ""),
        node.get("className", ""),
        node.get("role", ""),
        node.get("dataTestId", ""),
        node.get("ariaLabel", ""),
    ]).lower()

    score = 0

    if node.get("tag") in ("h1", "h2", "h3", "legend"):
        score += 30

    if "question" in blob:
        score += 55

    if "prompt" in blob or "instruction" in blob:
        score += 35

    if "exercise" in blob or "exercice" in blob:
        score += 20

    if "?" in text:
        score += 20

    if 15 <= len(text) <= 400:
        score += 15

    return score


def _candidate_answers(nodes):
    answers = []
    seen = set()

    for node in nodes:
        text = clean_text(node.get("text"))
        blob = " ".join([
            node.get("className", ""),
            node.get("id", ""),
            node.get("role", ""),
            node.get("dataTestId", ""),
        ]).lower()

        tag = node.get("tag")
        input_type = node.get("type")

        likely = False

        if input_type in ("radio", "checkbox"):
            likely = True

        if node.get("role") in ("option", "radio", "checkbox"):
            likely = True

        if "answer" in blob or "option" in blob or "choice" in blob:
            likely = True

        if tag == "label" and text:
            likely = True

        if likely and text and len(text) <= 500 and text not in seen:
            seen.add(text)
            answers.append(text)

    return answers[:100]


def _buttons(nodes):
    values = []
    seen = set()

    for node in nodes:
        if node.get("tag") != "button" and node.get("role") != "button":
            continue

        text = clean_text(node.get("text") or node.get("ariaLabel"))

        if text and text not in seen:
            seen.add(text)
            values.append(text)

    return values[:100]


def _inputs(nodes):
    results = []

    for node in nodes:
        if node.get("tag") not in ("input", "textarea", "select"):
            continue

        results.append({
            "tag": node.get("tag"),
            "type": node.get("type"),
            "name": node.get("name"),
            "placeholder": node.get("placeholder"),
            "aria_label": node.get("ariaLabel"),
        })

    return results[:100]


def _exercise_type(nodes, answers):
    types = [node.get("type") for node in nodes if node.get("tag") == "input"]

    if "radio" in types:
        return "qcm_single"

    if "checkbox" in types:
        return "qcm_multiple"

    if any(node.get("tag") == "select" for node in nodes):
        return "select"

    if any(
        node.get("tag") == "textarea" or node.get("type") in ("text", "")
        for node in nodes
        if node.get("tag") in ("input", "textarea")
    ):
        return "text_input"

    if answers:
        return "choice_or_custom"

    return "unknown"


def analyze_page(page):
    nodes = _dom_snapshot(page)

    question_candidates = []

    for node in nodes:
        score = _score_question(node)

        if score > 0:
            question_candidates.append((score, clean_text(node.get("text"))))

    question_candidates.sort(key=lambda x: x[0], reverse=True)

    question = question_candidates[0][1] if question_candidates else None

    answers = _candidate_answers(nodes)
    buttons = _buttons(nodes)
    inputs = _inputs(nodes)

    url = page.url
    login_required = (
        "auth.global-exam.com" in url.lower()
        or any(item.get("type") == "password" for item in inputs)
    )

    return {
        "url": url,
        "title": page.title(),
        "login_required": login_required,
        "exercise_type": _exercise_type(nodes, answers),
        "question": question,
        "question_candidates": [
            {"score": score, "text": text}
            for score, text in question_candidates[:30]
        ],
        "answers": answers,
        "buttons": buttons,
        "inputs": inputs,
        "dom_nodes": nodes,
    }
