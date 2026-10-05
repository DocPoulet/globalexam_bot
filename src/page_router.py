def classify_page(page):
    """
    Classe la page avant toute analyse métier.
    """
    url = page.url.lower().rstrip("/")

    if "auth.global-exam.com" in url:
        return "login"

    if "/activity/" in url and "/content/" in url:
        return "activity"

    if url == "https://general.global-exam.com":
        return "home"

    return "other"
