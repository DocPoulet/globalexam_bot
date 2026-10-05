from .base import ExerciseAdapter


class TextInputAdapter(ExerciseAdapter):
    name = "text_input"
    priority = 50

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
            el = locator.nth(i)
            fields.append({
                "index": i,
                "placeholder": el.get_attribute("placeholder") or "",
            })

        return {
            "adapter": self.name,
            "exercise_type": "text_input",
            "question": None,
            "answers": fields,
        }
