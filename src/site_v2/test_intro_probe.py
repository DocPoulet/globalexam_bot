"""Tests hors réseau : transition d'introduction et champs masqués."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from site_v2.intro_probe import advance_intro_and_capture, is_introduction

HTML = """<!doctype html><html><body>
<main><div>Protect And Serve 0 / 10</div><h2>Introduction</h2>
<p>Being a police officer is hard work.</p>
<button onclick="document.querySelector('main').innerHTML='<h2>Question 1</h2><p>What is correct?</p><input class=sr-only type=radio id=one name=test><label for=one>Correct answer</label><button>Valider</button>'">Suivant</button>
<button aria-label="Ouvrir le formulaire de retour" onclick="window.feedback=true">Feedback</button>
</main></body></html>"""

class Proxy:
    def __init__(self, page, url='https://general.global-exam.com/activity/11/content/44'):
        self.page = page
        self._url = url
    @property
    def url(self):
        return self._url
    def __getattr__(self, name):
        return getattr(self.page, name)

class IntroProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = sync_playwright().start()
        try:
            cls.browser = cls.driver.chromium.launch(headless=True)
        except Exception:
            cls.browser = cls.driver.chromium.launch(executable_path='/usr/bin/chromium', headless=True,args=['--no-sandbox'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.driver.stop()
    def setUp(self):
        self.ctx = self.browser.new_context()
        self.real = self.ctx.new_page()
        self.real.set_content(HTML)
        self.page = Proxy(self.real)
        self.temp = tempfile.TemporaryDirectory()
        self.patch1 = patch('site_v2.intro_probe.is_globalexam_host', return_value=True)
        self.patch2 = patch('site_v2.snapshot.is_globalexam_host', return_value=True)
        self.patch1.start()
        self.patch2.start()
    def tearDown(self):
        self.patch2.stop()
        self.patch1.stop()
        self.ctx.close()
        self.temp.cleanup()

    def test_next_intro_capture_and_hidden_radios(self):
        self.assertTrue(is_introduction(self.page))
        trace = advance_intro_and_capture(self.page, self.temp.name, wait_ms=800)
        self.assertTrue(trace['clicked'])
        self.assertTrue(trace['ok'])
        self.assertTrue(trace['has_answer_controls'])
        self.assertFalse(trace['still_introduction'])
        self.assertTrue(trace['archive'].exists())
        with zipfile.ZipFile(trace['archive']) as z:
            self.assertIn('question_detail.json',z.namelist())
            detail=json.loads(z.read('question_detail.json'))
            self.assertEqual(detail['fields'][0]['type'],'radio')
            self.assertEqual(detail['fields'][0]['label'],'Correct answer')
            self.assertEqual(detail['labels'][0]['text'],'Correct answer')
            self.assertNotIn('cookie', z.read('intro_transition_trace.json').decode())
        self.assertFalse(self.real.evaluate('window.feedback === true'))
    def test_refuse_when_question_already_open(self):
        self.real.locator('button',has_text='Suivant').click()
        self.assertFalse(is_introduction(self.page))
        trace=advance_intro_and_capture(self.page,self.temp.name)
        self.assertFalse(trace['clicked'])
        self.assertEqual(trace['reason'],'not_an_introduction')
    def test_refuse_other_site(self):
        self.patch1.stop()
        try:
            bad=Proxy(self.real,'https://example.com/activity/11/content/44')
            self.assertFalse(is_introduction(bad))
        finally:
            self.patch1.start()
    def test_refuse_next_disabled(self):
        self.real.locator('button',has_text='Suivant').evaluate('(e)=>e.setAttribute("disabled","")')
        trace=advance_intro_and_capture(self.page,self.temp.name)
        self.assertFalse(trace['clicked'])
        self.assertEqual(trace['reason'],'next_button_missing_or_disabled')

if __name__ == '__main__':
    unittest.main()
