"""Capture DOM structurelle via Playwright, sans cookies ou stockage local.

Une capture peut malgré tout contenir des consignes/textes privés ; il faut
la relire avant tout partage. Aucun formulaire n'est soumis.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .detector import classify_page, is_globalexam_host, route_without_secrets


# Évalue seulement des informations structurelles / visibles. N'inspecte
# ni cookie, ni localStorage, ni sessionStorage, ni réponses réseau.
DOM_PROBE_JS = r"""() => {
  const OUT = {
    title: (document.title || '').slice(0, 150),
    lang: document.documentElement?.lang || '',
    visible_text: '',
    headings: [], controls: [], links: [], containers: [],
    dom_counts: {},
  };
  const limit = (v, n=180) => String(v || '').replace(/\s+/g,' ').trim().slice(0,n);
  const sanitize = (v) => limit(v, 300)
    .replace(/[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}/g, '[EMAIL]')
    .replace(/(?:Bearer\s+)[a-z0-9._-]+/ig, 'Bearer [TOKEN]');
  const attr = (el, key) => sanitize(el.getAttribute?.(key) || '');
  const tag = (el) => (el.tagName || '').toLowerCase();
  const readLabel = (el) => sanitize(
      attr(el,'aria-label') || attr(el,'title') ||
      (el.labels?.[0]?.textContent || '') ||
      (el.innerText || el.textContent || '').slice(0,300)
  );
  const visible = (el) => {
    try { const s = getComputedStyle(el); const b = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden'
             && Number(s.opacity) !== 0 && b.width > 0 && b.height > 0;
    } catch { return false; }
  };
  const safe = (el) => ({
    tag: tag(el), id: attr(el,'id').slice(0,80),
    classes: attr(el,'class').slice(0,200),
    role: attr(el,'role'), type: attr(el,'type'),
    label: readLabel(el),
    testid: attr(el,'data-testid'), data_name: attr(el,'data-name'),
    data_state: attr(el,'data-state'),
    aria_expanded: attr(el,'aria-expanded'), aria_disabled: attr(el,'aria-disabled'),
  });
  const isControl = (el) => {
    const t=tag(el), r=attr(el,'role');
    return ['button','input','select','textarea','summary','label'].includes(t)
      || ['button','radio','checkbox','combobox','textbox','option','tab','link',
          'menuitem','switch','slider','radiogroup','listbox'].includes(r)
      || el.hasAttribute('data-draggable-item-id')
      || el.hasAttribute('draggable');
  };
  const isContainer = (el) => {
    const t=tag(el), r=attr(el,'role');
    return ['main','nav','header','footer','article','section','form','fieldset'].includes(t)
      || ['main','navigation','dialog','group','tablist','tabpanel','list',
          'form','region'].includes(r)
      || el.hasAttribute('data-testid') || el.hasAttribute('data-name')
      || String(el.className || '').includes('drop-zone');
  };
  // Inclut les éléments des shadowRoots ouvertes.
  const stack=[document.documentElement]; let scanned=0;
  while (stack.length && scanned < 18000) {
    const el=stack.pop(); scanned++;
    if (!el || el.nodeType !== 1) continue;
    const t=tag(el);
    if (['script','style','noscript','template'].includes(t)) continue;
    if (visible(el)) {
      if (/^h[1-6]$/.test(t) && OUT.headings.length < 140) {
        OUT.headings.push({level: t, text: readLabel(el)});
      }
      if (isControl(el) && OUT.controls.length < 900) {
        const c=safe(el);
        if (t==='input') {
          c.input_type = attr(el,'type') || 'text';
          c.placeholder = attr(el,'placeholder');
          // Jamais input.value / checked private state.
        }
        if (t==='select') c.option_count = el.options?.length || 0;
        OUT.controls.push(c);
      }
      if (t==='a' && OUT.links.length < 250) {
        const href=attr(el,'href');
        let hrefPath='';
        try {const u=new URL(href,document.baseURI);
          if (u.hostname === location.hostname) hrefPath=u.pathname;
        } catch {}
        OUT.links.push({text:readLabel(el), path:hrefPath});
      }
      if (isContainer(el) && OUT.containers.length < 550) {
        const c=safe(el); c.children=el.children?.length || 0;
        OUT.containers.push(c);
      }
    }
    if (el.shadowRoot) stack.push(...Array.from(el.shadowRoot.children).reverse());
    stack.push(...Array.from(el.children).reverse());
  }
  let txt='';
  try {txt=document.querySelector('main')?.innerText || document.body?.innerText || '';} catch {}
  OUT.visible_text = sanitize(txt).slice(0,300); // l'outline ne publie qu'un court aperçu
  const arr=OUT.controls;
  const n=(fn)=>arr.filter(fn).length;
  OUT.dom_counts={
    elements_scanned:scanned, controls:arr.length, containers:OUT.containers.length,
    buttons:n(x=>x.tag==='button'||x.role==='button'),
    password_inputs:n(x=>x.input_type==='password'),
    radio_inputs:n(x=>x.input_type==='radio'||x.role==='radio'),
    checkbox_inputs:n(x=>x.input_type==='checkbox'||x.role==='checkbox'),
    text_inputs:n(x=>x.tag==='input' && !['hidden','password','radio','checkbox','submit'].includes(x.input_type)),
    textareas:n(x=>x.tag==='textarea'),
    selects:n(x=>x.tag==='select'||x.role==='combobox'),
    radiogroups:n(x=>x.role==='radiogroup'),
    draggables:n(x=>x.data_name.includes('draggable')||x.classes.includes('draggable')),
    dropzones:OUT.containers.filter(x=>x.classes.includes('drop-zone')).length,
  };
  return OUT;
}"""


def redact_text(value):
    """Évite les données d'identification les plus évidentes dans les logs."""
    value = str(value or "")
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[EMAIL]", value)
    value = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [TOKEN]", value)
    return value


