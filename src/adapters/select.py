from .base import ExerciseAdapter


class SelectAdapter(ExerciseAdapter):
    name = "select"
    priority = 60

    def matches(self):
        return self.page.locator("select").count() > 0

    def analyze(self):
        fields = []
        locator = self.page.locator("select")

        for i in range(locator.count()):
            options = []
            select = locator.nth(i)

            for j in range(select.locator("option").count()):
                option = select.locator("option").nth(j)
                options.append({
                    "index": j,
                    "text": option.inner_text().strip(),
                    "value": option.get_attribute("value"),
                })

            fields.append({"index": i, "options": options})

        return {
            "adapter": self.name,
            "exercise_type": "select",
            "question": None,
            "answers": fields,
        }
