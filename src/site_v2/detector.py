"""Reconnaissance non intrusive d'écran via signaux sémantiques.

Ne déclenche aucun clic. Les résultats sont des hypothèses avec preuves,
pas des certitudes sur le DOM du nouveau GlobalExam.
"""
import re
from urllib.parse import urlsplit


def route_without_secrets(url):
    """Conserve seulement le schéma, l'hôte et le chemin ; retire ? et #."""
    try:
        parts = urlsplit(url or "")
        if parts.scheme not in ("https", "http"):
            return ""
        return f"{parts.scheme}://{parts.netloc}{parts.path}"
    except Exception:
        return ""


def is_globalexam_host(url):
    """Empêche de capturer accidentellement le DOM de sites tiers."""
    try:
        host = (urlsplit(url).hostname or "").lower()
        return host == "global-exam.com" or host.endswith(".global-exam.com")
    except Exception:
        return False


def classify_page(snapshot):
    """Déduit une famille d'écran à partir des indices visibles et DOM."""
    route = (snapshot.get("route") or "").lower()
    document = snapshot.get("document") or {}
    controls = snapshot.get("controls") or []
    headings = snapshot.get("headings") or []
    counts = snapshot.get("dom_counts") or {}
    text = " ".join([
        document.get("visible_text", ""),
        " ".join(str(x.get("text", "")) for x in controls),
        " ".join(str(x.get("text", "")) for x in headings),
    ]).lower()
    text = re.sub(r"\s+", " ", text)
    names = " ".join((x.get("label", "") or "").lower() for x in controls)
    evidence = []

    # Routes observées sur la nouvelle interface : l'URL prime sur les onglets.
    path = urlsplit(route).path.rstrip("/")
    if re.search(r"/activity/[^/]+/result$", path):
        return {"kind": "result", "confidence": .99, "evidence": ["route résultat"]}
    if re.search(r"/activity/[^/]+/content/[^/]+/correction$", path):
        return {"kind": "correction", "confidence": .99, "evidence": ["route correction"]}
    if re.search(r"/activity/[^/]+/content/[^/]+$", path):
        if not controls and not headings:
            return {"kind": "loading", "confidence": .7, "evidence": ["activité pas encore chargée"]}
        return {"kind": "exercise", "confidence": .98, "evidence": ["route exercice"]}
    if path in ("/levels/content", "/levels"):
        return {"kind": "catalog", "confidence": .99, "evidence": ["route parcours"]}
    if path in ("", "/") and "general.global-exam.com" in route:
        return {"kind": "home", "confidence": .95, "evidence": ["route accueil"]}

    if "auth.global-exam.com" in route or counts.get("password_inputs", 0):
        evidence.append("connexion détectée")
        return {"kind": "login", "confidence": 0.96, "evidence": evidence}

    result_hits = [x for x in ("votre score", "your score", "résultat", "results", "score obtenu") if x in text]
    if result_hits and any(x in text for x in ("continuer", "passer à la suite", "retour", "recommencer", "suivant")):
        evidence.extend(result_hits)
        return {"kind": "result", "confidence": 0.8, "evidence": evidence}

    if any(x in text for x in ("correction", "bonne réponse", "correct answer", "réponse attendue")):
        if any(x in text for x in ("mauvaise réponse", "incorrect", "explication", "solution", "réponse attendue")):
            evidence.append("indices de correction")
            return {"kind": "correction", "confidence": 0.68, "evidence": evidence}

    question_count = sum(int(counts.get(k, 0) or 0) for k in (
        "radio_inputs", "checkbox_inputs", "selects", "text_inputs", "textareas",
        "draggables", "dropzones", "radiogroups"))
    action_hits = [x for x in ("valider", "vérifier", "submit", "validate", "passer", "check answer") if x in names]
    if question_count > 0 and action_hits:
        evidence.append(f"{question_count} contrôle(s) de réponse")
        evidence.append("action de validation visible")
        return {"kind": "exercise", "confidence": 0.83, "evidence": evidence}
    if question_count > 0 and ("question" in text or "exercice" in text):
        evidence.append(f"{question_count} contrôle(s) de réponse")
        return {"kind": "exercise", "confidence": 0.58, "evidence": evidence}

    if any(x in route for x in ("/level", "/module", "/course", "/path", "/lesson")):
        evidence.append("URL ressemblant à une page de parcours")
        return {"kind": "catalog", "confidence": 0.48, "evidence": evidence}

    if len(snapshot.get("links") or []) >= 5:
        evidence.append("plusieurs liens de navigation")
        return {"kind": "catalog", "confidence": 0.35, "evidence": evidence}

    return {"kind": "unknown", "confidence": 0.0, "evidence": ["structure nouvelle ou non reconnue"]}
