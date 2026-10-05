from .base import ExerciseAdapter


class QcmAdapter(ExerciseAdapter):
    name = "qcm"
    priority = 80

    def matches(self):
        return (
            self.page.locator("input[type='radio']").count() > 0
            or self.page.locator("input[type='checkbox']").count() > 0
        )

    def analyze(self):
        kind = "radio" if self.page.locator("input[type='radio']").count() else "checkbox"
        locator = self.page.locator(f"input[type='{kind}']")
        answers = []

        for i in range(locator.count()):
            el = locator.nth(i)
            text = ""
            element_id = el.get_attribute("id")

            if element_id:
                label = self.page.locator(f"label[for='{element_id}']")
                if label.count():
                    try:
                        text = label.first.inner_text().strip()
                    except Exception:
                        pass

            answers.append({
                "index": i,
                "text": text or el.get_attribute("value") or "",
                "kind": kind,
            })

        return {
            "adapter": self.name,
            "exercise_type": "qcm_single" if kind == "radio" else "qcm_multiple",
            "question": None,
            "answers": answers,
        }

    def select(self, index):
        analysis = self.analyze()

        if index < 0 or index >= len(analysis["answers"]):
            return False

        kind = analysis["answers"][index]["kind"]
        self.page.locator(f"input[type='{kind}']").nth(index).click()
        self.page.wait_for_timeout(250)
        return True

    def actions(self):
        return {"select": self.select}
