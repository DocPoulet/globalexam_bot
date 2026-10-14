"""Contrat local de contributions communautaires (V1, SANS réseau).

Les empreintes sont déterministes pour permettre une future déduplication.
ATTENTION : SHA-256 n'anonymise PAS un contenu devinable ; les empreintes
peuvent permettre des attaques par dictionnaire. Aucun envoi n'est réalisé ici.
"""

import hashlib
import json
import re
import unicodedata

from correction_quality import structurally_valid

PROTOCOL_VERSION = "1.0"
FINGERPRINT_VERSION = "sha256-nfkc-v1"
PLATFORM = "globalexam"
VERIFIED_SOURCES = frozenset({
    "selected_data_state_correct",
    "dom_correct_markers",
    "labelled_correct_answer",
})
CHOICE_TYPES = frozenset({"qcm_single", "qcm_multiple", "button_choice", "span_choice"})
SUPPORTED_TYPES = CHOICE_TYPES | {"ordering", "select"}
HEX_SHA256 = re.compile(r"^sha256:[a-f0-9]{64}$")
EMAIL = re.compile(r"(?<!\S)[^\s@<>]+@[^\s@<>]+\.[a-zA-Z]{2,}(?!\S)")
URL = re.compile(r"https?://\S+", re.IGNORECASE)
PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[ .-]?)?(?:\d[ .()-]?){9,14}(?!\d)")
LONG_SECRET = re.compile(r"\b(?:sk-|ghp_|github_pat_|Bearer\s+)[a-zA-Z0-9_.-]{12,}", re.I)


class NotShareable(ValueError):
    """Une contribution ne doit pas être incluse dans l'aperçu."""


