"""Diagnostic ciblé du panneau de module GlobalExam ouvert.

Observe la structure et les libellés affichés sans clic, cookies, valeurs de
champs, jetons ou stockage navigateur. Aucune réponse n'est soumise.
"""
import json
import re
from pathlib import Path
from .detector import is_globalexam_host, route_without_secrets


MODULE_PROBE_JS = r"""(args) => {
  const maxNodes = 4500;
  const clean = (v, n=200) => String(v ?? '')
    .replace(/\s+/g, ' ').trim().slice(0, n)
    .replace(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/gi, '[EMAIL]')
    .replace(/Bearer\s+[a-z0-9._-]+/gi, 'Bearer [TOKEN]');
  const tag = el => String(el?.tagName || '').toLowerCase();
  const attr = (el, key, n=120) => clean(el?.getAttribute?.(key) || '', n);
  const shown = el => {
    try {
      const s = getComputedStyle(el), r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' &&
             s.opacity !== '0' && r.width > 0 && r.height > 0;
    } catch { return false; }
  };
  const ownText = el => clean(Array.from(el.childNodes || [])
    .filter(n => n.nodeType === 3).map(n => n.textContent).join(' '), 160);
  const nodeText = (el,n=250) => clean(el?.innerText || '',n);
  const safePath = el => {
    if (tag(el) !== 'a') return '';
    try { const url = new URL(el.getAttribute('href') || '', document.baseURI);
      return url.origin === location.origin ? url.pathname.slice(0,200) : '';
    } catch { return ''; }
  };
  const describe = (el, depth=0) => ({
    tag:tag(el), depth, id:attr(el,'id',80),
    classes:attr(el,'class',180), role:attr(el,'role',60),
    data_name:attr(el,'data-name',100), testid:attr(el,'data-testid',100),
    aria_label:attr(el,'aria-label',120), expanded:attr(el,'aria-expanded',30),
    title:attr(el,'title',100), href_path:safePath(el),
    own_text:ownText(el), text:nodeText(el,180),
    visible:shown(el), child_count:el.children?.length || 0,
  });
  // Button's aria-expanded identifies the open accordion even when the
  // content is rendered elsewhere in a CSS grid / an adjacent subtree.
  const modules = Array.from(document.querySelectorAll('button'))
    .filter(el => /^MODULE\s+\d+\b/i.test(nodeText(el,80)));
  const targetNumber = Number(args?.module_num || 0);
  let selected = targetNumber
    ? modules.find(el => Number((nodeText(el,80).match(/^MODULE\s+(\d+)/i)||[])[1])===targetNumber)
    : modules.find(el => attr(el,'aria-expanded')==='true');
  if (!selected) selected = modules[0] || null;
  if (!selected) return {
    detected:false, reason:'Aucun bouton MODULE trouvé', modules:[],
  };
  const selectedNum = Number((nodeText(selected,80).match(/^MODULE\s+(\d+)/i)||[])[1]);
  const pos = modules.indexOf(selected);
  const next = modules[pos+1] || null;
  const output = {
    detected:true, selected_module:selectedNum,
    module_title:nodeText(selected,250), is_expanded:attr(selected,'aria-expanded')==='true',
    module_buttons:modules.map(b=>({
      number:Number((nodeText(b,80).match(/^MODULE\s+(\d+)/i)||[])[1]),
      expanded:attr(b,'aria-expanded'), label:nodeText(b,160)
    })),
    ancestor_chain:[], sibling_clusters:[], section_text:[],
    section_outline:[], section_clickables:[],
    section_tag_histogram:{}, section_nodes_seen:0,
    section_truncated:false, warnings:[],
  };
  // Up to 7 ancestors: enough to understand the accordion/grid wrappers.
  let ancestor=selected;
  for(let level=0;level<7&&ancestor;level++,ancestor=ancestor.parentElement){
    const a=describe(ancestor,level);
    a.total_descendants=ancestor.querySelectorAll('*').length;
    a.visible_text_snippet=nodeText(ancestor,1200);
    output.ancestor_chain.push(a);
    if(level<=4 && ancestor.parentElement){
      const siblings=Array.from(ancestor.parentElement.children);
      output.sibling_clusters.push({level, sibling_count:siblings.length,
        siblings:siblings.slice(0,30).map(e=>({
          ...describe(e), sample_text:nodeText(e,500)
        }))});
    }
  }
  // Region of the DOM between this module header and the next header,
  // including non-interactive div/span/p/li cards with click handlers.
  let walker=document.createTreeWalker(document.body,NodeFilter.SHOW_ELEMENT);
  let current; let started=false; let total=0; let depth=0;
  const seenText=new Set();
  while((current=walker.nextNode())){
    if(current===selected) started=true;
    if(!started) continue;
    if(current===next) break;
    const t=tag(current);
    if(['script','style','noscript','template','svg','path','use','symbol'].includes(t)) continue;
    total++;
    if(total>maxNodes){output.section_truncated=true;break;}
    output.section_tag_histogram[t]=(output.section_tag_histogram[t]||0)+1;
    if(!shown(current))continue;
    const own=ownText(current);
    if(own && !seenText.has(own) && output.section_text.length<400){
      output.section_text.push({tag:t, text:own}); seenText.add(own);
    }
    if(output.section_outline.length<750){
      output.section_outline.push({
        tag:t, depth:Math.min(20,Math.max(0,(()=>{let d=0,p=current;while(p&&p!==selected&&d<25){p=p.parentElement;d++}return d})())),
        own_text:own, classes:attr(current,'class',140), role:attr(current,'role',50),
        data_name:attr(current,'data-name',90), testid:attr(current,'data-testid',90),
        aria_label:attr(current,'aria-label',120), href_path:safePath(current),
        children:current.children.length,
      });
    }
    const cls=attr(current,'class',250);
    const role=attr(current,'role');
    const tabindex=current.getAttribute('tabindex');
    const interactive=['button','a','summary','input','select','label'].includes(t)
      || ['button','link','menuitem','tab','option'].includes(role)
      || tabindex!==null || /cursor-pointer|cursor-grab/.test(cls)
      || typeof current.onclick==='function';
    if(interactive&&output.section_clickables.length<280){
      const entry=describe(current);
      entry.tabindex=tabindex; entry.onclick_registered=typeof current.onclick==='function';
      output.section_clickables.push(entry);
    }
  }
  output.section_nodes_seen=total;
  if(!output.is_expanded) output.warnings.push('Module non ouvert : ouvre-le avant capture');
  if(output.section_clickables.length<=1) output.warnings.push(
    'Aucun contrôle de lancement standard repéré ; examiner section_outline et screenshot');
  if(total>=maxNodes) output.warnings.push('Limite de nœuds atteinte');
  return output;
}"""


