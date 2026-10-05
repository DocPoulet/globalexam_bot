import unicodedata


FORBIDDEN_ARIA_LABELS = {
    "ouvrir le formulaire de retour",
}

FORBIDDEN_TEXT_FRAGMENTS = (
    "formulaire de retour",
    "feedback",
)


def normalize(text):
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def is_forbidden_element(element):
    """
    True si cet élément ne doit jamais être cliqué par le bot.
    """
    try:
        aria = normalize(element.get_attribute("aria-label") or "")
    except Exception:
        aria = ""

    if aria in {normalize(x) for x in FORBIDDEN_ARIA_LABELS}:
        return True

    try:
        title = normalize(element.get_attribute("title") or "")
    except Exception:
        title = ""

    try:
        text = normalize(element.inner_text() or "")
    except Exception:
        text = ""

    joined = f"{aria} {title} {text}"

    return any(
        normalize(fragment) in joined
        for fragment in FORBIDDEN_TEXT_FRAGMENTS
    )


def safe_click(element, force=False, timeout=3000):
    """
    Point de passage commun pour tous les clics programmatiques.

    Tous les clics sont bornés : aucun Locator.click() ne doit pouvoir
    bloquer silencieusement pendant ~30 secondes.
    """
    if is_forbidden_element(element):
        return False

    try:
        element.click(force=force, timeout=timeout)
        return True
    except Exception:
        return False
