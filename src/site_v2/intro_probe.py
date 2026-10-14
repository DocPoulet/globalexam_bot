"""Navigation guidée de l'introduction à la question suivante.

Un seul clic explicite sur « Suivant », et seulement lorsque l'écran est une
introduction sans champ de réponse. Aucune réponse/validation automatique.
"""
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from safety_clicks import safe_click, normalize
from .detector import is_globalexam_host, route_without_secrets
from .snapshot import capture_page, redact_text

EXERCISE_ROUTE = re.compile(r"^/activity/[^/]+/content/[^/]+/?$")


def _text(page):
    for selector in ("main", "[role='main']", "body"):
        try:
            loc = page.locator(selector)
            if loc.count():
                return (loc.first.inner_text(timeout=1500) or "")[:8000]
        except Exception:
            pass
    return ""


def _has_answer_controls(page):
    """Inclut les champs radio masqués avec sr-only (nouvelle interface)."""
    selectors = (
        "input[type=radio]", "input[type=checkbox]", "input:not([type]):not([hidden])",
        "input[type=text]", "textarea", "select", "[contenteditable=true]",
        "[role=radiogroup]", "[role=radio]", "[role=checkbox]",
        "[data-draggable-item-id]", "[data-name='user-answer-container']",
        ".ordering-drop-zone", ".draggable-item"
    )
    for selector in selectors:
        try:
            if page.locator(selector).count():
                return True
        except Exception:
            continue
    return False


def is_introduction(page):
    if not is_globalexam_host(page.url):
        return False
    if not EXERCISE_ROUTE.fullmatch(urlsplit(page.url).path):
        return False
    if _has_answer_controls(page):
        return False
    try:
        headings = page.locator("h1,h2,h3")
        for i in range(min(headings.count(), 30)):
            h = headings.nth(i)
            if h.is_visible() and normalize(h.inner_text(timeout=900)) in (
                "introduction", "intro"
            ):
                return True
    except Exception:
        pass
    return False


def _next_button(page):
    try:
        buttons = page.get_by_role("button", name="Suivant", exact=True)
        for i in range(min(buttons.count(), 15)):
            button = buttons.nth(i)
            if button.is_visible() and button.is_enabled() and (
                normalize(button.get_attribute("aria-disabled") or "") != "true"
            ):
                return button
    except Exception:
        pass
    return None


QUESTION_PROBE_JS = r"""() => {
 const trunc=(v,n=300)=>String(v||'').replace(/\s+/g,' ').trim().slice(0,n);
 const visible=(e)=>{try{let b=e.getBoundingClientRect(),s=getComputedStyle(e);return b.width>0&&b.height>0&&s.visibility!=='hidden'&&s.display!=='none';}catch{return false;}};
 const fields=[];
 const els=[...document.querySelectorAll('input,select,textarea,[role="radio"],[role="checkbox"],[contenteditable="true"]')].slice(0,150);
 for(const el of els){
   const t=(el.getAttribute('type')||el.tagName.toLowerCase()).toLowerCase();
   if(t==='hidden'||t==='password')continue;
   let label='';
   try { label=[...el.labels||[]].map(x=>x.innerText||x.textContent).join(' ') ||
       (el.id?document.querySelector('label[for="'+CSS.escape(el.id)+'"]')?.textContent:'') ||
       el.closest('label')?.textContent || el.getAttribute('aria-label') || ''; }catch{}
   fields.push({tag:el.tagName.toLowerCase(),type:t,
     id:trunc(el.id,100), name:trunc(el.getAttribute('name'),100),
     label:trunc(label,500),placeholder:trunc(el.getAttribute('placeholder'),200),
     visually_hidden:!visible(el),
     option_labels: el.tagName==='SELECT'?[...el.options].map(x=>trunc(x.textContent,200)).slice(0,40):undefined});
 }
 const labels=[...document.querySelectorAll('label')].filter(visible).slice(0,120).map(el=>({
   text:trunc(el.innerText||el.textContent,500),for:trunc(el.getAttribute('for'),100),
   class_name:trunc(el.className,120)
 }));
 const drag=[...document.querySelectorAll('[data-draggable-item-id],.draggable-item')].slice(0,80).map(el=>({
   text:trunc(el.innerText||el.textContent,350), draggable_id:trunc(el.getAttribute('data-draggable-item-id'),100)
 }));
 const zones=[...document.querySelectorAll('[data-name="user-answer-container"],.ordering-drop-zone')].slice(0,50).map(el=>({
   tag:el.tagName.toLowerCase(), text:trunc(el.innerText||el.textContent,600),name:trunc(el.getAttribute('data-name'),100)
 }));
 const buttons=[...document.querySelectorAll('button,[role="button"]')].filter(visible).slice(0,90).map(el=>({
    text:trunc(el.innerText||el.getAttribute('aria-label'),300),
    disabled:el.hasAttribute('disabled')||el.getAttribute('aria-disabled')==='true'
 }));
 const text=trunc(document.querySelector('main')?.innerText || document.body?.innerText || '',6500);
 return {text,fields,labels,draggables:drag,dropzones:zones,buttons};
}"""


