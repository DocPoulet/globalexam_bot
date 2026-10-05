from safety_clicks import is_forbidden_element, safe_click


ACTION_WORDS = {
    "skip": ("passer", "skip"),
    "validate": (
        "valider",
        "validate",
        "vérifier",
        "verifier",
        "confirmer",
        "terminer",
        "submit",
    ),
    "next": (
        "suivant",
        "next",
        "continuer",
        "continue",
    ),
}


def find_actions(page):
    actions = []
    locator = page.locator("button, [role='button']")

    for i in range(locator.count()):
        button = locator.nth(i)

        try:
            if not button.is_visible():
                continue

            if is_forbidden_element(button):
                continue

            text = (
                button.inner_text().strip()
                or (button.get_attribute("aria-label") or "").strip()
            )
            disabled = button.is_disabled()
        except Exception:
            continue

        if not text:
            continue

        lowered = text.lower()

        for kind, words in ACTION_WORDS.items():
            if any(word in lowered for word in words):
                actions.append({
                    "index": i,
                    "text": text,
                    "disabled": disabled,
                    "kind": kind,
                })
                break

    return actions


def click_common_action(page, kind):
    actions = find_actions(page)
    locator = page.locator("button, [role='button']")

    for action in actions:
        if action["kind"] != kind or action["disabled"]:
            continue

        target = locator.nth(action["index"])

        if not safe_click(target):
            continue

        page.wait_for_timeout(350)
        return True

    return False
