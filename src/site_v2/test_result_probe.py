"""Tests offline : Playwright sur HTML synthétique, sans URL réseau."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from site_v2.result_probe import result_overview, capture_result_review, replay_capture, ResultReviewStore

HTML = '''<!doctype html><html><head><title>Correction</title></head><body>
<header>Anglais General</header><main>
<h2>Ne vous découragez pas !</h2><p>Votre score 2 / 10</p>
<h2>Protect And Serve</h2>
<button class="bg-error-800" onclick="selectQ(1)">1</button>
<button class="border-success-400" onclick="selectQ(2)">2</button>
<button onclick="selectTab('Vos réponses')">Vos réponses</button>
<button onclick="selectTab('Correction')">Correction</button>
<button onclick="selectTab('Explication')">Explication</button>
<section id="panel"></section>
<button onclick="window.replayed=true; document.getElementById('panel').innerHTML='Exercice démarré'">Rejouer l'activité</button>
<button onclick="window.didProgress=true">Passer à la suite</button>
<button aria-label="Ouvrir le formulaire de retour" onclick="window.feedback=true">Retour</button>
</main><script>
let currentQ=1;
function selectQ(q){currentQ=q; selectTab('Vos réponses')}
function selectTab(t){document.getElementById('panel').textContent='Question '+currentQ+' | '+t+' | '+
(t==='Correction'?'Bonne réponse '+currentQ:t==='Explication'?'Pourquoi '+currentQ:'Réponse personnelle '+currentQ)}
selectTab('Vos réponses');
</script></body></html>'''

class Proxy:
    def __init__(self, page, mode='result'):
        self.page=page
        self.mode=mode

    @property
    def url(self):
        if self.mode == 'exercise' or self.page.evaluate('window.replayed === true'):
            return 'https://general.global-exam.com/activity/123/content/456'
        return 'https://general.global-exam.com/activity/123/result'

    def __getattr__(self, name):
        return getattr(self.page,name)

class Context:
    def __init__(self, page):
        self.pages=[page]

class ResultProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver=sync_playwright().start()
        try:
            cls.browser=cls.driver.chromium.launch(headless=True)
        except Exception:
            cls.browser=cls.driver.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()

    def setUp(self):
        self.patches=[patch('site_v2.snapshot.is_globalexam_host',return_value=True)]
        for p in self.patches:p.start()
        self.ctx=self.browser.new_context()
        self.real=self.ctx.new_page()
        self.real.set_content(HTML)
        self.page=Proxy(self.real)
        self.context=Context(self.page)
        self.tmp=tempfile.TemporaryDirectory()

    def tearDown(self):
        self.ctx.close()
        for p in self.patches:p.stop()
        self.tmp.cleanup()

    def test_detects_score_and_indicators(self):
        data=result_overview(self.page)
        self.assertTrue(data['ok'])
        self.assertEqual(data['score'],{'earned':2,'total':10})
        self.assertEqual(data['questions'],[
            {'number':1,'indicator':'incorrect'},
            {'number':2,'indicator':'correct'}])
        self.assertEqual(len(data['tabs']),3)

    def test_review_saves_tabs_without_progressing(self):
        db=Path(self.tmp.name)/'data'/'knowledge.sqlite3'
        saved=capture_result_review(self.page,self.tmp.name,db_path=db)
        self.assertTrue(saved['ok'])
        self.assertEqual(saved['questions_inspected'],2)
        self.assertEqual(saved['database_saved'],2)
        self.assertTrue(saved['archive'].exists())
        self.assertEqual(ResultReviewStore(db).count(),2)
        with sqlite3.connect(db) as con:
            rows=con.execute('SELECT question_number,correction_text FROM result_reviews ORDER BY question_number').fetchall()
            self.assertIn('Bonne réponse 1',rows[0][1])
            self.assertIn('Bonne réponse 2',rows[1][1])
            tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('learned_answers',tables)
        self.assertFalse(self.real.evaluate('window.didProgress === true'))
        self.assertFalse(self.real.evaluate('window.feedback === true'))

    def test_current_first_question_needs_no_click(self):
        from unittest.mock import patch as mock_patch
        from site_v2.result_probe import _selected_question_number
        self.assertEqual(_selected_question_number(self.page),1)
        # Cas observé : bouton n°1 non cliquable, mais contenu déjà actif.
        from site_v2.result_probe import safe_click as underlying
        def click_except_first(el, *args, **kwargs):
            if (el.inner_text() or "").strip() == "1":
                return False
            return underlying(el, *args, **kwargs)
        with mock_patch('site_v2.result_probe.safe_click',side_effect=click_except_first):
            review=capture_result_review(self.page,self.tmp.name)
        self.assertEqual(review['questions_inspected'],2)
        self.assertEqual(review['questions'][0]['errors'],[])
        self.assertIn('Correction',review['questions'][0]['tabs'])

    def test_replay_confirms_real_exercise(self):
        result=replay_capture(self.page,self.context,self.tmp.name,wait_ms=600)
        self.assertTrue(result['clicked'])
        self.assertTrue(result['ok'])
        self.assertIn('/content/456',result['after_route'])
        self.assertEqual(result['screen_kind'],'exercise')
        self.assertTrue(result['archive'].exists())

    def test_duplicate_replay_first_inert_second_navigates(self):
        # La vraie capture contient deux boutons Rejouer avec le même label.
        # Le premier peut réussir click() sans ouvrir l'exercice.
        self.real.locator("button").filter(has_text="Rejouer l'activité").first.evaluate(
            """el => { const btn = document.createElement('button'); btn.id='inert-replay'; btn.textContent="Rejouer l'activité"; el.before(btn); }"""
        )
        trace = replay_capture(self.page, self.context, self.tmp.name, wait_ms=800)
        self.assertTrue(trace['clicked'])
        self.assertTrue(trace['ok'])
        self.assertGreaterEqual(trace['candidate_count'], 2)
        self.assertEqual(len(trace['click_attempts']), 2)
        self.assertEqual(trace['click_attempts'][0]['result'], 'no_navigation_or_visible_change')
        self.assertIn('/content/456', trace['after_route'])

    def test_replay_failed_click_exports_trace(self):
        with patch('site_v2.result_probe.safe_click', return_value=False):
            trace = replay_capture(self.page, self.context, self.tmp.name, wait_ms=250)
        self.assertFalse(trace['clicked'])
        self.assertEqual(trace['reason'], 'replay_button_click_failed')
        self.assertGreaterEqual(trace['candidate_count'], 1)
        self.assertTrue(trace['archive'].exists())
        self.assertTrue((trace['directory'] / 'replay_trace.json').exists())

    def test_preexisting_exercise_tab_is_not_a_replay_success(self):
        # L'ancien replay regardait tous les onglets et pouvait déclarer
        # succès à cause d'un exercice déjà ouvert ailleurs.
        stale = Proxy(self.real, mode='exercise')
        self.context.pages = [self.page, stale]
        with patch('site_v2.result_probe.safe_click', return_value=True):
            trace = replay_capture(self.page, self.context, self.tmp.name, wait_ms=250)
        self.assertTrue(trace['clicked'])
        self.assertFalse(trace['ok'])

    def test_manually_opened_result_in_another_tab(self):
        from site_v2.guided import _result_page_in_context
        previous = Proxy(self.real, mode='exercise')
        current = self.page
        # En v0.10.9 une URL /content n'est plus traitée comme /result,
        # même si l'interface HTML est identique.
        selected = _result_page_in_context(previous, Context(previous))
        self.assertIsNone(selected)
        ctx = Context(previous)
        ctx.pages = [previous, current]
        self.assertIs(_result_page_in_context(previous, ctx), current)

    def test_no_replay_outside_result(self):
        proxy=Proxy(self.real,mode='exercise')
        result=replay_capture(proxy,Context(proxy),self.tmp.name)
        self.assertFalse(result['clicked'])

if __name__=='__main__': unittest.main()
