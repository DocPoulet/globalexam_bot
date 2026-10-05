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
    locator = page.locator("button")

    for i in range(locator.count()):
        button = locator.nth(i)

        try:
            if not button.is_visible():
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
    for action in find_actions(page):
        if action["kind"] != kind or action["disabled"]:
            continue

        page.locator("button").nth(action["index"]).click()
        page.wait_for_timeout(350)
        return True

    return False
