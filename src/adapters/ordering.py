from .base import ExerciseAdapter

SOURCE_SELECTOR = '[data-name="exam-answer-container"] button.draggable-item'
TARGET_SELECTOR = '[data-name="user-answer-container"]'
TARGET_ITEM_SELECTOR = '[data-name="user-answer-container"] button.draggable-item'


class OrderingAdapter(ExerciseAdapter):
    name = "ordering_click"
    priority = 100

    def matches(self):
        return (
            self.page.locator(SOURCE_SELECTOR).count() > 0
            or self.page.locator(TARGET_SELECTOR).count() > 0
        )

    def _question(self):
        for selector in ("main h2", "h2", "legend"):
            locator = self.page.locator(selector)

            for i in range(locator.count()):
                el = locator.nth(i)
                try:
                    if el.is_visible():
                        text = el.inner_text().strip()
                        if text:
                            return text
                except Exception:
                    pass

        return None

    def _items(self, selector, location):
        result = []
        locator = self.page.locator(selector)

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue

                text = el.inner_text().strip()
                item_id = el.get_attribute("data-draggable-item-id")
                state = el.get_attribute("data-state")
            except Exception:
                continue

            if text:
                result.append({
                    "index": i,
                    "id": item_id,
                    "text": text,
                    "state": state,
                    "location": location,
                })

        return result

    def analyze(self):
        available = self._items(SOURCE_SELECTOR, "available")
        placed = self._items(TARGET_ITEM_SELECTOR, "answer")

        return {
            "adapter": self.name,
            "exercise_type": "ordering",
            "question": self._question(),
            "answers": available,
            "placed": placed,
            "remaining": len(available),
            "placed_count": len(placed),
        }

    def select(self, index):
        locator = self.page.locator(SOURCE_SELECTOR)

        if index < 0 or index >= locator.count():
            return False

        locator.nth(index).click()
        self.page.wait_for_timeout(300)
        return True

    def drag_fallback(self, index):
        source = self.page.locator(SOURCE_SELECTOR)
        target = self.page.locator(TARGET_SELECTOR)

        if index < 0 or index >= source.count() or target.count() == 0:
            return False

        source.nth(index).drag_to(target.first)
        self.page.wait_for_timeout(300)
        return True

    def actions(self):
        return {
            "select": self.select,
            "drag_fallback": self.drag_fallback,
        }
