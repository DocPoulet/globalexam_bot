"""Tests pure Python, sans Playwright, sans réseau, sans GlobalExam."""
import json
import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path

from correction_quality import assess, labelled_choice, structurally_valid
from correction_learner import CorrectionLearner


PACKET = {
    "schema_version": "1.0",
    "question_id": "question-exemple-1",
    "exercise_type": "qcm_single",
    "adapter": "qcm",
    "instruction": "Pick the correct answer",
    "context": "An example",
    "choices": [
        {"index": 0, "text": "Bike", "value": "a", "selected": False},
        {"index": 1, "text": "Bicycle", "value": "b", "selected": False},
        {"index": 2, "text": "Car", "value": "c", "selected": False},
    ],
    "source_text": "Pick the correct answer\nBike\nBicycle\nCar",
    "url": "https://general.global-exam.com/activity/1/content/2",
}


class FakeLocator:
    def __init__(self, value=None):
        self.value = value
    def count(self):
        return int(self.value is not None)
    @property
    def first(self):
        return self
    def inner_text(self, **kwargs):
        return self.value or ""


class FakePage:
    def __init__(self, text):
        self.url = "https://general.global-exam.com/activity/1/content/2/correction"
        self.text = text
        self.frames = [self]
    def locator(self, selector):
        return FakeLocator(self.text if selector == "main" else None)


