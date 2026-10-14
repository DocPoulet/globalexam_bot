"""Ouverture guidée vérifiée des activités terminées du nouveau catalogue.

Un clic Playwright réussi n'est *pas* une preuve d'ouverture d'activité.
Le navigateur doit présenter une route d'activité ou un écran d'exercice
reconnaissable ; les simples changements d'accordéon/catalogue ne suffisent pas.
Aucun exercice n'est complété ou soumis par cette sonde.
"""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .catalog import ensure_module_open, open_completed_activity, module_list
from .detector import classify_page, route_without_secrets
from .module_probe import save_module_probe
from .snapshot import capture_page

_ACTIVITY_PATH_RE = re.compile(r"^/activity/[^/]+/(?:content(?:/[^/]+(?:/correction)?)?|result)/?$")
_LOGIN_HOST = "auth.global-exam.com"


def _fingerprint(page):
    """Empreinte du texte visible sans persister son contenu."""
    try:
        text = page.locator("body").inner_text(timeout=1800)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return None


def _pages(context, fallback):
    try:
        return list(context.pages) or [fallback]
    except Exception:
        return [fallback]


def _export(directory):
    archive = Path(str(directory) + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
        for file in sorted(directory.iterdir()):
            if file.is_file():
                output.write(file, file.name)
    return archive


def _is_login(page):
    try:
        return urlsplit(page.url).hostname == _LOGIN_HOST
    except Exception:
        return False


def _is_catalog(page):
    """Un catalogue prêt, pas une redirection login ou un shell incomplet."""
    if _is_login(page):
        return False
    path = urlsplit(page.url).path.rstrip("/")
    if path not in ("/levels", "/levels/content", ""):
        return False
    # Pour les tests HTML (about:blank), les modules visibles suffisent.
    return bool(module_list(page))


def _activity_evidence(page):
    """Signaux positifs ; *jamais* un simple changement du texte du catalogue."""
    if _is_login(page):
        return None
    path = urlsplit(page.url).path.rstrip("/")
    if _ACTIVITY_PATH_RE.fullmatch(path):
        return "activity_route"
    if path in ("/levels", "/levels/content"):
        return None
    try:
        choices = page.locator(
            "input[type='radio'],input[type='checkbox'],select,textarea,"
            "[data-draggable-item-id],.ordering-drop-zone"
        ).count()
        if choices:
            buttons = page.locator("button,[role='button']")
            for i in range(min(buttons.count(), 80)):
                button = buttons.nth(i)
                if button.is_visible():
                    text = (button.inner_text(timeout=700) or "").strip().lower()
                    if text in ("valider", "validate", "vérifier", "verifier", "submit", "passer"):
                        return "question_controls"
    except Exception:
        pass
    return None


def _wait_for_ready_catalog(page, timeout_ms=1800):
    """Attend une éventuelle redirection d'accueil ; n'essaie pas de se connecter."""
    steps = max(1, timeout_ms // 200)
    for i in range(steps + 1):
        if _is_catalog(page):
            return True
        if i < steps:
            try:
                page.wait_for_timeout(200)
            except Exception:
                break
    return False


def _wait_for_activity(page, context, previous_pages, timeout_ms=6500):
    """Attend un véritable signal d'activité ou un nouvel onglet pertinent."""
    total = max(1, timeout_ms // 200)
    for i in range(total + 1):
        for candidate in _pages(context, page):
            if id(candidate) in previous_pages and candidate is not page:
                continue
            try:
                if candidate.is_closed():
                    continue
                evidence = _activity_evidence(candidate)
                if evidence:
                    return candidate, evidence
            except Exception:
                continue
        if i < total:
            try:
                page.wait_for_timeout(200)
            except Exception:
                break
    return page, None


def open_capture_completed(page, context, module_number, activity_index,
                           destination, *, wait_ms=6500, ready_ms=1800):
    """Tente une seule ouverture, vérifie la destination et exporte un diagnostic.

    ``action.clicked`` = Playwright a cliqué une carte sûre.
    ``action.ok`` = vraie activité détectée après le clic.
    Le catalogue seul n'est JAMAIS une ouverture réussie.
    """
    initial_route = route_without_secrets(page.url)
    old_ids = {id(item) for item in _pages(context, page)}
    result = {"ok": False, "reason": "catalogue_indisponible"}
    ready = _wait_for_ready_catalog(page, ready_ms)
    ready_route = route_without_secrets(page.url)
    before_hash = _fingerprint(page)
    clicked = False
    evidence = None
    target = page

    if ready:
        try:
            if ensure_module_open(page, module_number):
                # Le fingerprint doit être mesuré APRÈS avoir déplié le module.
                before_hash = _fingerprint(page)
                result = open_completed_activity(page, module_number, activity_index)
                clicked = bool(result.get("ok"))
            else:
                result = {"ok": False, "reason": "module_introuvable_ou_ferme"}
        except Exception as exc:
            result = {"ok": False, "reason": "erreur_ouverture:" + type(exc).__name__}
    else:
        result = {
            "ok": False,
            "reason": "connexion_requise" if _is_login(page) else "catalogue_non_charge",
        }

    if clicked:
        target, evidence = _wait_for_activity(page, context, old_ids, wait_ms)

    verified = bool(clicked and evidence)
    after_route = route_without_secrets(target.url)
    after_hash = _fingerprint(target)
    changed = (ready_route != after_route or before_hash != after_hash or target is not page)
    label = "activite_ouverte_confirmee" if verified else "ouverture_activite_non_confirmee"
    directory, report = capture_page(target, label, destination)

    if not verified and ready and not _is_login(target):
        # On inspecte la carte/panneau réel si l'on est resté sur le catalogue.
        try:
            if _is_catalog(target):
                save_module_probe(target, directory, module_number)
        except Exception:
            pass

    reason = None if verified else (
        "clic_sans_ouverture_confirmee" if clicked else result.get("reason")
    )
    note = (
        "Le clic a eu lieu, mais aucune activité n'a été détectée. "
        "Le catalogue, un accordéon ou une redirection ne suffisent pas."
        if clicked and not verified else
        "Connexion nécessaire : connecte-toi manuellement, ouvre Parcours puis relance voir N M."
        if reason == "connexion_requise" else
        "Catalogue non prêt : ouvre Parcours avant la commande voir N M."
        if reason == "catalogue_non_charge" else None
    )
    trace = {
        "schema": "globalexam_activity_open_trace_v2",
        "requested_module": int(module_number),
        "requested_activity": int(activity_index),
        "action": {
            "ok": verified,
            "clicked": clicked,
            "reason": reason,
            "title": result.get("title"),
        },
        "initial_route": initial_route,
        "ready_route": ready_route,
        "after_route": after_route,
        "new_tab": target is not page,
        "visible_structure_changed": changed,
        "activity_evidence": evidence,
        "screen_kind": (report.get("detected") or {}).get("kind"),
        "diagnostic_note": note,
    }
    (directory / "navigation_trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive = _export(directory)
    return {**trace, "page": target, "directory": directory, "archive": archive}
