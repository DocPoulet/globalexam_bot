from .base import ExerciseAdapter


class SelectAdapter(ExerciseAdapter):
    name = "select"
    priority = 70

    def matches(self):
        return self.page.locator("select").count() > 0

    def analyze(self):
        selects = []

        locator = self.page.locator("select")

        for i in range(locator.count()):
            select = locator.nth(i)

            try:
                if not select.is_visible():
                    continue
            except Exception:
                continue

            options = []
            option_locator = select.locator("option")

            for j in range(option_locator.count()):
                option = option_locator.nth(j)
                options.append({
                    "index": j,
                    "text": option.inner_text().strip(),
                    "value": option.get_attribute("value"),
                })

            selects.append({
                "index": i,
                "options": options,
            })

        return {
            "adapter": self.name,
            "exercise_type": "select",
            "question": None,
            "answers": selects,
        }

    def choose(self, select_index, option_index):
        locator = self.page.locator("select")

        if select_index < 0 or select_index >= locator.count():
            return False

        select = locator.nth(select_index)
        options = select.locator("option")

        if option_index < 0 or option_index >= options.count():
            return False

        value = options.nth(option_index).get_attribute("value")
        select.select_option(value=value)
        return True

    def actions(self):
        return {"choose_select": self.choose}
