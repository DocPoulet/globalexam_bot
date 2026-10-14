"""Tests hors-ligne de la capture après ouverture d'une carte terminée."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright
from site_v2.activity_probe import open_capture_completed, _activity_evidence
from site_v2.catalog import module_list

HTML = """<!doctype html><html><body>
<div><button aria-expanded="true">MODULE 5 Test · 5 / 12 activités</button>
  <div class="grid grid-rows-[1fr] visible">
    <div class="relative cursor-pointer" onclick="document.body.innerHTML='<h1>Activity opened</h1><input type=radio><button>Valider</button>'">
      <span>Terminée</span><span>Voir</span><p class="text-pretty">Protect And Serve</p>
    </div>
    <div class="relative cursor-default" onclick="window.locked=true">
      <span>À débloquer</span><p class="text-pretty">Real World Calling</p>
    </div>
    <div class="relative cursor-pointer" onclick="window.special=true">
      <p class="text-pretty">Conversation IA</p><span>Lancer</span>
    </div>
  </div>
</div>
<div><button aria-expanded="true">MODULE 13 Autre</button>
  <div class="grid grid-rows-[1fr] visible"><div class="relative cursor-pointer"><span>Terminée</span><span>Voir</span><p class="text-pretty">Other</p></div></div>
</div>
</body></html>"""


class ActivityProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._driver = sync_playwright().start()
        try:
            cls.browser = cls._driver.chromium.launch(headless=True)
        except Exception:
            chromium = Path('/usr/bin/chromium')
            if not chromium.exists():
                cls._driver.stop()
                raise unittest.SkipTest('Chromium non disponible')
            cls.browser = cls._driver.chromium.launch(
                executable_path=str(chromium), headless=True, args=['--no-sandbox']
            )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._driver.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.page.set_content(HTML)
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [
            patch('site_v2.catalog.is_globalexam_host', return_value=True),
            patch('site_v2.snapshot.is_globalexam_host', return_value=True),
            # Le test charge son HTML via set_content (URL about:blank).
            patch('site_v2.activity_probe._is_catalog', side_effect=lambda page: bool(module_list(page))),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.temp.cleanup()
        self.context.close()

    def test_success_auto_export(self):
        trace = open_capture_completed(self.page, self.context, 5, 1, self.temp.name)
        self.assertTrue(trace['action']['ok'])
        self.assertTrue(trace['action']['clicked'])
        self.assertEqual(trace['activity_evidence'], 'question_controls')
        self.assertTrue(trace['visible_structure_changed'])
        self.assertFalse(trace['new_tab'])
        self.assertEqual(trace['action']['title'], 'Protect And Serve')
        self.assertTrue(trace['archive'].exists())
        with zipfile.ZipFile(trace['archive']) as z:
            self.assertIn('navigation_trace.json', z.namelist())
            self.assertIn('structure.json', z.namelist())
            stored = json.loads(z.read('navigation_trace.json'))
            self.assertTrue(stored['visible_structure_changed'])
            self.assertTrue(stored['action']['ok'])
            self.assertEqual(stored['schema'], 'globalexam_activity_open_trace_v2')
            self.assertNotIn('cookie', stored)

    def test_authentication_gate_prevents_click(self):
        with patch('site_v2.activity_probe._is_login', return_value=True), \
             patch('site_v2.activity_probe._is_catalog', return_value=False):
            trace = open_capture_completed(
                self.page, self.context, 5, 1, self.temp.name, ready_ms=200
            )
        self.assertFalse(trace["action"]["ok"])
        self.assertFalse(trace["action"]["clicked"])
        self.assertEqual(trace["action"]["reason"], "connexion_requise")

    def test_activity_route_signal_and_catalog_rejection(self):
        class Dummy:
            def __init__(self, url):
                self.url = url
        self.assertEqual(
            _activity_evidence(Dummy("https://general.global-exam.com/activity/123/content/456")),
            "activity_route",
        )
        self.assertIsNone(
            _activity_evidence(Dummy("https://general.global-exam.com/levels/content"))
        )

    def test_locked_not_clicked(self):
        trace = open_capture_completed(self.page, self.context, 5, 2, self.temp.name)
        self.assertFalse(trace['action']['ok'])
        self.assertIn('etat_interdit', trace['action']['reason'])
        self.assertIsNone(self.page.evaluate('window.locked'))
        self.assertTrue(trace['archive'].exists())

    def test_special_not_clicked(self):
        trace = open_capture_completed(self.page, self.context, 5, 3, self.temp.name)
        self.assertFalse(trace['action']['ok'])
        self.assertIn('etat_interdit', trace['action']['reason'])
        self.assertIsNone(self.page.evaluate('window.special'))

    def test_module_13_scoping(self):
        trace = open_capture_completed(self.page, self.context, 13, 1, self.temp.name, wait_ms=400)
        self.assertFalse(trace['action']['ok'])
        self.assertTrue(trace['action']['clicked'])
        self.assertEqual(trace['action']['title'], 'Other')
        self.assertEqual(trace['action']['reason'], 'clic_sans_ouverture_confirmee')
        self.assertIsNone(trace['activity_evidence'])


if __name__ == '__main__':
    unittest.main()
