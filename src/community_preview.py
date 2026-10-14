"""Aperçu local de futures contributions, lecture seule de SQLite.

Aucun import de navigateur, d'API, ni de client HTTP. Aucune donnée brute
(question, réponse, correction, URL) n'est écrite dans le JSON de prévisualisation.
"""
import json
import sqlite3
from collections import Counter
from pathlib import Path

from community_protocol import (
    PROTOCOL_VERSION, PLATFORM, VERIFIED_SOURCES,
    NotShareable, create_record, validate_envelope,
)


def _open_existing_database(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Base SQLite introuvable : {path}")
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def build_preview(database_path):
    """Ne modifie jamais la base. Ignore legacy/provisional/disputed."""
    counts = Counter()
    records = {}
    with _open_existing_database(database_path) as conn:
        rows = conn.execute("""
            SELECT q.packet_json, q.exercise_type, l.answer_json,
                   l.source_attempt_id, v.status, v.attempt_id AS verified_attempt_id,
                   v.evidence_source
            FROM learned_answers AS l
            JOIN questions AS q ON q.question_id=l.question_id
            LEFT JOIN answer_verifications AS v ON v.question_id=l.question_id
            ORDER BY q.question_id
        """).fetchall()
        for row in rows:
            if row["status"] != "verified":
                counts[row["status"] or "not_verified"] += 1
                continue
            if row["evidence_source"] not in VERIFIED_SOURCES:
                counts["untrusted_evidence"] += 1
                continue
            if not row["verified_attempt_id"] or row["verified_attempt_id"] != row["source_attempt_id"]:
                counts["evidence_attempt_mismatch"] += 1
                continue
            try:
                packet = json.loads(row["packet_json"])
                answer = json.loads(row["answer_json"])
                if packet.get("exercise_type") != row["exercise_type"]:
                    raise NotShareable("exercise_type_mismatch")
                record = create_record(packet, answer, row["evidence_source"])
            except (ValueError, KeyError, TypeError, NotShareable) as exc:
                counts[str(exc) if isinstance(exc, NotShareable) else "malformed_local_data"] += 1
                continue
            records[record["record_fingerprint"]] = record
            counts["eligible"] += 1
    envelope = {
        "schema_version": PROTOCOL_VERSION,
        "platform": PLATFORM,
        "privacy": "hashed_metadata_preview",
        "network_upload": False,
        "records": [records[k] for k in sorted(records)],
    }
    validate_envelope(envelope)
    return envelope, dict(sorted(counts.items()))


def export_local_preview(database_path, destination, *, confirm_review=False):
    """Export explicite : seulement sur disque et seulement après revue consentie."""
    if not confirm_review:
        raise PermissionError("Confirmation explicite requise : --confirm-review")
    envelope, counts = build_preview(database_path)
    dest = Path(destination).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(f"Export existant, aucun écrasement automatique : {dest}")
    text = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with dest.open("x", encoding="utf-8") as f:
        f.write(text)
    return dest, counts
