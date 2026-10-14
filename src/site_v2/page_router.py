"""Sélection des onglets de la nouvelle interface par URL réelle.

Aucun clic, aucune ouverture de session et aucune lecture de cookies.
Les URL imprimées ne comportent ni query-string ni fragment.
"""
import re
from urllib.parse import urlsplit

from .detector import is_globalexam_host, route_without_secrets


_RESULT = re.compile(r"^/activity/[^/]+/result/?$", re.I)
_CONTENT = re.compile(r"^/activity/[^/]+/content/[^/]+/?$", re.I)
_CORRECTION = re.compile(r"^/activity/[^/]+/content/[^/]+/correction/?$", re.I)


def kind_from_url(url):
    """Type d'écran selon l'URL, sans dépendre du contenu HTML."""
    if not is_globalexam_host(url):
        return "external"
    path = urlsplit(url).path
    if _RESULT.fullmatch(path):
        return "result"
    if _CORRECTION.fullmatch(path):
        return "correction"
    if _CONTENT.fullmatch(path):
        return "exercise"
    if path.rstrip("/") in ("/levels", "/levels/content"):
        return "catalog"
    if urlsplit(url).hostname == "auth.global-exam.com" or path.startswith('/login'):
        return "login"
    if path in ("", "/"):
        return "home"
    return "unknown"


def _available_pages(context):
    try:
        pages = list(context.pages)
    except Exception:
        return []
    result = []
    for candidate in pages:
        try:
            if not candidate.is_closed():
                result.append(candidate)
        except Exception:
            continue
    return result


def _focused(candidate):
    """Indice facultatif. Le terminal peut temporairement prendre le focus."""
    try:
        return bool(candidate.evaluate("() => document.hasFocus()"))
    except Exception:
        return False


def tab_inventory(context, selected=None):
    """Tableau de diagnostic des onglets suivis par Playwright."""
    output = []
    for idx, candidate in enumerate(_available_pages(context), 1):
        try:
            url = candidate.url
            output.append({
                "index": idx,
                "page": candidate,
                "route": route_without_secrets(url),
                "kind": kind_from_url(url),
                "selected": candidate is selected,
                "focused": _focused(candidate),
            })
        except Exception:
            continue
    return output


def page_for_kind(current_page, context, kind):
    """Trouve une page par URL; privilégie la sélection courante si correcte.

    En présence de plusieurs résultats, préfère un onglet ayant le focus,
    sinon le plus récent. On ne fait pas confiance aux anciennes captures DOM.
    """
    inventory = tab_inventory(context, current_page)
    matches = [item for item in inventory if item["kind"] == kind]
    if not matches:
        return None
    focused = [item for item in matches if item["focused"]]
    if focused:
        return focused[-1]["page"]
    if current_page is not None and any(item["page"] is current_page for item in matches):
        return current_page
    return matches[-1]["page"]


def initial_page(context):
    """Préserve un résultat/exercice déjà ouvert au démarrage du programme.

    Ne redirige pas l'utilisateur vers le parcours si l'URL d'un onglet
    existant suffit déjà à déterminer l'écran.
    """
    inventory = tab_inventory(context)
    focused = [item for item in inventory if item["focused"] and item["kind"] in
               ("result", "exercise", "correction", "catalog")]
    if focused:
        return focused[-1]["page"]
    for wanted in ("result", "exercise", "correction", "catalog"):
        matches = [x for x in inventory if x["kind"] == wanted]
        if matches:
            return matches[-1]["page"]
    return inventory[0]["page"] if inventory else context.new_page()


def needs_initial_navigation(page):
    """Visiter le parcours seulement si aucune page utile n'est déjà ouverte."""
    return kind_from_url(page.url) not in ("result", "exercise", "correction", "catalog")
