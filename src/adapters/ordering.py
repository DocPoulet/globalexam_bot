from .base import ExerciseAdapter
from dom_utils import extract_question_text
from safety_clicks import safe_click

SOURCE_SELECTOR = '[data-name="exam-answer-container"] button.draggable-item'
TARGET_SELECTOR = '[data-name="user-answer-container"]'
TARGET_ITEM_SELECTOR = '[data-name="user-answer-container"] button.draggable-item'


class OrderingAdapter(ExerciseAdapter):
    name = "ordering"
    priority = 120

    def matches(self):
        return (
            self.page.locator(SOURCE_SELECTOR).count() > 0
            or self.page.locator(TARGET_SELECTOR).count() > 0
        )

    def _items(self, selector, location):
        result = []
        locator = self.page.locator(selector)

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue

                text = el.inner_text().strip()
            except Exception:
                continue

            if not text:
                continue

            result.append({
                "index": len(result),
                "dom_index": i,
                "id": el.get_attribute("data-draggable-item-id"),
                "text": text,
                "state": el.get_attribute("data-state"),
                "location": location,
            })

        return result

    def analyze(self):
        answers = self._items(SOURCE_SELECTOR, "available")
        placed = self._items(TARGET_ITEM_SELECTOR, "answer")

        return {
            "adapter": self.name,
            "exercise_type": "ordering",
            "question": extract_question_text(self.page),
            "answers": answers,
            "placed": placed,
            "remaining": len(answers),
            "placed_count": len(placed),
        }

    def select(self, index):
        analysis = self.analyze()
        answers = analysis["answers"]

        if index < 0 or index >= len(answers):
            return False

        target = self.page.locator(SOURCE_SELECTOR).nth(
            answers[index]["dom_index"]
        )

        if not safe_click(target):
            return False

        self.page.wait_for_timeout(300)
        return True

    def drag_fallback(self, index):
        analysis = self.analyze()
        answers = analysis["answers"]

        if index < 0 or index >= len(answers):
            return False

        source = self.page.locator(SOURCE_SELECTOR).nth(
            answers[index]["dom_index"]
        )
        target = self.page.locator(TARGET_SELECTOR)

        if target.count() == 0:
            return False

        source.drag_to(target.first)
        self.page.wait_for_timeout(300)
        return True

    def actions(self):
        return {
            "select": self.select,
            "drag_fallback": self.drag_fallback,
        }
