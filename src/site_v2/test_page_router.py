"""Tests URL/onglets sans connexion réelle au site GlobalExam."""
import unittest
from site_v2.page_router import (
    kind_from_url, initial_page, needs_initial_navigation,
    page_for_kind, tab_inventory,
)
from site_v2.guided import _result_page_in_context
from site_v2.result_probe import is_result, result_overview


class FakePage:
    def __init__(self, url, *, focus=False, closed=False):
        self.url = url
        self.focus = focus
        self.closed = closed

    def is_closed(self):
        return self.closed

    def evaluate(self, expression):
        return self.focus

    def locator(self, selector):
        raise RuntimeError("DOM indisponible pour le test")


class Context:
    def __init__(self, pages):
        self.pages = pages


class UrlRoutingTest(unittest.TestCase):
    def setUp(self):
        self.catalog = FakePage("https://general.global-exam.com/levels/content")
        self.result = FakePage("https://general.global-exam.com/activity/123/result?token=secret#frag")
        self.exercise = FakePage("https://general.global-exam.com/activity/123/content/789")

    def test_recognizes_result_from_url_without_dom(self):
        self.assertEqual(kind_from_url(self.result.url), "result")
        self.assertTrue(is_result(self.result))
        self.assertTrue(result_overview(self.result)["ok"])

    def test_manually_opened_result_tab_is_found(self):
        ctx = Context([self.catalog, self.result])
        self.assertIs(_result_page_in_context(self.catalog, ctx), self.result)
        self.assertIs(page_for_kind(self.catalog, ctx, "result"), self.result)

    def test_existing_result_survives_startup(self):
        ctx = Context([self.catalog, self.result])
        page = initial_page(ctx)
        self.assertIs(page, self.result)
        self.assertFalse(needs_initial_navigation(page))

    def test_content_page_survives_startup(self):
        ctx = Context([FakePage("about:blank"), self.exercise])
        self.assertIs(initial_page(ctx), self.exercise)
        self.assertFalse(needs_initial_navigation(self.exercise))

    def test_tab_list_redacts_query_fragment(self):
        inventory = tab_inventory(Context([self.catalog, self.result]), self.catalog)
        self.assertTrue(inventory[0]["selected"])
        self.assertEqual(inventory[1]["kind"], "result")
        self.assertEqual(inventory[1]["route"], "https://general.global-exam.com/activity/123/result")
        self.assertNotIn("secret", str(inventory))

    def test_not_confuse_external_site_and_local(self):
        fake = FakePage("https://not-global-exam.example/activity/123/result")
        self.assertEqual(kind_from_url(fake.url), "external")
        self.assertIsNone(page_for_kind(fake, Context([fake]), "result"))
        self.assertEqual(kind_from_url("https://auth.global-exam.com/login"), "login")
        self.assertEqual(kind_from_url("https://general.global-exam.com/activity/123/content/789/correction"), "correction")

    def test_newest_result_or_focused_result(self):
        older = FakePage("https://general.global-exam.com/activity/1/result")
        newer = FakePage("https://general.global-exam.com/activity/2/result")
        ctx = Context([self.catalog, older, newer])
        self.assertIs(page_for_kind(self.catalog, ctx, "result"), newer)
        older.focus = True
        self.assertIs(page_for_kind(self.catalog, ctx, "result"), older)

    def test_closed_result_ignored(self):
        closed = FakePage(self.result.url, closed=True)
        self.assertIsNone(page_for_kind(self.catalog, Context([self.catalog, closed]), "result"))


if __name__ == "__main__":
    unittest.main()
