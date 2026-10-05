import re
import unicodedata

FINISHED_WORDS = (
    "résultat", "resultat", "result",
    "score",
    "terminé", "termine", "terminée", "terminee",
    "activité terminée", "activite terminee",
    "completed", "finished",
    "félicitations", "felicitations",
)

NEXT_WORDS = ("suivant", "next", "continuer", "continue")
SKIP_WORDS = ("passer", "skip")

QUESTION_SELECTORS = (
    '[data-name="exam-answer-container"] button.draggable-item',
    'input[type="radio"]',
    'input[type="checkbox"]',
    'select',
    'textarea',
    'input[type="text"]',
)


def normalize(text):
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


class FlowController:
    """
    Gère les écrans où il n'y a rien à répondre :
    résultats, transitions, flashcards, Next/Skip.
    """

    def __init__(self, page, logger):
        self.page = page
        self.logger = logger

    def _visible(self, locator):
        try:
            return locator.is_visible()
        except Exception:
            return False

    def _disabled(self, locator):
        try:
            return locator.is_disabled()
        except Exception:
            return False

    def _main_text(self):
        for selector in ("main", "[role='main']", "body"):
            locator = self.page.locator(selector)
            if locator.count() == 0:
                continue
            try:
                text = locator.first.inner_text().strip()
                if text:
                    return text
            except Exception:
                pass
        return ""

    def _visible_controls(self):
        result = []
        locator = self.page.locator("button, a, [role='button']")

        for i in range(locator.count()):
            el = locator.nth(i)

            if not self._visible(el) or self._disabled(el):
                continue

            try:
                text = (
                    el.inner_text().strip()
                    or (el.get_attribute("aria-label") or "").strip()
                    or (el.get_attribute("title") or "").strip()
                )
            except Exception:
                continue

            if text:
                result.append((el, text))

        return result

    def has_answerable_question(self):
        for selector in QUESTION_SELECTORS:
            locator = self.page.locator(selector)

            for i in range(locator.count()):
                if self._visible(locator.nth(i)):
                    return True

        return False

    def looks_finished(self):
        text = normalize(self._main_text())

        if not text:
            return False

        if any(normalize(word) in text for word in FINISHED_WORDS):
            return True

        if not self.has_answerable_question():
            if re.search(r"\b\d+\s*/\s*\d+\b", text):
                return True
            if re.search(r"\b\d{1,3}\s*%\b", text):
                return True

        return False

    def _find_action(self, words):
        normalized_words = tuple(normalize(x) for x in words)

        for el, text in self._visible_controls():
            value = normalize(text)

            if value in normalized_words:
                return el, text

            if any(word in value for word in normalized_words):
                return el, text

        return None, None

    def click_next(self):
        el, text = self._find_action(NEXT_WORDS)

        if el is None:
            return False

        self.logger.info("Flow : clic Next (%s)", text)

        try:
            el.click()
            self.page.wait_for_timeout(550)
            return True
        except Exception:
            return False

    def click_skip(self):
        el, text = self._find_action(SKIP_WORDS)

        if el is None:
            return False

        self.logger.info("Flow : clic Skip (%s)", text)

        try:
            el.click()
            self.page.wait_for_timeout(550)
            return True
        except Exception:
            return False

    def _flashcard_controls(self):
        prev_selectors = (
            "#tns-flashcards-prev",
            ".tns-flashcards-prev",
            '[class*="tns-flashcards-prev"]',
            '[id*="tns-flashcards-prev"]',
        )

        next_selectors = (
            "#tns-flashcards-next",
            ".tns-flashcards-next",
            '[class*="tns-flashcards-next"]',
            '[id*="tns-flashcards-next"]',
        )

        prev = None
        next_ = None

        for selector in prev_selectors:
            locator = self.page.locator(selector)
            for i in range(locator.count()):
                candidate = locator.nth(i)
                if self._visible(candidate) and not self._disabled(candidate):
                    prev = candidate
                    break
            if prev is not None:
                break

        for selector in next_selectors:
            locator = self.page.locator(selector)
            for i in range(locator.count()):
                candidate = locator.nth(i)
                if self._visible(candidate) and not self._disabled(candidate):
                    next_ = candidate
                    break
            if next_ is not None:
                break

        return prev, next_

    def has_flashcards(self):
        prev, next_ = self._flashcard_controls()
        return prev is not None or next_ is not None

    def swipe_flashcards_until_next(self, max_swipes=60):
        """
        Parcourt les flashcards jusqu'à apparition du bouton Next global.
        """
        for step in range(max_swipes):
            next_action, _ = self._find_action(NEXT_WORDS)
            if next_action is not None:
                self.logger.info(
                    "Flashcards : Next apparu après %s swipe(s).",
                    step,
                )
                return True

            if self.has_answerable_question():
                return False

            prev, next_ = self._flashcard_controls()

            if prev is None and next_ is None:
                return False

            target = next_ if next_ is not None else prev

            self.logger.info(
                "Flashcards : clic %s/%s.",
                step + 1,
                max_swipes,
            )

            try:
                target.click()
                self.page.wait_for_timeout(350)
            except Exception:
                return False

        return False

    def advance_until_question(self, max_steps=80):
        """
        Continue jusqu'à rencontrer une vraie question.
        """
        for step in range(max_steps):
            if self.has_answerable_question():
                return {"state": "question", "steps": step}

            if self.looks_finished():
                if self.click_next():
                    continue

                if self.click_skip():
                    continue

                return {
                    "state": "finished_without_action",
                    "steps": step,
                }

            if self.click_next():
                continue

            if self.has_flashcards():
                self.swipe_flashcards_until_next()

                if self.click_next():
                    continue

                if self.has_answerable_question():
                    return {
                        "state": "question",
                        "steps": step + 1,
                    }

            if self.click_skip():
                continue

            return {"state": "blocked", "steps": step}

        return {"state": "max_steps", "steps": max_steps}
