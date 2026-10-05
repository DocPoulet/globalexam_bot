from .base import ExerciseAdapter


class ButtonChoiceAdapter(ExerciseAdapter):
    name = "button_choice"
    priority = 70

    EXCLUDED = (
        "passer",
        "suivant",
        "valider",
        "continuer",
        "faire défiler",
        "ouvrir le formulaire",
        "fermer",
    )

    def _candidate_buttons(self):
        result = []
        locator = self.page.locator("button")

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue

                text = (
                    el.inner_text().strip()
                    or (el.get_attribute("aria-label") or "").strip()
                )
            except Exception:
                continue

            if not text:
                continue

            lowered = text.lower()

            if any(word in lowered for word in self.EXCLUDED):
                continue

            if el.get_attribute("data-testid") in (
                "close-button-desktop",
                "close-button-mobile",
            ):
                continue

            result.append({
                "index": i,
                "text": text,
            })

        return result

    def matches(self):
        return len(self._candidate_buttons()) >= 2

    def analyze(self):
        return {
            "adapter": self.name,
            "exercise_type": "button_choice",
            "question": None,
            "answers": self._candidate_buttons(),
        }

    def select(self, index):
        answers = self._candidate_buttons()

        if index < 0 or index >= len(answers):
            return False

        self.page.locator("button").nth(answers[index]["index"]).click()
        self.page.wait_for_timeout(250)
        return True

    def actions(self):
        return {"select": self.select}
