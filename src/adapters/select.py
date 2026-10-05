from .base import ExerciseAdapter
from dom_utils import extract_question_text


class SelectAdapter(ExerciseAdapter):
    name = "select"
    priority = 70

    def _visible_selects(self):
        result = []
        locator = self.page.locator("select")

        for i in range(locator.count()):
            try:
                if locator.nth(i).is_visible():
                    result.append(i)
            except Exception:
                pass

        return result

    def matches(self):
        return bool(self._visible_selects())

    def analyze(self):
        fields = []
        visible = self._visible_selects()
        locator = self.page.locator("select")

        for field_index, dom_index in enumerate(visible):
            select = locator.nth(dom_index)
            options = []

            current_value = select.input_value()

            for j in range(select.locator("option").count()):
                option = select.locator("option").nth(j)
                option_value = option.get_attribute("value")

                options.append({
                    "index": j,
                    "text": option.inner_text().strip(),
                    "value": option_value,
                    "selected": str(option_value) == str(current_value),
                })

            fields.append({
                "index": field_index,
                "dom_index": dom_index,
                "value": select.input_value(),
                "options": options,
            })

        return {
            "adapter": self.name,
            "exercise_type": "select",
            "question": extract_question_text(self.page),
            "answers": fields,
        }

    def choose(self, field_index, option_index):
        analysis = self.analyze()
        fields = analysis["answers"]

        if field_index < 0 or field_index >= len(fields):
            return False

        field = fields[field_index]
        options = field["options"]

        if option_index < 0 or option_index >= len(options):
            return False

        option = options[option_index]
        select = self.page.locator("select").nth(field["dom_index"])

        try:
            if option["value"] is not None:
                select.select_option(value=option["value"])
            else:
                select.select_option(index=option_index)
            self.page.wait_for_timeout(250)
            return True
        except Exception:
            return False

    def actions(self):
        return {"choose": self.choose}