def _frame_probe(frame):
    url = frame.url
    if not is_globalexam_host(url):
        return {"route": route_without_secrets(url), "access": "external_frame_skipped"}
    try:
        parsed = frame.evaluate(DOM_PROBE_JS)
        parsed["route"] = route_without_secrets(url)
        return parsed
    except Exception as exc:
        return {"route": route_without_secrets(url), "error": redact_text(type(exc).__name__)}


def capture_page(page, label, base_dir, with_screenshot=False):
    """Crée un JSON par écran, éventuellement une capture sur demande.

    Retourne le chemin du dossier. Ne clique nulle part.
    """
    label = re.sub(r"[^a-z0-9_-]+", "_", str(label).lower())[:35] or "page"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dest = Path(base_dir) / f"{stamp}_{label}"
    dest.mkdir(parents=True, exist_ok=True)

    frames = []
    for frame in page.frames[:25]:
        frames.append(_frame_probe(frame))

    # Pour classification, page principale. Une SPA peut utiliser un iframe
    # spécifique pour l'exercice ; le rapport contient les deux.
    main = frames[0] if frames else {}
    report = {
        "schema": "globalexam_site_scan_v1",
        "label": label,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "route": route_without_secrets(page.url),
        "document": {
            "title": redact_text(main.get("title", "")),
            "lang": main.get("lang", ""),
            "visible_text": redact_text(main.get("visible_text", "")),
        },
        "headings": main.get("headings", []),
        "controls": main.get("controls", []),
        "links": main.get("links", []),
        "containers": main.get("containers", []),
        "dom_counts": main.get("dom_counts", {}),
        "frames": frames,
    }
    report["detected"] = classify_page(report)
    signature = json.dumps({
        "route": report["route"],
        "controls": report["controls"],
        "containers": report["containers"],
    }, ensure_ascii=False, sort_keys=True)
    report["structure_hash"] = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]

    (dest / "structure.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        f"Écran : {label}",
        f"Route : {report['route']}",
        f"Détection : {report['detected']}",
        f"Contrôles : {len(report['controls'])}",
        f"Conteneurs : {len(report['containers'])}",
        "",
        "Titres :",
    ]
    lines.extend(f"- {h['level']}: {h['text']}" for h in report["headings"])
    lines.extend(["", "Contrôles visibles :"])
    lines.extend(
        f"- <{c.get('tag')}> role={c.get('role')} type={c.get('type')} "
        f"name={c.get('data_name')} testid={c.get('testid')} "
        f"label={c.get('label')}"
        for c in report["controls"]
    )
    (dest / "resume.txt").write_text("\n".join(lines), encoding="utf-8")

    if with_screenshot:
        try:
            page.screenshot(path=str(dest / "capture.png"), full_page=True, timeout=10000)
        except Exception as exc:
            (dest / "screenshot_error.txt").write_text(
                type(exc).__name__, encoding="utf-8")
    return dest, report
