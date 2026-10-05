def first_visible_text(page, selectors):
    for selector in selectors:
        locator = page.locator(selector)

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue

                text = el.inner_text().strip()
            except Exception:
                continue

            if text:
                return text

    return None


def extract_question_text(page):
    """
    Cherche la consigne avec des sélecteurs d'abord spécifiques,
    puis des fallbacks plus généraux.
    """
    specific = (
        '[data-name="question"]',
        '[data-testid*="question"]',
        '[class*="question-title"]',
        '[class*="question"] h1',
        '[class*="question"] h2',
        '[class*="question"] h3',
        'main legend',
    )

    text = first_visible_text(page, specific)
    if text:
        return text

    generic = (
        "main h1",
        "main h2",
        "main h3",
        "[role='main'] h1",
        "[role='main'] h2",
        "[role='main'] h3",
        "legend",
    )

    return first_visible_text(page, generic)
