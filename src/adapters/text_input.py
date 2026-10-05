from .base import ExerciseAdapter


class TextInputAdapter(ExerciseAdapter):
    name = "text_input"
    priority = 60

    def matches(self):
        return self.page.locator(
            "textarea, input[type='text'], input:not([type])"
        ).count() > 0

    def analyze(self):
        locator = self.page.locator(
            "textarea, input[type='text'], input:not([type])"
        )

        fields = []

        for i in range(locator.count()):
            item = locator.nth(i)

            try:
                if not item.is_visible():
                    continue
            except Exception:
                continue

            fields.append({
                "index": i,
                "kind": "text",
                "name": item.get_attribute("name") or "",
                "placeholder": item.get_attribute("placeholder") or "",
            })

        return {
            "adapter": self.name,
            "exercise_type": "text_input",
            "question": None,
            "answers": fields,
        }

    def fill(self, index, value):
        locator = self.page.locator(
            "textarea, input[type='text'], input:not([type])"
        )

        if index < 0 or index >= locator.count():
            return False

        locator.nth(index).fill(value)
        return True

    def actions(self):
        return {"fill": self.fill}
