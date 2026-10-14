"""Tests offline du raccord catalogue V2 -> ancien AutoPilot."""
import logging
import unittest
from unittest.mock import patch

from site_v2.autopilot_catalog import NewCatalogLauncher


class FakePage:
    def __init__(self, url="https://general.global-exam.com/levels/content"):
        self.url = url
        self.wait_calls = 0

    def wait_for_timeout(self, _ms):
        self.wait_calls += 1


class NewCatalogLauncherTests(unittest.TestCase):
    def setUp(self):
        self.page = FakePage()
        self.bot = NewCatalogLauncher(self.page, logging.getLogger("test"))
        self.modules = [
            {"number": 1, "title": "MODULE 1", "expanded": False},
            {"number": 5, "title": "MODULE 5", "expanded": True},
        ]
        self.cards = {
            5: [
                {"index": 1, "title": "Terminé", "state": "completed"},
                {"index": 2, "title": "En cours", "state": "in_progress"},
                {"index": 3, "title": "Dialogue", "state": "special"},
                {"index": 4, "title": "Verrouillé", "state": "locked"},
            ],
            1: [{"index": 1, "title": "Autre en cours", "state": "in_progress"}],
        }
        self.patches = [
            patch("site_v2.autopilot_catalog.module_list", side_effect=lambda _p: self.modules),
            patch("site_v2.autopilot_catalog.ensure_module_open", return_value=True),
            patch("site_v2.autopilot_catalog.list_activities", side_effect=lambda _p, m: {
                "ok": True, "activities": self.cards.get(m, []),
            }),
        ]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])

    def test_catalog_url_without_trailing_slash(self):
        self.assertTrue(self.bot.is_list_page())
        self.page.url = "https://general.global-exam.com/levels/content/"
        self.assertTrue(self.bot.is_list_page())

    def test_opens_in_progress_first(self):
        clicks = []

        def open_card(page, module, index):
            clicks.append((module, index))
            page.url = "https://general.global-exam.com/activity/42/content/7"
            return {"ok": True}

        with patch("site_v2.autopilot_catalog.open_completed_activity", side_effect=open_card):
            self.assertTrue(self.bot.launch_first_available())
        self.assertEqual(clicks, [(5, 2)])
        self.assertFalse(self.bot.is_list_page())

    def test_no_repeated_completed_or_visited_activity(self):
        clicks = []

        def open_card(page, module, index):
            clicks.append((module, index))
            page.url = "https://general.global-exam.com/activity/42/content/7"
            return {"ok": True}

        with patch("site_v2.autopilot_catalog.open_completed_activity", side_effect=open_card):
            self.assertTrue(self.bot.launch_first_available())
            self.page.url = "https://general.global-exam.com/levels/content"
            self.assertTrue(self.bot.launch_first_available())
            self.page.url = "https://general.global-exam.com/levels/content"
            self.assertFalse(self.bot.launch_first_available())
        self.assertEqual(clicks, [(5, 2), (1, 1)])

    def test_click_without_navigation_is_not_success(self):
        self.cards[1] = []
        with patch("site_v2.autopilot_catalog.open_completed_activity", return_value={"ok": True}) as opener:
            self.assertFalse(self.bot.launch_first_available())
            self.assertFalse(self.bot.launch_first_available())
        self.assertEqual(opener.call_count, 1)

    def test_completed_opt_in_only(self):
        self.cards[1] = []
        self.cards[5] = [{"index": 1, "title": "Terminé", "state": "completed"}]
        with patch("site_v2.autopilot_catalog.open_completed_activity", return_value={"ok": True}) as opener:
            self.assertFalse(self.bot.launch_first_available())
        opener.assert_not_called()

    def test_result_url_not_catalog(self):
        self.page.url = "https://general.global-exam.com/activity/42/result"
        self.assertFalse(self.bot.is_list_page())
        self.assertTrue(self.bot.launch_first_available())


if __name__ == "__main__":
    unittest.main()
