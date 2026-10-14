"""Tests hors ligne : stabilité, filtres SQLite, minimisation et aucun upload."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from community_protocol import (
    NotShareable, create_record, validate_record, validate_envelope,
)
from community_preview import build_preview, export_local_preview
from correction_learner import CorrectionLearner


class ProtocolTests(unittest.TestCase):
    def packet(self):
        return {
            "question_id": "old-local-id",
            "exercise_type": "qcm_single",
            "html_language": "fr",
            "instruction": "Choisissez une réponse",
            "context": "What did the sailor see?",
            "url": "https://private.example/session?token=VERY_SECRET",
            "choices": [
                {"index": 0, "text": "A lighthouse", "selected": False},
                {"index": 1, "text": "A train", "selected": False},
                {"index": 2, "text": "A bicycle", "selected": False},
            ],
        }

    def answer(self):
        return {"kind": "choice_indices", "indices": [2], "choices": []}

    def test_question_fingerprint_independent_of_choice_order_and_index(self):
        packet1 = self.packet()
        packet2 = self.packet()
        packet2["choices"] = [
            {"index": 0, "text": "A bicycle"},
            {"index": 1, "text": "A lighthouse"},
            {"index": 2, "text": "A train"},
        ]
        record1 = create_record(packet1, self.answer(), "dom_correct_markers")
        record2 = create_record(packet2, {"kind": "choice_indices", "indices": [0]}, "dom_correct_markers")
        self.assertEqual(record1, record2)
        self.assertTrue(validate_record(record1))

    def test_reject_different_context_and_answer(self):
        p = self.packet()
        r = create_record(p, self.answer(), "dom_correct_markers")
        p["context"] = "What did the sailor eat?"
        self.assertNotEqual(r["question_fingerprint"], create_record(p, self.answer(), "dom_correct_markers")["question_fingerprint"])
        p = self.packet()
        other = create_record(p, {"kind": "choice_indices", "indices": [0]}, "dom_correct_markers")
        self.assertEqual(r["question_fingerprint"], other["question_fingerprint"])
        self.assertNotEqual(r["record_fingerprint"], other["record_fingerprint"])

    def test_no_raw_text_or_private_data_in_record(self):
        r = create_record(self.packet(), self.answer(), "dom_correct_markers")
        text = json.dumps(r)
        for private in ("private.example", "VERY_SECRET", "sailor", "bicycle", "Choisissez", "old-local-id"):
            self.assertNotIn(private, text)

    def test_duplicate_choice_labels_rejected(self):
        packet = self.packet()
        packet["choices"][1]["text"] = "A bicycle"
        with self.assertRaises(NotShareable):
            create_record(packet, self.answer(), "dom_correct_markers")

    def test_sensitive_question_blocked(self):
        p = self.packet()
        p["context"] = "Email alice@example.com about this"
        with self.assertRaisesRegex(NotShareable, "personal"):
            create_record(p, self.answer(), "dom_correct_markers")

    def test_unverified_source_and_text_input_rejected(self):
        with self.assertRaises(NotShareable):
            create_record(self.packet(), self.answer(), "correction_text_delta")
        p = self.packet()
        p["exercise_type"] = "text_input"
        with self.assertRaises(NotShareable):
            create_record(p, {"kind": "text_fields", "fields": []}, "dom_correct_markers")

    def test_validate_catches_tampering_and_extra_fields(self):
        r = create_record(self.packet(), self.answer(), "dom_correct_markers")
        r["answer"]["values"] = ["sha256:" + "0" * 64]
        with self.assertRaisesRegex(ValueError, "mismatch"):
            validate_record(r)
        r["cookie"] = "my-cookie"
        with self.assertRaisesRegex(ValueError, "unexpected_record_fields"):
            validate_record(r)

    def test_select_allows_repeated_correct_labels_across_fields(self):
        packet = {
            "exercise_type": "select", "instruction": "Complétez les phrases", "context": "Examples",
            "fields": [
                {"index": i, "options": [{"index": 0, "text": "Yes"}, {"index": 1, "text": "No"}]}
                for i in range(2)
            ],
        }
        answer = {
            "kind": "select_options",
            "fields": [{"field_index": i, "selected_option_indices": [0]} for i in range(2)],
        }
        record = create_record(packet, answer, "dom_correct_markers")
        self.assertEqual(len(record["answer"]["values"]), 2)
        self.assertEqual(record["answer"]["values"][0], record["answer"]["values"][1])
        self.assertTrue(validate_record(record))

    def test_ordering_preserves_solution_order_and_ignores_available_order(self):
        p = {
            "exercise_type": "ordering", "instruction": "Mettez dans l'ordre", "context": "Days",
            "ordering": {"available": [{"id": "a", "text": "Monday"},
                                       {"id": "b", "text": "Tuesday"},
                                       {"id": "c", "text": "Wednesday"}], "already_placed": []},
        }
        a = {"kind": "ordering", "items": [p["ordering"]["available"][i] for i in (0, 1, 2)]}
        r = create_record(p, a, "dom_correct_markers")
        p["ordering"]["available"].reverse()
        same = create_record(p, a, "dom_correct_markers")
        self.assertEqual(r, same)
        reverse = create_record(p, {"kind": "ordering", "items": list(reversed(a["items"]))}, "dom_correct_markers")
        self.assertNotEqual(r["record_fingerprint"], reverse["record_fingerprint"])


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.db = CorrectionLearner(self.base).db_path
        self.packet = ProtocolTests().packet()
        self.answer = ProtocolTests().answer()

    def add(self, qid, status="verified", evidence="dom_correct_markers", answer=None, packet=None, mismatch=False):
        packet = dict(packet or self.packet)
        packet["question_id"] = qid
        answer = self.answer if answer is None else answer
        with sqlite3.connect(self.db) as db:
            db.execute("INSERT INTO questions(question_id, exercise_type, packet_json,first_seen_at,last_seen_at,times_seen) VALUES (?,?,?,?,?,?)",
                       (qid, packet["exercise_type"], json.dumps(packet), "2026-01-01", "2026-01-01", 1))
            cur = db.execute("INSERT INTO attempts(question_id,created_at,finish_action,outcome) VALUES (?,?,?,?)",
                             (qid, "2026-01-01", "validate", "correct"))
            attempt_id = cur.lastrowid
            db.execute("INSERT INTO learned_answers(question_id,answer_json,source_attempt_id,learned_at,confidence) VALUES (?,?,?,?,?)",
                       (qid, json.dumps(answer), attempt_id, "2026-01-01", 1.0))
            db.execute("INSERT INTO answer_verifications(question_id,attempt_id,status,evidence_source,verified_at) VALUES (?,?,?,?,?)",
                       (qid, 9999 if mismatch else attempt_id, status, evidence, "2026-01-01"))

    def test_only_verified_matching_sources_exported(self):
        self.add("verified")
        self.add("legacy", status="legacy_unverified")
        self.add("disputed", status="disputed")
        self.add("weak", evidence="text_verdict_correct")
        self.add("mismatch", mismatch=True)
        env, stats = build_preview(self.db)
        self.assertEqual(len(env["records"]), 1)
        self.assertEqual(stats["eligible"], 1)
        self.assertEqual(stats["legacy_unverified"], 1)
        self.assertEqual(stats["disputed"], 1)
        self.assertEqual(stats["untrusted_evidence"], 1)
        self.assertEqual(stats["evidence_attempt_mismatch"], 1)
        self.assertTrue(validate_envelope(env))
        serialized = json.dumps(env)
        self.assertNotIn("old-local-id", serialized)
        self.assertNotIn("bicycle", serialized.lower())
        self.assertNotIn("private.example", serialized)

    def test_export_requires_explicit_acknowledgement_and_no_overwrite(self):
        self.add("verified")
        dest = self.base / "preview.json"
        with self.assertRaises(PermissionError):
            export_local_preview(self.db, dest)
        self.assertFalse(dest.exists())
        result, _ = export_local_preview(self.db, dest, confirm_review=True)
        self.assertEqual(result, dest)
        self.assertTrue(validate_envelope(json.loads(dest.read_text(encoding="utf8"))))
        with self.assertRaises(FileExistsError):
            export_local_preview(self.db, dest, confirm_review=True)

    def test_database_is_not_written_during_preview(self):
        self.add("verified")
        with sqlite3.connect(self.db) as db:
            before = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        build_preview(self.db)
        with sqlite3.connect(self.db) as db:
            after = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
        self.assertEqual(before, after)

    def test_missing_db_rejected_no_new_db_created(self):
        db = self.base / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            build_preview(db)
        self.assertFalse(db.exists())


if __name__ == "__main__":
    unittest.main()