def save_question_detail(page, directory):
    """Extraction passive des labels associés aux radios masqués, etc."""
    try:
        detail = page.evaluate(QUESTION_PROBE_JS)
    except Exception as exc:
        detail = {"error": type(exc).__name__}
    if isinstance(detail, dict) and "text" in detail:
        detail["text"] = redact_text(detail["text"])
    (Path(directory) / "question_detail.json").write_text(
        json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    return detail


def _archive(directory):
    archive = Path(str(directory) + ".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.iterdir()):
            if p.is_file():
                z.write(p, p.name)
    return archive


def advance_intro_and_capture(page, destination, *, wait_ms=4500):
    """Sur ordre utilisateur, avance UNE SEULE FOIS depuis l'introduction.

    Ne clique jamais lorsque des champs de réponse sont déjà présents.
    Toujours sauvegarder le résultat et le statut exact, même si rien ne bouge.
    """
    if not is_introduction(page):
        return {"ok": False, "clicked": False, "reason": "not_an_introduction"}
    button = _next_button(page)
    if button is None:
        return {"ok": False, "clicked": False, "reason": "next_button_missing_or_disabled"}
    before_route = route_without_secrets(page.url)
    before_text = _text(page)
    if not safe_click(button, timeout=2500):
        return {"ok": False, "clicked": False, "reason": "next_click_failed"}

    # SPA: URL peut rester identique; le texte ou les contrôles changent.
    change_seen = False
    for _ in range(max(1, wait_ms // 200)):
        page.wait_for_timeout(200)
        if route_without_secrets(page.url) != before_route or _text(page) != before_text:
            change_seen = True
            if not is_introduction(page):
                break

    directory, report = capture_page(page, "apres_introduction", destination)
    detail = save_question_detail(page, directory)
    still_intro = is_introduction(page)
    has_answer = _has_answer_controls(page)
    after_route = route_without_secrets(page.url)
    trace = {
        "schema": "globalexam_intro_transition_v1",
        "clicked": True,
        "ok": bool(change_seen and not still_intro and EXERCISE_ROUTE.fullmatch(urlsplit(page.url).path)),
        "reason": "still_introduction" if still_intro else ("no_visible_change" if not change_seen else None),
        "before_route": before_route,
        "after_route": after_route,
        "visible_change": change_seen,
        "has_answer_controls": has_answer,
        "still_introduction": still_intro,
        "screen_kind": (report.get("detected") or {}).get("kind"),
        "fields_detected": len(detail.get("fields", [])),
        "labels_detected": len(detail.get("labels", [])),
    }
    (directory / "intro_transition_trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**trace, "directory": directory, "archive": _archive(directory)}
