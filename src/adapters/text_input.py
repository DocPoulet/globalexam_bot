from .base import ExerciseAdapter
from dom_utils import extract_question_text


INPUT_SELECTOR = (
    "textarea, "
    "input[type='text'], "
    "input:not([type]), "
    "[contenteditable='true']"
)


class TextInputAdapter(ExerciseAdapter):
    name = "text_input"
    priority = 60

    def _visible_fields(self):
        locator = self.page.locator(INPUT_SELECTOR)
        result = []

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue

            result.append(i)

        return result

    def matches(self):
        return bool(self._visible_fields())

    def analyze(self):
        locator = self.page.locator(INPUT_SELECTOR)
        fields = []

        for field_index, dom_index in enumerate(self._visible_fields()):
            el = locator.nth(dom_index)

            try:
                value = el.input_value()
            except Exception:
                value = el.inner_text().strip()

            fields.append({
                "index": field_index,
                "dom_index": dom_index,
                "placeholder": el.get_attribute("placeholder") or "",
                "value": value,
            })

        return {
            "adapter": self.name,
            "exercise_type": "text_input",
            "question": extract_question_text(self.page),
            "answers": fields,
        }

    def fill(self, field_index, text):
        analysis = self.analyze()
        fields = analysis["answers"]

        if field_index < 0 or field_index >= len(fields):
            return False

        el = self.page.locator(INPUT_SELECTOR).nth(
            fields[field_index]["dom_index"]
        )

        try:
            if el.get_attribute("contenteditable") == "true":
                el.click()
                el.fill(text)
            else:
                el.fill(text)

            self.page.wait_for_timeout(250)
            return True
        except Exception:
            return False

    def actions(self):
        return {"fill": self.fill}
