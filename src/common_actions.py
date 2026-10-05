ACTION_WORDS = {
    "skip": ("passer", "skip"),
    "validate": ("valider", "validate", "vérifier", "verifier", "confirmer"),
    "next": ("suivant", "next", "continuer", "continue"),
}


def find_actions(page):
    result = []
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
        except Exception:
            continue

        if not text:
            continue

        lowered = text.lower()

        for kind, words in ACTION_WORDS.items():
            if any(word in lowered for word in words):
                result.append({
                    "index": i,
                    "text": text,
                    "kind": kind,
                })
                break

    return result


def click_common_action(page, kind):
    actions = find_actions(page)

    for action in actions:
        if action["kind"] != kind:
            continue

        buttons = page.locator("button")
        buttons.nth(action["index"]).click()
        return True

    return False