def normalize_text(value):
    """Normalisation indépendante de la casse/espacement (accents conservés)."""
    if not isinstance(value, str):
        return ""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(domain, value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    seed = f"globalexam-community-v1\x00{domain}\x00{value}"
    return "sha256:" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def _assert_safe_text(value):
    """Refuse les questions probablement personnalisées, même si rien n'est exporté en clair."""
    value = str(value or "")
    if EMAIL.search(value) or URL.search(value) or LONG_SECRET.search(value) or PHONE.search(value):
        raise NotShareable("possible_personal_or_secret_content")
    return normalize_text(value)


def _key_of_text(value):
    cleaned = _assert_safe_text(value)
    if not cleaned:
        raise NotShareable("empty_item_label")
    return _digest("item-label", cleaned)


def _unique_keys(items):
    keys = [_key_of_text(item.get("text", "")) for item in items]
    if len(set(keys)) != len(keys):
        raise NotShareable("duplicate_or_ambiguous_item_labels")
    return keys


def _canonical_question(packet):
    if not isinstance(packet, dict):
        raise NotShareable("invalid_question_packet")
    kind = packet.get("exercise_type")
    if kind not in SUPPORTED_TYPES:
        raise NotShareable("unsupported_exercise_type")
    instruction = _assert_safe_text(packet.get("instruction"))
    context = _assert_safe_text(packet.get("context"))
    if not (instruction or context):
        raise NotShareable("missing_question_text")
    result = {
        "platform": PLATFORM,
        "exercise_type": kind,
        "instruction": instruction,
        "context": context,
        "language": normalize_text(packet.get("html_language") or ""),
    }
    if kind in CHOICE_TYPES:
        choices = packet.get("choices") or []
        if len(choices) < 2:
            raise NotShareable("insufficient_choices")
        result["choice_keys"] = sorted(_unique_keys(choices))
    elif kind == "ordering":
        order = packet.get("ordering") or {}
        items = [*(order.get("available") or []), *(order.get("already_placed") or [])]
        if len(items) < 2:
            raise NotShareable("insufficient_ordering_items")
        result["item_keys"] = sorted(_unique_keys(items))
    elif kind == "select":
        fields = packet.get("fields") or []
        if not fields:
            raise NotShareable("no_select_fields")
        result["fields"] = []
        for field in fields:
            options = field.get("options") or []
            if len(options) < 2:
                raise NotShareable("insufficient_select_options")
            result["fields"].append(sorted(_unique_keys(options)))
    return result


def _match_by_index(items, index):
    matches = [x for x in items if x.get("index") == index]
    if len(matches) != 1:
        raise NotShareable("answer_index_ambiguous_or_missing")
    return matches[0]


def _answer_fingerprints(packet, answer):
    if not structurally_valid(packet, answer):
        raise NotShareable("invalid_answer_structure")
    kind = packet["exercise_type"]
    if kind in CHOICE_TYPES:
        picked = [_match_by_index(packet["choices"], i) for i in answer["indices"]]
        return {"kind": "choice_keys", "values": sorted(_unique_keys(picked))}
    if kind == "ordering":
        original = [*((packet.get("ordering") or {}).get("available") or []),
                    *((packet.get("ordering") or {}).get("already_placed") or [])]
        if len(set(_unique_keys(original))) != len(original):
            raise NotShareable("duplicate_ordering_labels")
        # La structure est vérifiée contre le packet par correction_quality.
        return {"kind": "ordered_item_keys", "values": [_key_of_text(x.get("text")) for x in answer["items"]]}
    if kind == "select":
        values = []
        for src, chosen in zip(packet["fields"], answer["fields"]):
            opt = _match_by_index(src.get("options") or [], chosen["selected_option_indices"][0])
            values.append(_key_of_text(opt.get("text")))
        return {"kind": "field_option_keys", "values": values}
    raise NotShareable("unsupported_exercise_type")


def create_record(packet, answer, evidence_source):
    """Émet seulement des empreintes dérivées des textes (pas les textes eux-mêmes)."""
    if evidence_source not in VERIFIED_SOURCES:
        raise NotShareable("unverified_evidence_source")
    canonical = _canonical_question(packet)
    question_fp = _digest("question", canonical)
    answer_fp = _answer_fingerprints(packet, answer)
    record = {
        "question_fingerprint": question_fp,
        "exercise_type": packet["exercise_type"],
        "answer": answer_fp,
        "evidence_category": evidence_source,
    }
    record["record_fingerprint"] = _digest("record", record)
    return record


def validate_record(record):
    """Validation de forme uniquement ; la preuve réelle doit être vérifiée côté serveur."""
    if not isinstance(record, dict) or set(record) != {
        "question_fingerprint", "exercise_type", "answer", "evidence_category", "record_fingerprint"
    }:
        raise ValueError("unexpected_record_fields")
    if record["exercise_type"] not in SUPPORTED_TYPES:
        raise ValueError("unsupported_type")
    if record["evidence_category"] not in VERIFIED_SOURCES:
        raise ValueError("invalid_evidence")
    if not HEX_SHA256.fullmatch(record["question_fingerprint"]):
        raise ValueError("invalid_question_fingerprint")
    if not HEX_SHA256.fullmatch(record["record_fingerprint"]):
        raise ValueError("invalid_record_fingerprint")
    ans = record["answer"]
    allowed_answer_kinds = {
        **{x: "choice_keys" for x in CHOICE_TYPES},
        "ordering": "ordered_item_keys", "select": "field_option_keys",
    }
    if not isinstance(ans, dict) or set(ans) != {"kind", "values"} or ans["kind"] != allowed_answer_kinds[record["exercise_type"]]:
        raise ValueError("invalid_answer_shape")
    if not isinstance(ans["values"], list) or not ans["values"] or any(
        not isinstance(x, str) or not HEX_SHA256.fullmatch(x) for x in ans["values"]
    ):
        raise ValueError("invalid_answer_keys")
    # Deux champs select peuvent parfaitement avoir la même réponse
    # (p.ex. « yes » à deux endroits), contrairement aux choix/ordering.
    if ans["kind"] != "field_option_keys" and len(set(ans["values"])) != len(ans["values"]):
        raise ValueError("duplicate_answer_keys")
    if record["exercise_type"] in {"qcm_single", "button_choice", "span_choice"} and len(ans["values"]) != 1:
        raise ValueError("single_choice_expected")
    copy = {k: v for k, v in record.items() if k != "record_fingerprint"}
    if _digest("record", copy) != record["record_fingerprint"]:
        raise ValueError("record_fingerprint_mismatch")
    return True


def validate_envelope(envelope):
    if not isinstance(envelope, dict) or set(envelope) != {"schema_version", "platform", "privacy", "network_upload", "records"}:
        raise ValueError("unexpected_envelope_fields")
    if (envelope["schema_version"] != PROTOCOL_VERSION or envelope["platform"] != PLATFORM
            or envelope["privacy"] != "hashed_metadata_preview" or envelope["network_upload"] is not False):
        raise ValueError("invalid_envelope_header")
    if not isinstance(envelope["records"], list) or len(envelope["records"]) > 10000:
        raise ValueError("invalid_records")
    seen = set()
    for record in envelope["records"]:
        validate_record(record)
        if record["record_fingerprint"] in seen:
            raise ValueError("duplicate_record")
        seen.add(record["record_fingerprint"])
    return True
