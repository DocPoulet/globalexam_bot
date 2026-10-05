def _safe_texts(locator, limit=50):
    """
    Récupère proprement le texte visible d'une collection Playwright.

    Entrées :
        locator : locator Playwright.
        limit   : nombre maximum d'éléments.

    Sortie :
        Liste de chaînes non vides.
    """
    results = []

    count = min(locator.count(), limit)

    for i in range(count):
        try:
            text = locator.nth(i).inner_text().strip()
            if text:
                results.append(text)
        except Exception:
            pass

    return results


def analyze_page(page):
    """
    Analyse la structure générale de la page courante.

    Entrée :
        page : page Playwright ouverte.

    Sortie :
        Dictionnaire contenant les principaux éléments détectés.
    """

    headings = _safe_texts(
        page.locator("h1, h2, h3, [role='heading']")
    )

    buttons = _safe_texts(
        page.locator("button, [role='button']")
    )

    result = {
        "title": page.title(),
        "url": page.url,
        "headings": headings,
        "buttons": buttons,
        "inputs": list(range(page.locator("input").count())),
        "radios": list(range(page.locator("input[type='radio']").count())),
        "checkboxes": list(range(page.locator("input[type='checkbox']").count())),
    }

    return result
