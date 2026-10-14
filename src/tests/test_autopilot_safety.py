"""Tests hors connexion des garde-fous V0.10.11."""
import json
import logging
import tempfile
import unittest
from unittest.mock import patch

from autopilot import AutoPilot
from autopilot_audit import AutoPilotAudit, QuestionRunGuard, safe_path


class FakePage:
    def __init__(self):
        self.url = 'https://general.global-exam.com/activity/42/content/7?token=secret'
    def wait_for_timeout(self, _ms):
        pass


class FakeFlow:
    def __init__(self):
        self.body = 'Question A'
    def _main_text(self):
        return self.body


class FakeQuestions:
    learner = None
    def __init__(self, flow):
        self.flow = flow
        self.calls = 0
        self.qid = 'question_A'
        self.changed = True
        self.fail = False
        self.marker = 'question'
    def wait_for_auto_marker_or_next(self, **kw):
        return self.marker
    def extract_packet(self):
        return {'question_id': self.qid, 'exercise_type': 'qcm_single'}
    def auto_answer_passer_exercise(self, advance=False):
        self.calls += 1
        if self.fail:
            raise RuntimeError('uncertain submission')
        if self.changed:
            self.flow.body = 'validated'
        return {'handled': True, 'action': 'llm', 'action_steps': 1,
                'finish_action': 'validate',
                'learning': {'outcome': 'unknown', 'attempt_id': 12, 'learned': False}}


class GuardAndAuditTests(unittest.TestCase):
    def test_guard_deduplicates_query_variants(self):
        guard = QuestionRunGuard()
        a = guard.key('https://example.org/a?key=X', 'id')
        b = guard.key('https://example.org/a?key=Y', 'id')
        c = guard.key('https://example.org/b', 'id')
        self.assertEqual(a, b)
        self.assertTrue(guard.begin(a))
        guard.finish(a)
        self.assertFalse(guard.begin(b))
        self.assertTrue(guard.begin(c))
    def test_trace_does_not_keep_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            audit = AutoPilotAudit(d, logging.getLogger('test'), 't')
            audit.emit('question_detected', question_id='abc', url='https://test/?secret=BAD', cookie='COOKIE')
            audit.emit('sqlite', question_id='abc', status='saved', attempt_id=4, learned=True)
            text = audit.path.read_text(encoding='utf-8')
            self.assertNotIn('BAD', text)
            self.assertNotIn('COOKIE', text)
            self.assertEqual(audit.summary()['learned'], 1)
            self.assertEqual(safe_path('https://host/a?secret=BAD'), '/a')


class AutoPilotTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.page = FakePage()
        self.flow = FakeFlow()
        self.questions = FakeQuestions(self.flow)
        self.bot = AutoPilot(self.page, logging.getLogger('test'), None, self.flow, self.questions)
        self.bot.audit = AutoPilotAudit(self.dir.name, logging.getLogger('test'), 'audit')
        self.bot._settle = lambda **kw: None
    def test_never_validates_same_question_twice(self):
        self.assertTrue(self.bot._handle_question())
        self.assertFalse(self.bot._handle_question())
        self.assertEqual(self.questions.calls, 1)
        events = [json.loads(x)['event'] for x in self.bot.audit.path.read_text().splitlines()]
        self.assertIn('duplicate_prevented', events)
        self.assertIn('sqlite', events)
    def test_unchanged_screen_blocks_even_if_id_changes(self):
        self.questions.changed = False
        self.assertFalse(self.bot._handle_question())
        self.questions.qid = 'feedback_modified_question_id'
        self.assertFalse(self.bot._handle_question())
        self.assertEqual(self.questions.calls, 1)
    def test_next_question_on_same_url_is_allowed(self):
        self.assertTrue(self.bot._handle_question())
        self.questions.qid = 'question_B'
        self.flow.body = 'Question B'
        self.assertTrue(self.bot._handle_question())
        self.assertEqual(self.questions.calls, 2)

    def test_exception_never_retries(self):
        self.questions.fail = True
        self.assertFalse(self.bot._handle_question())
        self.assertFalse(self.bot._handle_question())
        self.assertEqual(self.questions.calls, 1)
    def test_next_click_needs_change(self):
        self.questions.marker = 'next'
        with patch('autopilot.click_common_action', return_value=True):
            self.assertFalse(self.bot._handle_question())
        def navigate(*args):
            self.page.url = 'https://general.global-exam.com/activity/42/content/8'
            return True
        with patch('autopilot.click_common_action', side_effect=navigate):
            self.assertTrue(self.bot._handle_question())


if __name__ == '__main__':
    unittest.main()