class QualityTests(unittest.TestCase):
    def test_exact_labeled_answer(self):
        answer = labelled_choice(PACKET, "Correction\nLa bonne réponse est : Bicycle\nExplication")
        self.assertEqual(answer['indices'], [1])
        self.assertEqual(assess(PACKET, answer, 'labelled_correct_answer')[0], 'verified')

    def test_generic_text_is_not_proof(self):
        self.assertIsNone(labelled_choice(PACKET, "Vos réponses\nBike\nBicycle\nCar"))
        answer = {"kind": "choice_indices", "indices": [1]}
        self.assertEqual(assess(PACKET, answer, 'correction_text_delta')[0], 'provisional')

    def test_malformed_answers_rejected(self):
        self.assertFalse(structurally_valid(PACKET, {"kind": "choice_indices", "indices": [0, 1]}))
        self.assertFalse(structurally_valid(PACKET, {"kind": "choice_indices", "indices": [99]}))
        self.assertFalse(structurally_valid(PACKET, {"kind": "choice_indices", "indices": [True]}))

    def test_ambiguous_single_marker_never_learns(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            result = learner._map_correct_answer(PACKET, [{"text": "Bike"}, {"text": "Bicycle"}])
            self.assertIsNone(result)

    def test_strict_explicit_label_saves_verified_answer(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory, logging.getLogger('test'))
            answer = learner.record_explicit_correction(
                FakePage("Vos réponses\nCorrection\nLa bonne réponse est : Bicycle"),
                PACKET, PACKET, standalone=True,
            )
            self.assertTrue(answer['learned'])
            self.assertEqual(answer['verification_status'], 'verified')
            self.assertEqual(learner.lookup(PACKET['question_id'])['answer']['indices'], [1])
            self.assertEqual(learner.stats()['verified_answers'], 1)

    def test_unlabeled_delta_is_only_suggestion(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            result = learner.record_explicit_correction(
                FakePage(PACKET['source_text'] + '\nBicycle\nExplication'),
                PACKET, PACKET, standalone=True,
            )
            # Duplicated choice text does not become an added line: no fabricated memory.
            self.assertFalse(result['learned'])
            self.assertIsNone(learner.lookup(PACKET['question_id']))

    def test_ordering_dom_never_trusted_as_correction(self):
        packet = {'exercise_type':'ordering', 'ordering': {
            'available': [{'id':'a', 'text':'One'}, {'id':'b', 'text':'Two'}],
            'already_placed': []}}
        answer = {'kind':'ordering','items':[{'id':'b','text':'Two'}, {'id':'a','text':'One'}]}
        self.assertEqual(assess(packet, answer, 'ordering_corrected_dom')[0], 'provisional')

    def test_weak_dom_marker_is_provisional(self):
        answer = {"kind": "choice_indices", "indices": [1]}
        self.assertEqual(assess(PACKET, answer, 'dom_class_only')[0], 'provisional')

    def test_unlabelled_delta_stored_as_suggestion_if_unambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            # Le DOM d'une vraie question peut déplacer des lignes ; même si
            # une option n'apparaît qu'après le clic, ce n'est PAS une preuve.
            answered = dict(PACKET, source_text='Pick the correct answer\nBike\nCar')
            page = FakePage('Pick the correct answer\nBike\nCar\nBicycle')
            result = learner.record_explicit_correction(
                page, PACKET, answered, standalone=True,
            )
            self.assertEqual(result['verification_status'], 'provisional')
            self.assertFalse(result['learned'])
            self.assertEqual(learner.stats()['provisional_suggestions'], 1)
            self.assertEqual(learner.stats()['learned_answers'], 0)

    def test_conflicting_verified_corrections_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            first = learner.record_explicit_correction(
                FakePage('Correction\nLa bonne réponse est : Bicycle'),
                PACKET, PACKET, standalone=True,
            )
            self.assertTrue(first['learned'])
            second = learner.record_explicit_correction(
                FakePage('Correction\nLa bonne réponse est : Bike'),
                PACKET, PACKET, standalone=True,
            )
            self.assertFalse(second['learned'])
            self.assertEqual(second['verification_status'], 'disputed')
            self.assertEqual(learner.stats()['disputed_answers'], 1)
            # Une réponse litigieuse n'est plus rejouée automatiquement.
            self.assertIsNone(learner.lookup(PACKET['question_id']))
            with learner._connect() as conn:
                self.assertEqual(conn.execute(
                    'SELECT COUNT(*) FROM correction_conflicts'
                ).fetchone()[0], 1)

    def test_same_answer_from_different_metadata_is_not_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            first = learner.record_explicit_correction(
                FakePage('La bonne réponse est : Bicycle'),
                PACKET, PACKET, standalone=True,
            )
            self.assertTrue(first['learned'])
            with learner._connect() as conn:
                accepted, status = learner._store_verified_candidate(
                    conn, PACKET['question_id'],
                    {'kind': 'choice_indices', 'indices': [1]},
                    first['attempt_id'], 'dom_correct_markers',
                )
            self.assertTrue(accepted)
            self.assertEqual(status, 'verified')
            self.assertEqual(learner.stats()['disputed_answers'], 0)

    def test_existing_learned_answers_survive_as_legacy(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            with learner._connect() as db:
                db.execute("""INSERT INTO questions(
                    question_id,exercise_type,adapter,instruction,context,packet_json,
                    first_seen_at,last_seen_at,times_seen)
                    VALUES ('old','qcm_single','qcm','i','c','{}','d','d',1)""")
                db.execute("""INSERT INTO learned_answers(
                    question_id,answer_json,source_attempt_id,learned_at,confidence)
                    VALUES ('old','{\"kind\":\"choice_indices\",\"indices\":[0]}',NULL,'d',0.95)""")
            reopened = CorrectionLearner(directory)
            self.assertEqual(reopened.stats()['legacy_unverified'], 1)
            self.assertEqual(reopened.stats()['verified_answers'], 0)
            self.assertEqual(reopened.lookup('old')['verification_status'], 'legacy_unverified')
            self.assertEqual(reopened.lookup('old')['answer']['indices'], [0])

    def test_missing_route_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            learner = CorrectionLearner(directory)
            page = FakePage('La bonne réponse est : Bicycle')
            page.url = 'https://general.global-exam.com/levels/content'
            with self.assertRaises(RuntimeError):
                learner.record_explicit_correction(page, PACKET, PACKET, standalone=True)
            self.assertEqual(learner.stats()['attempts'], 0)


if __name__ == '__main__':
    unittest.main()