def inspect_module(page, module_num=None):
    """Retourne l'analyse structurelle d'un module sans agir sur le site."""
    safe_frame = next((f for f in page.frames if is_globalexam_host(f.url)), None)
    if safe_frame is None:
        return {"detected": False, "reason": "Aucune frame GlobalExam accessible"}
    data = safe_frame.evaluate(MODULE_PROBE_JS, {"module_num": module_num})
    data["route"] = route_without_secrets(safe_frame.url)
    return data


def save_module_probe(page, dest, module_num=None):
    """Sauvegarde JSON complet et résumé lisible à proximité de structure.json."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    data = inspect_module(page, module_num)
    (dest / "module_activities.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"Module: {data.get('selected_module')}",
        f"Ouvert: {data.get('is_expanded')}",
        f"Titre: {data.get('module_title', '')}",
        f"Nœuds inspectés: {data.get('section_nodes_seen', 0)}",
        f"Éléments cliquables: {len(data.get('section_clickables', []))}",
        "", "Texte des éléments :",
    ]
    for item in data.get("section_text", [])[:250]:
        lines.append("- " + item.get("text", ""))
    lines += ["", "Contrôles cliquables potentiels :"]
    for item in data.get("section_clickables", []):
        lines.append(f"- <{item.get('tag')}> {item.get('text','')} "
                     f"role={item.get('role')} class={item.get('classes')}")
    if data.get("warnings"):
        lines += ["", "Avertissements :", *["- " + x for x in data["warnings"]]]
    (dest / "module_resume.txt").write_text("\n".join(lines), encoding="utf-8")
    return data
