from .base import ExerciseAdapter
from dom_utils import extract_question_text
from safety_clicks import is_forbidden_element, safe_click


class SpanChoiceAdapter(ExerciseAdapter):
    """
    Gère les réponses dont le texte visible est dans un <span>.

    On ne scanne PAS tous les spans de la page :
    - priorité aux conteneurs de réponse connus ;
    - sinon aux zones proches d'une question ;
    - on remonte toujours vers un ancêtre interactif si possible.
    """

    name = "span_choice"
    priority = 90

    ROOT_SELECTORS = (
        '[data-name="exam-answer-container"]',
        '[data-name="user-answer-container"]',
        '[data-testid*="answer"]',
        '[data-name*="answer"]',
        '[class*="answer-container"]',
        '[class*="answers"]',
        '[class*="choices"]',
        '[class*="options"]',
    )

    INTERACTIVE_ANCESTOR_XPATH = (
        "ancestor-or-self::*["
        "self::button or self::a or "
        "@role='button' or "
        "@tabindex='0' or "
        "contains(@class,'cursor-pointer') or "
        "contains(@class,'clickable') or "
        "@data-state or "
        "@data-value"
        "][1]"
    )

    def _roots(self):
        roots = []

        for selector in self.ROOT_SELECTORS:
            locator = self.page.locator(selector)

            for i in range(locator.count()):
                el = locator.nth(i)
                try:
                    if el.is_visible():
                        roots.append(el)
                except Exception:
                    pass

        # Déduplication approximative par texte + tag/class.
        unique = []
        seen = set()

        for root in roots:
            try:
                signature = root.evaluate(
                    """e => [
                        e.tagName,
                        e.getAttribute('class') || '',
                        e.getAttribute('data-name') || '',
                        (e.innerText || '').slice(0, 300)
                    ].join('|')"""
                )
            except Exception:
                signature = str(id(root))

            if signature in seen:
                continue

            seen.add(signature)
            unique.append(root)

        return unique

    def _candidate_from_span(self, span):
        """
        Retourne l'élément à cliquer :
        - parent interactif si présent ;
        - sinon le span lui-même uniquement s'il semble interactif.
        """
        try:
            text = span.inner_text().strip()
        except Exception:
            return None

        if not text:
            return None

        # Évite les gros spans de paragraphe.
        if len(text) > 500:
            return None

        try:
            ancestor = span.locator(
                f"xpath={self.INTERACTIVE_ANCESTOR_XPATH}"
            )

            if ancestor.count() > 0:
                target = ancestor.first
                if not is_forbidden_element(target):
                    return target
        except Exception:
            pass

        # Span lui-même : seulement s'il porte des indices d'interactivité.
        try:
            role = span.get_attribute("role")
            tabindex = span.get_attribute("tabindex")
            cls = span.get_attribute("class") or ""
            onclick = span.get_attribute("onclick")

            interactive = (
                role == "button"
                or tabindex == "0"
                or "cursor-pointer" in cls
                or "clickable" in cls
                or onclick is not None
            )

            if interactive and not is_forbidden_element(span):
                return span
        except Exception:
            pass

        return None

    def _candidates(self):
        result = []
        seen = set()

        for root in self._roots():
            spans = root.locator("span")

            for i in range(spans.count()):
                span = spans.nth(i)

                try:
                    if not span.is_visible():
                        continue
                    text = span.inner_text().strip()
                except Exception:
                    continue

                if not text:
                    continue

                target = self._candidate_from_span(span)
                if target is None:
                    continue

                try:
                    signature = target.evaluate(
                        """e => [
                            e.tagName,
                            e.getAttribute('class') || '',
                            e.getAttribute('role') || '',
                            e.getAttribute('tabindex') || '',
                            e.getAttribute('data-value') || '',
                            e.getAttribute('data-state') || '',
                            (e.innerText || '').trim()
                        ].join('|')"""
                    )
                except Exception:
                    signature = text

                if signature in seen:
                    continue

                seen.add(signature)

                result.append({
                    "index": len(result),
                    "text": text,
                    "state": target.get_attribute("data-state"),
                    "value": target.get_attribute("data-value"),
                    "target": target,
                })

        return result

    def matches(self):
        return len(self._candidates()) > 0

    def analyze(self):
        candidates = self._candidates()

        return {
            "adapter": self.name,
            "exercise_type": "span_choice",
            "question": extract_question_text(self.page),
            "answers": [
                {
                    "index": item["index"],
                    "text": item["text"],
                    "state": item["state"],
                    "value": item["value"],
                }
                for item in candidates
            ],
        }

    def select(self, index):
        candidates = self._candidates()

        if index < 0 or index >= len(candidates):
            return False

        target = candidates[index]["target"]

        if not safe_click(target):
            # Fallback : le span/parent peut être recouvert mais être le bon
            # composant Vue. Le garde-fou sécurité reste appliqué.
            if is_forbidden_element(target):
                return False

            if not safe_click(target, force=True):
                return False

        self.page.wait_for_timeout(300)
        return True

    def actions(self):
        return {"select": self.select}
