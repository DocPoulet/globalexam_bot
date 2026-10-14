"""Regression checks for the October 2026 route signatures (synthetic only)."""
import unittest
from site_v2.detector import classify_page


class RouteTest(unittest.TestCase):
    def test_known_routes(self):
        rows = (
            ('https://general.global-exam.com/', 'home'),
            ('https://general.global-exam.com/levels/content', 'catalog'),
            ('https://general.global-exam.com/activity/123/content/456', 'exercise'),
            ('https://general.global-exam.com/activity/123/content/456/correction', 'correction'),
            ('https://general.global-exam.com/activity/123/result', 'result'),
        )
        for route, expected in rows:
            with self.subTest(route=route):
                snap = {'route': route, 'document': {}, 'controls': [{'label': 'Test'}],
                        'headings': [], 'links': [], 'dom_counts': {}}
                self.assertEqual(classify_page(snap)['kind'], expected)

    def test_no_dom_is_loading(self):
        snap = {'route':'https://general.global-exam.com/activity/123/content/456',
                'document': {},'controls':[],'headings':[],'links':[],'dom_counts':{}}
        self.assertEqual(classify_page(snap)['kind'], 'loading')

    def test_result_wins_over_correction_tab(self):
        snap = {'route':'https://general.global-exam.com/activity/123/result',
                'document':{'visible_text':'Vos réponses Correction Explication Votre score'},
                'controls':[{'label':'Correction'}], 'headings':[], 'links':[], 'dom_counts':{}}
        self.assertEqual(classify_page(snap)['kind'], 'result')


if __name__ == '__main__':
    unittest.main()
