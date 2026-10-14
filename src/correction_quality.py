"""Règles conservatrices de vérification des corrections.

Fonctions pures : aucun accès réseau, aucune modification du DOM.
"""
import re

from safety_clicks import normalize


CHOICE_TYPES = {"qcm_single", "qcm_multiple", "button_choice", "span_choice"}
SINGLE_TYPES = {"qcm_single", "button_choice", "span_choice"}


def structurally_valid(packet, answer):
    """Rejette les réponses vides, partielles ou incompatibles avec la question."""
    if not isinstance(answer, dict):
        return False
    kind = answer.get("kind")
    exercise_type = packet.get("exercise_type")
    if exercise_type in CHOICE_TYPES and kind == "choice_indices":
        raw_indices = answer.get("indices", [])
        if not isinstance(raw_indices, list) or not raw_indices:
            return False
        if len(raw_indices) != len(set(map(str, raw_indices))):
            return False
        choices = packet.get("choices", []) or []
        valid = {x.get("index") for x in choices if not x.get("disabled")}
        if any(isinstance(x, bool) or not isinstance(x, int) or x not in valid for x in raw_indices):
            return False
        if exercise_type in SINGLE_TYPES and len(raw_indices) != 1:
            return False
        return True
    if exercise_type == "ordering" and kind == "ordering":
        all_items = [*((packet.get("ordering") or {}).get("available", []) or []),
                     *((packet.get("ordering") or {}).get("already_placed", []) or [])]
        items = answer.get("items", [])
        if not isinstance(items, list) or len(items) != len(all_items) or not items:
            return False
        source_ids = [str(x.get("id") or "") + ":" + normalize(x.get("text", "")) for x in all_items]
        answer_ids = [str(x.get("id") or "") + ":" + normalize(x.get("text", "")) for x in items]
        return sorted(source_ids) == sorted(answer_ids)
    if exercise_type == "select" and kind == "select_options":
        src_fields = packet.get("fields", []) or []
        answer_fields = answer.get("fields", []) or []
        if not src_fields or len(src_fields) != len(answer_fields):
            return False
        for src, dest in zip(src_fields, answer_fields):
            if src.get("index") != dest.get("field_index"):
                return False
            allowed = {opt.get("index") for opt in src.get("options", []) or []}
            chosen = dest.get("selected_option_indices", [])
            if not isinstance(chosen, list) or len(chosen) != 1 or chosen[0] not in allowed:
                return False
        return True
    if exercise_type == "text_input" and kind == "text_fields":
        src_fields = packet.get("fields", []) or []
        ans_fields = answer.get("fields", []) or []
        return bool(src_fields) and len(src_fields) == len(ans_fields) and all(
            src.get("index") == ans.get("field_index")
            and str(ans.get("value") or "").strip()
            for src, ans in zip(src_fields, ans_fields)
        )
    return False


def labelled_choice(packet, correction_text):
    """Lit une solution explicitement annoncée, jamais du texte parasite.

    Exemple : `La bonne réponse est : Bicycle`.
    Ne décide pas d'un QCM multiple : plusieurs choix exigent une preuve DOM.
    """
    if packet.get("exercise_type") not in SINGLE_TYPES:
        return None
    choices = packet.get("choices", []) or []
    # Une solution doit être associée à UNE ligne de correction explicite.
    pattern = re.compile(
        r"^(?:la\s+bonne\s+reponse|reponse\s+attendue|reponse\s+correcte|"
        r"correct\s+answer|the\s+correct\s+answer)"
        r"(?:\s+(?:est|is))?\s*[:=\-–]?\s+(.+?)\s*$"
    )
    candidates = []
    for line in (correction_text or "").splitlines():
        match = pattern.fullmatch(normalize(line))
        if not match:
            continue
        target = match.group(1).strip().rstrip(". ")
        for choice in choices:
            if normalize(choice.get("text", "")).rstrip(". ") == target:
                candidates.append(choice)
    unique = {x.get("index"): x for x in candidates}
    if len(unique) != 1:
        return None
    chosen = next(iter(unique.values()))
    return {"kind": "choice_indices", "indices": [chosen["index"]],
            "choices": [{"index": chosen["index"], "text": chosen.get("text", ""),
                         "value": chosen.get("value")}]} 


def assess(packet, answer, source):
    """Retourne verified/provisional/rejected selon provenance explicite."""
    if not structurally_valid(packet, answer):
        return "rejected", "invalid_or_incomplete_answer"
    if source in {"selected_data_state_correct", "dom_correct_markers", "labelled_correct_answer"}:
        return "verified", "explicit_correctness_evidence"
    if source in {"correction_text_delta", "ordering_corrected_dom", "text_verdict_correct", "dom_class_only"}:
        return "provisional", "not_enough_evidence_to_reuse"
    return "rejected", "untrusted_evidence_source"
