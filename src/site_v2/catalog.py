"""Navigation guidée du catalogue GlobalExam (interface octobre 2026).

Un module est un bouton ``MODULE N`` dont le panneau est le sibling direct
suivant. Les cartes ordinaires sont des ``div.relative.cursor-*`` avec un ``p``
contenant le titre. Cette implémentation refuse les éléments verrouillés,
les paliers, les tests et les conversations. Elle ne soumet aucune réponse.
"""
import re

from safety_clicks import normalize, safe_click
from .detector import is_globalexam_host, route_without_secrets


MODULE_RE = re.compile(r"^module\s+(\d+)\b")


def _globalexam_frame(page):
    """Trouve seulement le document de la plateforme, pas les frames tierces."""
    for frame in page.frames:
        if is_globalexam_host(frame.url) and frame == page.main_frame:
            return frame
    return next((f for f in page.frames if is_globalexam_host(f.url)), None)


def _module_button(page, number):
    """Localise le bouton exact du module choisi sans s'appuyer sur une classe CSS."""
    frame = _globalexam_frame(page)
    if frame is None:
        return None
    for button in frame.locator("button").all()[:300]:
        try:
            if not button.is_visible():
                continue
            match = MODULE_RE.match(normalize(button.inner_text()))
            if match and int(match.group(1)) == int(number):
                return button
        except Exception:
            continue
    return None


def module_list(page):
    """Liste des modules présents, même si aucun n'est actuellement déplié."""
    frame = _globalexam_frame(page)
    if frame is None:
        return []
    items = []
    for button in frame.locator("button").all()[:300]:
        try:
            if not button.is_visible():
                continue
            title = " ".join(button.inner_text().split())
            match = MODULE_RE.match(normalize(title))
            if match:
                items.append({
                    "number": int(match.group(1)),
                    "title": title[:200],
                    "expanded": button.get_attribute("aria-expanded") == "true",
                })
        except Exception:
            continue
    return items


def ensure_module_open(page, number):
    """Ouvre un module si besoin ; ne referme jamais un module déjà ouvert."""
    header = _module_button(page, number)
    if header is None:
        return False
    try:
        if header.get_attribute("aria-expanded") == "true":
            return True
        header.scroll_into_view_if_needed(timeout=3000)
        if not safe_click(header):
            return False
        page.wait_for_timeout(650)
        return header.get_attribute("aria-expanded") == "true"
    except Exception:
        return False


def _panel_for_module(page, number):
    """Un panneau doit être le frère immédiatement après l'en-tête MODULE N."""
    header = _module_button(page, number)
    if header is None:
        return None
    try:
        if header.get_attribute("aria-expanded") != "true":
            return None
        panel = header.locator("xpath=following-sibling::*[1]")
        if panel.count() != 1:
            return None
        # Le diagnostic montre `grid transition-all ... grid-rows-[1fr] visible`.
        # On exige cette enveloppe pour ne pas se tromper de module.
        classes = panel.get_attribute("class") or ""
        if "grid" not in classes or "grid-rows" not in classes:
            return None
        if not panel.is_visible():
            return None
        return panel
    except Exception:
        return None


def list_activities(page, module_number):
    """Lecture non intrusive des cartes du module ; aucune action navigateur."""
    panel = _panel_for_module(page, module_number)
    if panel is None:
        return {"ok": False, "reason": "module_ferme_ou_structure_inconnue",
                "module": int(module_number), "activities": []}

    cards = panel.locator("div.relative.cursor-pointer, div.relative.cursor-default")
    activities = []
    for dom_index in range(min(cards.count(), 100)):
        card = cards.nth(dom_index)
        try:
            if not card.is_visible():
                continue
            title_el = card.locator("p.text-pretty").first
            if title_el.count() == 0:
                continue  # pas une activité : exemple « Validation du module »
            title = " ".join(title_el.inner_text().split())
            if not title:
                continue
            full_text = " ".join(card.inner_text().split())[:1000]
            key = normalize(full_text)
            css = card.get_attribute("class") or ""
            clickable = "cursor-pointer" in css.split()
            if "a debloquer" in key or not clickable:
                state = "locked"
            elif "lancer" in key or "conversation ia" in key or "je releve le defi" in key:
                state = "special"
            elif "terminee" in key and "voir" in key:
                state = "completed"
            elif "en cours" in key and "continuer" in key:
                state = "in_progress"
            else:
                # Un nouveau type d'activité non documenté n'est jamais
                # présumé cliquable automatiquement.
                state = "unverified"
            activities.append({
                "index": len(activities) + 1,
                "dom_index": dom_index,
                "title": title[:220],
                "state": state,
                "label": full_text[:300],
            })
        except Exception:
            continue

    return {"ok": True, "module": int(module_number),
            "route": route_without_secrets(page.url), "activities": activities}


def open_completed_activity(page, module_number, activity_index):
    """Ouvre une activité ordinaire Terminée/Voir ou En cours/Continuer.

    Toujours sur commande explicite. Refuse les autres cartes : aucun
    bouton ``Lancer``, palier,
    questionnaire verrouillé ou formulaire de retour n'est cliqué.
    """
    found = list_activities(page, module_number)
    if not found["ok"]:
        return {"ok": False, "reason": found["reason"]}
    try:
        index = int(activity_index)
    except (ValueError, TypeError):
        return {"ok": False, "reason": "index_invalide"}
    activity = next((a for a in found["activities"] if a["index"] == index), None)
    if activity is None:
        return {"ok": False, "reason": "activite_introuvable"}
    if activity["state"] not in ("completed", "in_progress"):
        return {"ok": False, "reason": f"etat_interdit:{activity['state']}",
                "title": activity["title"]}
    panel = _panel_for_module(page, module_number)
    if panel is None:
        return {"ok": False, "reason": "panneau_introuvable"}
    target = panel.locator("div.relative.cursor-pointer, div.relative.cursor-default").nth(
        activity["dom_index"])
    try:
        # Revérification juste avant clic, car une SPA peut changer après la liste.
        current_title = " ".join(target.locator("p.text-pretty").first.inner_text().split())
        current_label = normalize(target.inner_text())
        valid_label = (
            (activity["state"] == "completed" and
             "terminee" in current_label and "voir" in current_label)
            or
            (activity["state"] == "in_progress" and
             "en cours" in current_label and "continuer" in current_label)
        )
        if current_title != activity["title"] or not valid_label:
            return {"ok": False, "reason": "etat_modifie_depuis_inspection"}
    except Exception:
        return {"ok": False, "reason": "carte_modifiee"}
    if not safe_click(target):
        return {"ok": False, "reason": "clic_refuse"}
    page.wait_for_timeout(700)
    return {"ok": True, "title": activity["title"],
            "state": activity["state"],
            "route": route_without_secrets(page.url)}
