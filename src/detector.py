import re


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _frame_snapshot(frame):
    """Extrait les contrôles et textes importants d'un frame accessible."""
    try:
        nodes = frame.evaluate(
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

                const result = [];
                const selector = [
                    'h1','h2','h3','h4','p','legend','label','button',
                    'input','textarea','select',
                    '[role="button"]','[role="option"]','[role="radio"]',
                    '[role="checkbox"]','[role="group"]','[role="radiogroup"]',
                    '[data-testid]','[aria-label]'
                ].join(',');

                for (const el of document.querySelectorAll(selector)) {
                    if (!visible(el)) continue;

                    const tag = el.tagName.toLowerCase();
                    const text = textOf(el);

                    if (!text && !['input','textarea','select','button'].includes(tag)) {
                        continue;
                    }

                    result.push({
                        tag,
                        text: text.slice(0, 2000),
                        id: el.id || '',
                        className: typeof el.className === 'string' ? el.className : '',
                        role: el.getAttribute('role') || '',
                        type: el.getAttribute('type') || '',
                        name: el.getAttribute('name') || '',
                        value: el.getAttribute('value') || '',
                        placeholder: el.getAttribute('placeholder') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        dataTestId: el.getAttribute('data-testid') || '',
                        forId: el.getAttribute('for') || ''
                    });

                    if (result.length >= 2500) break;
                }

                return result;
            }
            """
        )
    except Exception:
        return []

    frame_url = getattr(frame, "url", "") or ""
    for node in nodes:
        node["frame_url"] = frame_url

    return nodes


def _dom_snapshot(page):
    """Analyse le document principal ET les iframes accessibles."""
    nodes = []
    for frame in page.frames:
        nodes.extend(_frame_snapshot(frame))
    return nodes[:5000]


def _metadata_blob(node):
    return " ".join(
        [
            node.get("id", ""),
            node.get("className", ""),
            node.get("role", ""),
            node.get("dataTestId", ""),
            node.get("ariaLabel", ""),
            node.get("name", ""),
        ]
    ).lower()


def _score_question(node):
    text = clean_text(node.get("text"))
    if len(text) < 5 or len(text) > 1600:
        return -999

    blob = _metadata_blob(node)
    score = 0

    if node.get("tag") in ("h1", "h2", "h3", "h4", "legend"):
        score += 30

    for word, bonus in (
        ("question", 70),
        ("prompt", 50),
        ("instruction", 35),
        ("exercise", 25),
        ("exercice", 25),
        ("statement", 25),
    ):
        if word in blob:
            score += bonus

    if "?" in text:
        score += 25

    if 10 <= len(text) <= 450:
        score += 15

    if text.lower() in {"suivant", "next", "valider", "validate", "continuer"}:
        score -= 100

    return score


def _candidate_answers(nodes):
    answers = []
    seen = set()

    labels_by_for = {
        node.get("forId"): clean_text(node.get("text"))
        for node in nodes
        if node.get("tag") == "label" and node.get("forId")
    }

    for node in nodes:
        text = clean_text(node.get("text"))
        blob = _metadata_blob(node)
        tag = node.get("tag")
        input_type = (node.get("type") or "").lower()
        role = (node.get("role") or "").lower()

        if tag == "input" and input_type in ("radio", "checkbox"):
            text = (
                labels_by_for.get(node.get("id"))
                or text
                or clean_text(node.get("ariaLabel"))
                or clean_text(node.get("value"))
            )

        likely = (
            input_type in ("radio", "checkbox")
            or role in ("option", "radio", "checkbox")
            or "answer" in blob
            or "option" in blob
            or "choice" in blob
            or "response" in blob
        )

        if tag == "label" and text:
            likely = likely or any(
                token in blob
                for token in ("answer", "option", "choice", "radio", "checkbox")
            )

        if not likely or not text or len(text) > 700:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        answers.append(
            {
                "text": text,
                "kind": input_type or role or tag,
                "frame_url": node.get("frame_url", ""),
            }
        )

    return answers[:100]


def _buttons(nodes):
    buttons = []
    seen = set()

    for node in nodes:
        if node.get("tag") != "button" and node.get("role") != "button":
            continue

        text = clean_text(node.get("text") or node.get("ariaLabel"))
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        buttons.append(
            {
                "text": text,
                "frame_url": node.get("frame_url", ""),
            }
        )

    return buttons[:100]


def _inputs(nodes):
    results = []

    for node in nodes:
        if node.get("tag") not in ("input", "textarea", "select"):
            continue

        results.append(
            {
                "tag": node.get("tag"),
                "type": node.get("type"),
                "name": node.get("name"),
                "placeholder": node.get("placeholder"),
                "aria_label": node.get("ariaLabel"),
                "frame_url": node.get("frame_url", ""),
            }
        )

    return results[:150]


def _exercise_type(nodes, answers):
    types = [
        (node.get("type") or "").lower()
        for node in nodes
        if node.get("tag") == "input"
    ]

    if "radio" in types:
        return "qcm_single"

    if "checkbox" in types:
        return "qcm_multiple"

    if any(node.get("tag") == "select" for node in nodes):
        return "select"

    if any(
        node.get("tag") == "textarea"
        or (node.get("tag") == "input" and node.get("type") in ("text", ""))
        for node in nodes
    ):
        return "text_input"

    if answers:
        return "choice_or_custom"

    return "unknown"


def analyze_page(page):
    nodes = _dom_snapshot(page)

    candidates = []
    for node in nodes:
        score = _score_question(node)
        if score > 0:
            candidates.append(
                (
                    score,
                    clean_text(node.get("text")),
                    node.get("frame_url", ""),
                )
            )

    candidates.sort(key=lambda item: item[0], reverse=True)

    answers = _candidate_answers(nodes)
    buttons = _buttons(nodes)
    inputs = _inputs(nodes)

    return {
        "url": page.url,
        "title": page.title(),
        "login_required": (
            "auth.global-exam.com" in page.url.lower()
            or any((item.get("type") or "").lower() == "password" for item in inputs)
        ),
        "frame_count": len(page.frames),
        "exercise_type": _exercise_type(nodes, answers),
        "question": candidates[0][1] if candidates else None,
        "question_frame": candidates[0][2] if candidates else None,
        "question_candidates": [
            {"score": score, "text": text, "frame_url": frame_url}
            for score, text, frame_url in candidates[:30]
        ],
        "answers": answers,
        "buttons": buttons,
        "inputs": inputs,
        "dom_nodes": nodes,
    }
