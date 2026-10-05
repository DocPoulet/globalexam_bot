from .base import ExerciseAdapter


class OrderingDragDropAdapter(ExerciseAdapter):
    """
    Adaptateur basé sur les diagnostics réels GlobalExam :
    button.draggable-item.
    """

    name = "ordering_dragdrop"
    priority = 100

    def matches(self):
        locator = self.page.locator("button.draggable-item")

        try:
            return locator.count() > 0
        except Exception:
            return False

    def _question(self):
        for selector in ("main h2", "h2", "legend"):
            locator = self.page.locator(selector)

            for i in range(locator.count()):
                item = locator.nth(i)

                try:
                    if not item.is_visible():
                        continue

                    text = item.inner_text().strip()
                except Exception:
                    continue

                if text:
                    return text

        return None

    def _items(self):
        items = []
        locator = self.page.locator("button.draggable-item")

        for i in range(locator.count()):
            item = locator.nth(i)

            try:
                if not item.is_visible():
                    continue

                text = item.inner_text().strip()
            except Exception:
                continue

            if text:
                items.append({
                    "index": i,
                    "text": text,
                    "kind": "draggable",
                })

        return items

    def analyze(self):
        return {
            "adapter": self.name,
            "exercise_type": self.name,
            "question": self._question(),
            "answers": self._items(),
        }

    def drag(self, source_index, target_index):
        locator = self.page.locator("button.draggable-item")

        if source_index < 0 or target_index < 0:
            return False

        if source_index >= locator.count() or target_index >= locator.count():
            return False

        locator.nth(source_index).drag_to(locator.nth(target_index))
        return True

    def click_item(self, index):
        locator = self.page.locator("button.draggable-item")

        if index < 0 or index >= locator.count():
            return False

        locator.nth(index).click()
        return True

    def actions(self):
        return {
            "drag": self.drag,
            "click_item": self.click_item,
        }
