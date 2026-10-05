from .base import ExerciseAdapter


class QcmAdapter(ExerciseAdapter):
    name = "qcm"
    priority = 80

    def matches(self):
        return (
            self.page.locator("input[type='radio']").count() > 0
            or self.page.locator("input[type='checkbox']").count() > 0
        )

    def _question(self):
        for selector in ("main h2", "h2", "legend", "h3"):
            locator = self.page.locator(selector)

            for i in range(locator.count()):
                item = locator.nth(i)

                try:
                    if item.is_visible():
                        text = item.inner_text().strip()
                        if text:
                            return text
                except Exception:
                    pass

        return None

    def _choices(self):
        radio_count = self.page.locator("input[type='radio']").count()
        kind = "radio" if radio_count else "checkbox"
        locator = self.page.locator(f"input[type='{kind}']")

        choices = []

        for i in range(locator.count()):
            element = locator.nth(i)

            try:
                if not element.is_visible():
                    continue
            except Exception:
                continue

            text = ""
            element_id = element.get_attribute("id")

            if element_id:
                label = self.page.locator(f"label[for='{element_id}']")
                if label.count():
                    try:
                        text = label.first.inner_text().strip()
                    except Exception:
                        pass

            if not text:
                text = element.get_attribute("value") or ""

            choices.append({
                "index": i,
                "text": text,
                "kind": kind,
            })

        return choices, kind

    def analyze(self):
        choices, kind = self._choices()

        return {
            "adapter": self.name,
            "exercise_type": "qcm_single" if kind == "radio" else "qcm_multiple",
            "question": self._question(),
            "answers": choices,
        }

    def choose(self, index):
        analysis = self.analyze()
        answers = analysis["answers"]

        if index < 0 or index >= len(answers):
            return False

        kind = answers[index]["kind"]
        locator = self.page.locator(f"input[type='{kind}']")

        locator.nth(answers[index]["index"]).click()
        return True

    def actions(self):
        return {"choose": self.choose}
