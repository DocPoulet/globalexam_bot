"""Tests hors-ligne du catalogue v2, sans connexion à GlobalExam."""
import unittest
from pathlib import Path
from unittest.mock import patch
from playwright.sync_api import sync_playwright
from site_v2.catalog import list_activities, ensure_module_open, open_completed_activity

HTML = """<!doctype html><html><body>
<div>
  <button aria-expanded="false">MODULE 4 Ancien module</button>
  <div class="grid grid-rows-[0fr]" style="display:none"></div>
</div>
<div>
  <button id="header-5" aria-expanded="true" onclick="this.setAttribute('aria-expanded','true')">MODULE 5 Nom du module · 5 / 12 activités</button>
  <div class="grid transition-all grid-rows-[1fr] visible">
    <div class="relative cursor-pointer" onclick="window.clicked='Protect And Serve'">
      <div><span>Terminée</span><span>Voir</span><p class="text-pretty">Protect And Serve</p></div>
    </div>
    <div class="relative cursor-pointer" onclick="window.clicked='In Your Honor'">
      <div><span>Terminée</span><span>Voir</span><p class="text-pretty">In Your Honor</p></div>
    </div>
    <button>Palier À PASSER</button>
    <div class="relative cursor-default"><div>À débloquer<p class="text-pretty">Real World Calling</p></div></div>
    <div class="relative cursor-pointer" onclick="window.clicked='conversation'">
      <div><p class="text-pretty">Racontez les rebondissements de votre séjour</p><span>Lancer</span></div>
    </div>
    <button>Validation du module TEST DU MODULE</button>
  </div>
</div>
<div>
  <button aria-expanded="true">MODULE 13 Autre module</button>
  <div class="grid grid-rows-[1fr] visible">
    <div class="relative cursor-pointer"><div>Terminée Voir<p class="text-pretty">Autre activité</p></div></div>
  </div>
</div>
<button aria-label="Ouvrir le formulaire de retour" onclick="window.feedback=true">feedback</button>
</body></html>"""


class CatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._driver = sync_playwright().start()
        try:
            cls.browser = cls._driver.chromium.launch(headless=True)
        except Exception:
            linux_chromium = Path("/usr/bin/chromium")
            if not linux_chromium.exists():
                cls._driver.stop()
                raise unittest.SkipTest("Chromium Playwright indisponible")
            cls.browser = cls._driver.chromium.launch(
                headless=True, executable_path=str(linux_chromium),
                args=["--no-sandbox"],
            )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._driver.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content(HTML)
        # Site entièrement simulé, aucun accès à GlobalExam pendant les tests.
        self.host_patch = patch('site_v2.catalog.is_globalexam_host', return_value=True)
        self.host_patch.start()

    def tearDown(self):
        self.host_patch.stop()
        self.page.close()

    def test_read_module_and_states(self):
        result = list_activities(self.page, 5)
        self.assertTrue(result['ok'])
        self.assertEqual([item['state'] for item in result['activities']],
                         ['completed', 'completed', 'locked', 'special'])
        self.assertEqual(result['activities'][0]['title'], 'Protect And Serve')

    def test_open_completed_only(self):
        self.assertTrue(open_completed_activity(self.page, 5, 1)['ok'])
        self.assertEqual(self.page.evaluate('window.clicked'), 'Protect And Serve')
        self.assertFalse(open_completed_activity(self.page, 5, 3)['ok'])
        self.assertFalse(open_completed_activity(self.page, 5, 4)['ok'])
        self.assertEqual(self.page.evaluate('window.clicked'), 'Protect And Serve')
        self.assertIsNone(self.page.evaluate('window.feedback'))

    def test_in_progress_continue_is_an_ordinary_activity(self):
        # Diagnostic réel du 14/10 : la carte #1 n'est plus Terminée/Voir.
        html = HTML.replace(
            '<span>Terminée</span><span>Voir</span><p class="text-pretty">Protect And Serve</p>',
            '<span>En cours · 0/14</span><span>Continuer</span><p class="text-pretty">Protect And Serve</p>',
        )
        self.page.set_content(html)
        listed = list_activities(self.page, 5)
        self.assertEqual(listed['activities'][0]['state'], 'in_progress')
        self.assertTrue(open_completed_activity(self.page, 5, 1)['ok'])
        self.assertEqual(self.page.evaluate('window.clicked'), 'Protect And Serve')
        self.assertFalse(open_completed_activity(self.page, 5, 3)['ok'])
        self.assertFalse(open_completed_activity(self.page, 5, 4)['ok'])
        self.assertIsNone(self.page.evaluate('window.feedback'))

    def test_module_specific_scoping(self):
        self.assertEqual(len(list_activities(self.page, 5)['activities']), 4)
        self.assertEqual(len(list_activities(self.page, 13)['activities']), 1)
        self.assertFalse(list_activities(self.page, 4)['ok'])
        self.assertTrue(ensure_module_open(self.page, 5))


if __name__ == '__main__':
    unittest.main()
