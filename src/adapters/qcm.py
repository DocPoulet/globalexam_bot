from .base import ExerciseAdapter
from dom_utils import extract_question_text
from safety_clicks import safe_click


class QcmAdapter(ExerciseAdapter):
    name = "qcm"
    priority = 100

    def _kind(self):
        radios = self.page.locator("input[type='radio']")
        for i in range(radios.count()):
            try:
                if radios.nth(i).is_visible():
                    return "radio"
            except Exception:
                pass

        checks = self.page.locator("input[type='checkbox']")
        for i in range(checks.count()):
            try:
                if checks.nth(i).is_visible():
                    return "checkbox"
            except Exception:
                pass

        return None

    def matches(self):
        return self._kind() is not None

    def _label_text(self, el):
        element_id = el.get_attribute("id")

        if element_id:
            label = self.page.locator(f"label[for='{element_id}']")
            if label.count():
                try:
                    text = label.first.inner_text().strip()
                    if text:
                        return text
                except Exception:
                    pass

        try:
            parent_label = el.locator("xpath=ancestor::label[1]")
            if parent_label.count():
                text = parent_label.first.inner_text().strip()
                if text:
                    return text
        except Exception:
            pass

        try:
            parent = el.locator("xpath=parent::*")
            text = parent.inner_text().strip()
            if text:
                return text
        except Exception:
            pass

        return el.get_attribute("value") or ""

    def analyze(self):
        kind = self._kind()
        locator = self.page.locator(f"input[type='{kind}']")
        answers = []

        for i in range(locator.count()):
            el = locator.nth(i)

            try:
                if not el.is_visible():
                    continue
            except Exception:
                continue

            answers.append({
                "index": len(answers),
                "dom_index": i,
                "text": self._label_text(el),
                "kind": kind,
                "selected": el.is_checked(),
                "disabled": el.is_disabled(),
            })

        return {
            "adapter": self.name,
            "exercise_type": (
                "qcm_single" if kind == "radio" else "qcm_multiple"
            ),
            "question": extract_question_text(self.page),
            "answers": answers,
        }

    def select(self, index):
        analysis = self.analyze()

        if index < 0 or index >= len(analysis["answers"]):
            return False

        item = analysis["answers"][index]

        if item["disabled"]:
            return False

        target = self.page.locator(
            f"input[type='{item['kind']}']"
        ).nth(item["dom_index"])

        if not safe_click(target):
            return False

        self.page.wait_for_timeout(250)
        return True

    def actions(self):
        return {"select": self.select}
