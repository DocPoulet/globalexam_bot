from .base import ExerciseAdapter
from dom_utils import extract_question_text
from safety_clicks import safe_click


class QcmAdapter(ExerciseAdapter):
    name = "qcm"
    priority = 100

    def _usable_control(self, el):
        """Accepte les inputs sr-only reliés à un label visible."""
        try:
            if el.is_visible():
                return True
            element_id = el.get_attribute("id")
            if element_id:
                labels = self.page.locator("label")
                for i in range(min(labels.count(), 100)):
                    label = labels.nth(i)
                    if label.get_attribute("for") == element_id and label.is_visible():
                        return True
            parent_label = el.locator("xpath=ancestor::label[1]")
            if parent_label.count() and parent_label.first.is_visible():
                return True
            parent = el.locator("xpath=parent::*")
            return ("sr-only" in (el.get_attribute("class") or "")
                    and parent.count() > 0 and parent.first.is_visible()
                    and bool(parent.first.inner_text().strip()))
        except Exception:
            return False

    def _kind(self):
        radios = self.page.locator("input[type='radio']")
        for i in range(radios.count()):
            try:
                if self._usable_control(radios.nth(i)):
                    return "radio"
            except Exception:
                pass

        checks = self.page.locator("input[type='checkbox']")
        for i in range(checks.count()):
            try:
                if self._usable_control(checks.nth(i)):
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
                if not self._usable_control(el):
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

        # Sur la nouvelle UI, l'input radio est sr-only : cliquer le label.
        clicked = False
        element_id = target.get_attribute("id")
        if element_id:
            labels = self.page.locator("label")
            for i in range(min(labels.count(), 100)):
                label = labels.nth(i)
                try:
                    if label.get_attribute("for") == element_id and label.is_visible():
                        clicked = safe_click(label)
                        if clicked:
                            break
                except Exception:
                    pass
        if not clicked:
            parent_label = target.locator("xpath=ancestor::label[1]")
            if parent_label.count() and parent_label.first.is_visible():
                clicked = safe_click(parent_label.first)
        if not clicked:
            try:
                target.check(timeout=1500)
                clicked = True
            except Exception:
                return False
        self.page.wait_for_timeout(250)
        return True

    def actions(self):
        return {"select": self.select}
