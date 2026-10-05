from .base import ExerciseAdapter
from dom_utils import extract_question_text
from safety_clicks import is_forbidden_element, safe_click


class ButtonChoiceAdapter(ExerciseAdapter):
    name = "button_choice"
    priority = 80

    EXCLUDED = (
        "passer",
        "suivant",
        "next",
        "skip",
        "valider",
        "validate",
        "continuer",
        "continue",
        "faire défiler",
        "ouvrir le formulaire",
        "fermer",
        "précédent",
        "precedent",
    )

    def _root(self):
        for selector in (
            '[data-name="exam-answer-container"]',
            '[data-name="user-answer-container"]',
            '[data-testid*="answer"]',
            '[class*="answer-container"]',
        ):
            locator = self.page.locator(selector)
            if locator.count():
                return locator.first

        return self.page.locator("main").first

    def _candidate_buttons(self):
        root = self._root()
        locator = root.locator("button, [role='button']")
        result = []

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue

                if is_forbidden_element(el):
                    continue

                text = (
                    el.inner_text().strip()
                    or (el.get_attribute("aria-label") or "").strip()
                )
            except Exception:
                continue

            if not text:
                continue

            lowered = text.lower()

            if any(word in lowered for word in self.EXCLUDED):
                continue

            if el.get_attribute("data-testid") in (
                "close-button-desktop",
                "close-button-mobile",
            ):
                continue

            result.append({
                "index": len(result),
                "dom_index": i,
                "text": text,
                "state": el.get_attribute("data-state"),
                "pressed": el.get_attribute("aria-pressed"),
            })

        return result

    def matches(self):
        return len(self._candidate_buttons()) >= 1

    def analyze(self):
        return {
            "adapter": self.name,
            "exercise_type": "button_choice",
            "question": extract_question_text(self.page),
            "answers": self._candidate_buttons(),
        }

    def select(self, index):
        answers = self._candidate_buttons()

        if index < 0 or index >= len(answers):
            return False

        target = self._root().locator(
            "button, [role='button']"
        ).nth(answers[index]["dom_index"])

        if not safe_click(target):
            return False

        self.page.wait_for_timeout(250)
        return True

    def actions(self):
        return {"select": self.select}
