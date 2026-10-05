import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

from safety_clicks import is_forbidden_element, safe_click


RESULT_PHRASES = (
    "votre score",
)

RESULT_CONTINUE_PHRASES = (
    "passer à la suite",
    "passer a la suite",
)

RESULT_VALIDATE_WORDS = (
    "valider",
    "validate",
    "confirmer",
    "terminer",
    "finish",
    "submit",
)

NEXT_WORDS = (
    "suivant",
    "next",
    "continuer",
    "continue",
    "poursuivre",
    "étape suivante",
    "etape suivante",
    "question suivante",
)

SKIP_WORDS = (
    "passer",
    "skip",
    "ignorer",
)

QUESTION_SELECTORS = (
    '[data-name="exam-answer-container"] button.draggable-item',
    '[data-name="exam-answer-container"] button',
    '[data-name="exam-answer-container"] span',
    '[data-testid*="answer"] span',
    '[data-name*="answer"] span',
    '[class*="answer-container"] span',
    'input[type="radio"]',
    'input[type="checkbox"]',
    'select',
    'textarea',
    'input[type="text"]',
    '[contenteditable="true"]',
)

CONTROL_SELECTOR = (
    "button, "
    "a, "
    "[role='button'], "
    "[tabindex='0'], "
    "input[type='button'], "
    "input[type='submit'], "
    "[class*='cursor-pointer'], "
    "[data-controls], "
    "[data-action]"
)

MEMO_KEYWORDS = (
    "mémo", "memo", "mémoriser", "memoriser", "memory", "flash", "card",
)

AUDIO_KEYWORDS = (
    "audio", "écouter", "ecouter", "listen", "play", "lecture", "speaker",
)

CONTENT_ACTION_KEYWORDS = {
    "memo": (
        "mémo", "memo", "révéler", "reveler", "voir", "show", "afficher",
        "comprendre", "continuer",
    ),
    "audio": (
        "audio", "écouter", "ecouter", "listen", "play", "lecture",
        "lancer", "démarrer", "demarrer",
    ),
}


def normalize(text):
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


class FlowController:
    def __init__(self, page, logger):
        self.page = page
        self.logger = logger

    # ---------------------------------------------------------------
    # Frames / DOM helpers
    # ---------------------------------------------------------------

    def _candidate_frames(self):
        frames = list(self.page.frames)

        def score(frame):
            url = (frame.url or "").lower()
            if "general.global-exam.com" in url:
                return 0
            if "global-exam.com" in url:
                return 1
            return 2

        return sorted(frames, key=score)

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
        for frame in self._candidate_frames():
            for selector in ("main", "[role='main']", "body"):
                locator = frame.locator(selector)

                if locator.count() == 0:
                    continue

                try:
                    text = locator.first.inner_text().strip()
                    if text:
                        return text
                except Exception:
                    pass

        return ""

    def _control_text(self, el):
        values = []

        try:
            text = el.inner_text().strip()
            if text:
                values.append(text)
        except Exception:
            pass

        for attr in (
            "aria-label",
            "title",
            "value",
            "data-label",
            "data-testid",
            "name",
        ):
            try:
                value = (el.get_attribute(attr) or "").strip()
                if value:
                    values.append(value)
            except Exception:
                pass

        return " | ".join(values)

    def _visible_controls(self):
        result = []

        for frame in self._candidate_frames():
            locator = frame.locator(CONTROL_SELECTOR)

            for i in range(locator.count()):
                el = locator.nth(i)

                if not self._visible(el):
                    continue

                if self._disabled(el):
                    continue

                if is_forbidden_element(el):
                    continue

                text = self._control_text(el)
                if not text:
                    continue

                result.append((el, text, frame.url))

        return result

    def debug_controls(self):
        return [
            {"text": text, "frame": frame_url}
            for _, text, frame_url in self._visible_controls()
        ]

    def _page_signature(self):
        """
        Signature légère de l'état courant pour savoir si un clic
        a réellement fait évoluer la page.
        """
        try:
            text = normalize(self._main_text())
        except Exception:
            text = ""

        return (
            self.page.url,
            text[:1500],
        )

    def _wait_after_progress_click(
        self,
        before_signature=None,
        min_wait_ms=700,
        max_wait_ms=3000,
        poll_ms=150,
    ):
        """
        Après un clic de progression :
        - attend au minimum min_wait_ms ;
        - puis surveille URL/texte jusqu'à changement ;
        - ne dépasse jamais max_wait_ms.

        Cela évite de recliquer plusieurs fois sur le même bouton pendant
        que GlobalExam charge encore l'écran suivant.
        """
        if before_signature is None:
            before_signature = self._page_signature()

        elapsed = 0

        # Délai plancher volontaire.
        self.page.wait_for_timeout(min_wait_ms)
        elapsed += min_wait_ms

        while elapsed < max_wait_ms:
            current = self._page_signature()

            if current != before_signature:
                # Laisse encore un petit temps à Vue/SPA pour finir le rendu.
                self.page.wait_for_timeout(250)
                return True

            try:
                self.page.wait_for_load_state(
                    "domcontentloaded",
                    timeout=poll_ms,
                )
            except Exception:
                pass

            self.page.wait_for_timeout(poll_ms)
            elapsed += poll_ms

        return False

    # ---------------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------------

    def _save_blocked_diagnostic(self):
        base_dir = Path(__file__).resolve().parent.parent / "diagnostics"
        base_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        payload = {
            "url": self.page.url,
            "title": self.page.title(),
            "screen_kind": self.detect_screen_kind(),
            "looks_finished": self.looks_finished(),
            "answerable_question": self.has_answerable_question(),
            "flashcards": self.has_flashcards(),
            "memo": self.has_memo_content(),
            "audio": self.has_audio_content(),
            "visible_controls": self.debug_controls(),
        }

        path = base_dir / f"flow_blocked_{stamp}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        try:
            self.page.screenshot(
                path=str(base_dir / f"flow_blocked_{stamp}.png"),
                full_page=True,
            )
        except Exception:
            pass

        self.logger.info("Flow bloqué : diagnostic %s", path)

    # ---------------------------------------------------------------
    # Screen-kind detection
    # ---------------------------------------------------------------

    def has_answerable_question(self):
        for frame in self._candidate_frames():
            for selector in QUESTION_SELECTORS:
                locator = frame.locator(selector)

                for i in range(locator.count()):
                    if self._visible(locator.nth(i)):
                        return True

        return False

    def looks_finished(self):
        """
        Un écran est considéré comme résultat uniquement si GlobalExam
        affiche explicitement "Votre score".

        On n'utilise plus :
        - "score" tout seul ;
        - les pourcentages ;
        - les formes 8/10 ;
        - "result"/"finished" génériques.

        Cela évite de confondre une vraie question avec un résultat.
        """
        text = normalize(self._main_text())

        if not text:
            return False

        return any(
            normalize(phrase) in text
            for phrase in RESULT_PHRASES
        )

    def _text_has_any(self, keywords):
        text = normalize(self._main_text())
        return any(normalize(word) in text for word in keywords)

    def has_flashcards(self):
        # Détection directe des IDs connus, même si le bouton est
        # momentanément disabled pendant une animation.
        for frame in self._candidate_frames():
            for selector in (
                "#tns-flashcards-next",
                "#tns-flashcards-prev",
                '[id="tns-flashcards-next"]',
                '[id="tns-flashcards-prev"]',
            ):
                try:
                    locator = frame.locator(selector)
                except Exception:
                    continue

                for i in range(locator.count()):
                    try:
                        if locator.nth(i).is_visible():
                            return True
                    except Exception:
                        pass

        prev, next_ = self._flashcard_controls()
        return prev is not None or next_ is not None

    def has_memo_content(self):
        if self.has_answerable_question():
            return False

        if self._text_has_any(MEMO_KEYWORDS):
            return True

        for frame in self._candidate_frames():
            for selector in (
                '[class*="memo"]',
                '[data-testid*="memo"]',
                '[data-name*="memo"]',
            ):
                locator = frame.locator(selector)
                for i in range(locator.count()):
                    if self._visible(locator.nth(i)):
                        return True

        return False

    def has_audio_content(self):
        if self.has_answerable_question():
            return False

        for frame in self._candidate_frames():
            locator = frame.locator("audio")
            for i in range(locator.count()):
                if self._visible(locator.nth(i)):
                    return True

        if self._text_has_any(AUDIO_KEYWORDS):
            return True

        for _, text, _ in self._visible_controls():
            value = normalize(text)
            if any(normalize(word) in value for word in AUDIO_KEYWORDS):
                return True

        return False

    def has_exact_skip_passer(self):
        """
        Si un contrôle de progression affiche exactement "Passer",
        on le traite comme le bouton Skip d'un exercice.
        """
        for el, text, _ in self._visible_controls():
            value = normalize(text)

            # Le contrôle peut avoir plusieurs labels séparés par |
            parts = [part.strip() for part in value.split("|")]

            if "passer" in parts:
                return True

        return False

    def has_exact_next_suivant(self):
        """
        True uniquement si le bouton exact "Suivant" est visible ET utilisable.
        """
        el, _, _ = self._find_exact_suivant()
        return el is not None

    def detect_screen_kind(self):
        if self.looks_finished():
            return "result"

        # PRIORITÉ FLASHCARD :
        # la page peut afficher un bouton "Suivant" désactivé pendant
        # que le carousel #tns-flashcards-next/#tns-flashcards-prev
        # doit encore être parcouru.
        if self.has_flashcards():
            return "flashcard"

        # Seulement ensuite, un vrai "Suivant" actif signifie transition.
        if self.has_exact_next_suivant():
            return "transition"

        # Un bouton Skip "Passer" reste un marqueur fort d'exercice.
        if self.has_exact_skip_passer():
            return "exercise"

        if self.has_answerable_question():
            return "exercise"

        if self.has_memo_content():
            return "memo"

        if self.has_audio_content():
            return "audio"

        return "transition"

    def _find_exact_text_action(self, phrases):
        """
        Cherche un texte visible partout dans les frames et remonte vers
        le premier parent réellement cliquable.

        Retourne une liste de candidats afin de pouvoir en essayer plusieurs
        si un élément visible n'est qu'un wrapper décoratif.
        """
        candidates = []
        seen = set()

        for frame in self._candidate_frames():
            for phrase in phrases:
                try:
                    matches = frame.get_by_text(phrase, exact=False)
                except Exception:
                    continue

                for i in range(matches.count()):
                    node = matches.nth(i)

                    try:
                        if not node.is_visible():
                            continue
                    except Exception:
                        continue

                    try:
                        target_locator = node.locator(
                            "xpath=ancestor-or-self::*["
                            "self::button or self::a or "
                            "@role='button' or @tabindex='0' or "
                            "contains(@class,'cursor-pointer') or "
                            "@data-controls or @data-action"
                            "][1]"
                        )

                        target = (
                            target_locator.first
                            if target_locator.count() > 0
                            else node
                        )
                    except Exception:
                        target = node

                    if is_forbidden_element(target):
                        continue

                    try:
                        signature = target.evaluate(
                            """e => [
                                e.tagName,
                                e.getAttribute('class') || '',
                                e.getAttribute('role') || '',
                                e.getAttribute('data-controls') || '',
                                e.getAttribute('data-action') || '',
                                (e.innerText || '').trim()
                            ].join('|')"""
                        )
                    except Exception:
                        signature = f"{frame.url}|{phrase}|{i}"

                    if signature in seen:
                        continue

                    seen.add(signature)
                    candidates.append(
                        (
                            target,
                            self._control_text(target) or self._control_text(node),
                            frame.url,
                        )
                    )

        return candidates

    def _click_and_confirm_progress(
        self,
        el,
        label,
        frame_url=None,
        min_wait_ms=650,
        max_wait_ms=4500,
    ):
        """
        Un clic n'est considéré réussi que si l'écran évolue vraiment.

        Cela évite la boucle infinie :
        clic techniquement accepté -> aucun changement -> même clic -> ...
        """
        before = self._page_signature()

        self.logger.info(
            "Flow : tentative clic %s frame=%s",
            label,
            frame_url,
        )

        clicked = safe_click(el)

        if not clicked and not is_forbidden_element(el):
            clicked = safe_click(el, force=True)

        if not clicked:
            self.logger.info("Flow : clic refusé/échoué pour %s", label)
            return False

        changed = self._wait_after_progress_click(
            before,
            min_wait_ms=min_wait_ms,
            max_wait_ms=max_wait_ms,
        )

        if changed:
            self.logger.info("Flow : %s a bien fait évoluer la page.", label)
            return True

        self.logger.info(
            "Flow : %s cliqué mais aucun changement détecté.",
            label,
        )
        return False

    def _find_exact_suivant(self):
        """
        Cherche le CTA exact 'Suivant' dans tous les frames, mais seulement
        s'il est réellement utilisable.

        Sur les flashcards GlobalExam, "Suivant" peut être visible avant
        d'être activé. Ce bouton ne doit alors PAS court-circuiter le carousel.
        """
        candidates = self._find_exact_text_action(("Suivant",))

        for el, text, frame_url in candidates:
            try:
                if el.is_disabled():
                    continue
            except Exception:
                pass

            try:
                aria_disabled = (el.get_attribute("aria-disabled") or "").lower()
                if aria_disabled == "true":
                    continue
            except Exception:
                pass

            try:
                disabled_attr = el.get_attribute("disabled")
                if disabled_attr is not None:
                    continue
            except Exception:
                pass

            # Plusieurs composants front utilisent des classes plutôt qu'un
            # attribut disabled.
            try:
                cls = (el.get_attribute("class") or "").lower()
                if any(token in cls for token in (
                    "disabled",
                    "pointer-events-none",
                    "cursor-not-allowed",
                    "opacity-50",
                )):
                    continue
            except Exception:
                pass

            return el, text, frame_url

        return None, None, None

    def _find_result_continue_candidates(self):
        """
        Candidats privilégiés de l'écran résultat.

        On cherche d'abord le libellé observé sur GlobalExam :
        "Passer à la suite".
        """
        return self._find_exact_text_action(RESULT_CONTINUE_PHRASES)

    def click_result_continue(self, wait=False, timeout_ms=4500, step_ms=150):
        """
        Essaie tous les candidats 'Passer à la suite'.

        Un candidat n'est accepté que si la page change réellement.
        """
        elapsed = 0
        last_log_bucket = -1

        while True:
            candidates = self._find_result_continue_candidates()

            if candidates:
                self.logger.info(
                    "Résultat : %s candidat(s) 'Passer à la suite'.",
                    len(candidates),
                )

                for el, text, frame_url in candidates:
                    if self._click_and_confirm_progress(
                        el,
                        f"Passer à la suite ({text})",
                        frame_url,
                    ):
                        return True

            if not wait or elapsed >= timeout_ms:
                return False

            bucket = elapsed // 1000
            if bucket != last_log_bucket:
                last_log_bucket = bucket
                self.logger.info(
                    "Résultat : attente du bouton de sortie... %sms/%sms",
                    elapsed,
                    timeout_ms,
                )

            self.page.wait_for_timeout(step_ms)
            elapsed += step_ms

    def _find_result_validate_action(self):
        """
        Dernier fallback d'un écran résultat :
        Valider / Confirmer / Terminer / Submit.
        """
        wanted = tuple(normalize(x) for x in RESULT_VALIDATE_WORDS)

        for el, text, frame_url in self._visible_controls():
            parts = [normalize(x).strip() for x in text.split("|")]

            if any(part in wanted for part in parts):
                return el, text, frame_url

        for el, text, frame_url in self._visible_controls():
            value = normalize(text)

            if any(word in value for word in wanted):
                return el, text, frame_url

        return None, None, None

    def click_result_fallback(self, wait=False, timeout_ms=3500, step_ms=150):
        """
        Si "Passer à la suite" n'existe pas, essaie dans cet ordre :

        1. Next / Suivant / Continuer
        2. Skip / Passer
        3. Validate / Valider / Confirmer / Terminer
        """
        elapsed = 0

        while True:
            # Next / Skip utilisent déjà les sélecteurs robustes multi-frame.
            kind, el, text, frame_url = self._find_progress_action()

            if el is not None:
                self.logger.info(
                    "Flow résultat fallback : clic %s (%s) frame=%s",
                    kind,
                    text,
                    frame_url,
                )

                if self._click_and_confirm_progress(
                    el,
                    f"result fallback {kind} ({text})",
                    frame_url,
                ):
                    return kind

            # Dernier secours : Validate/Valider/Terminer.
            el, text, frame_url = self._find_result_validate_action()

            if el is not None:
                self.logger.info(
                    "Flow résultat fallback : clic validate (%s) frame=%s",
                    text,
                    frame_url,
                )

                if self._click_and_confirm_progress(
                    el,
                    f"result fallback validate ({text})",
                    frame_url,
                ):
                    return "validate"

            if not wait or elapsed >= timeout_ms:
                return None

            self.page.wait_for_timeout(step_ms)
            elapsed += step_ms

    # ---------------------------------------------------------------
    # Progress actions
    # ---------------------------------------------------------------

    def _find_action(self, words):
        wanted = tuple(normalize(x) for x in words)
        controls = self._visible_controls()

        for el, text, frame_url in controls:
            parts = [normalize(x) for x in text.split("|")]
            if any(part.strip() in wanted for part in parts):
                return el, text, frame_url

        for el, text, frame_url in controls:
            value = normalize(text)
            if any(word in value for word in wanted):
                return el, text, frame_url

        return None, None, None

    def _find_progress_action(self):
        next_el, next_text, next_frame = self._find_action(NEXT_WORDS)
        if next_el is not None:
            return "next", next_el, next_text, next_frame

        skip_el, skip_text, skip_frame = self._find_action(SKIP_WORDS)
        if skip_el is not None:
            return "skip", skip_el, skip_text, skip_frame

        return None, None, None, None

    def _wait_for_progress_action(self, timeout_ms=3500, step_ms=150):
        elapsed = 0

        while elapsed <= timeout_ms:
            result = self._find_progress_action()
            if result[0] is not None:
                return result

            if elapsed >= timeout_ms:
                break

            self.page.wait_for_timeout(step_ms)
            elapsed += step_ms

        return None, None, None, None

    def click_progress_action(self, wait=False):
        if wait:
            kind, el, text, frame_url = self._wait_for_progress_action()
        else:
            kind, el, text, frame_url = self._find_progress_action()

        if el is None:
            return None

        self.logger.info(
            "Flow : clic progression %s (%s) frame=%s",
            kind,
            text,
            frame_url,
        )

        if self._click_and_confirm_progress(
            el,
            f"progress {kind} ({text})",
            frame_url,
            min_wait_ms=550,
            max_wait_ms=3500,
        ):
            return kind

        return None

    # ---------------------------------------------------------------
    # Flashcards / memo / audio helpers
    # ---------------------------------------------------------------

    def _flashcard_controls(self):
        """
        Retourne les vrais boutons de navigation des flashcards.

        Sélecteurs prioritaires observés sur GlobalExam :
        - #tns-flashcards-next
        - #tns-flashcards-prev

        Les anciens sélecteurs restent seulement en secours.
        """
        prev_selectors = (
            "#tns-flashcards-prev",
            '[id="tns-flashcards-prev"]',
            '[data-controls="prev"]',
            ".tns-flashcards-prev",
            '[class*="tns-flashcards-prev"]',
        )

        next_selectors = (
            "#tns-flashcards-next",
            '[id="tns-flashcards-next"]',
            '[data-controls="next"]',
            ".tns-flashcards-next",
            '[class*="tns-flashcards-next"]',
        )

        def first_usable(selectors):
            for frame in self._candidate_frames():
                for selector in selectors:
                    try:
                        locator = frame.locator(selector)
                    except Exception:
                        continue

                    for i in range(locator.count()):
                        candidate = locator.nth(i)

                        try:
                            if not candidate.is_visible():
                                continue
                        except Exception:
                            continue

                        # Un bouton peut être présent mais disabled en bout
                        # de carousel. On l'ignore dans ce cas.
                        try:
                            if candidate.is_disabled():
                                continue
                        except Exception:
                            pass

                        if is_forbidden_element(candidate):
                            continue

                        return candidate

            return None

        prev = first_usable(prev_selectors)
        next_ = first_usable(next_selectors)
        return prev, next_

    def swipe_flashcards_until_progress(self, max_swipes=30):
        """
        Fait défiler les flashcards jusqu'à apparition du bouton général
        exact "Suivant".

        Important :
        le DOM du carousel peut être recréé après chaque clic. On ne garde
        donc jamais un ancien Locator : les boutons next/prev sont recherchés
        à nouveau à CHAQUE itération.
        """
        last_direction = "next"
        no_control_count = 0

        for step in range(max_swipes + 1):
            # 1) Le CTA global "Suivant" n'arrête la boucle que s'il est
            # réellement actif. Un bouton visible mais disabled est ignoré.
            suivant, text, frame_url = self._find_exact_suivant()

            if suivant is not None:
                self.logger.info(
                    "Flashcards : bouton général 'Suivant' apparu après %s clic(s).",
                    step,
                )
                return True

            # 2) Réacquérir les boutons à chaque tour.
            prev, next_ = self._flashcard_controls()

            if next_ is not None:
                target = next_
                direction = "next"
            elif prev is not None:
                target = prev
                direction = "prev"
            else:
                no_control_count += 1
                self.logger.info(
                    "Flashcards : aucun #tns-flashcards-next/prev visible "
                    "(tentative %s/5).",
                    no_control_count,
                )

                # Le carousel peut être entre deux rendus.
                if no_control_count < 5:
                    self.page.wait_for_timeout(350)
                    continue

                return False

            no_control_count = 0
            last_direction = direction

            try:
                control_id = target.get_attribute("id") or ""
            except Exception:
                control_id = ""

            self.logger.info(
                "Flashcards : clic %s/%s sur #%s (%s).",
                step + 1,
                max_swipes,
                control_id or "flashcard-control",
                direction,
            )

            # Timeout court : aucun clic flashcard ne doit bloquer.
            clicked = safe_click(target, timeout=1800)

            if not clicked and not is_forbidden_element(target):
                clicked = safe_click(target, force=True, timeout=1200)

            if not clicked:
                self.logger.info(
                    "Flashcards : clic impossible sur %s, nouvelle détection.",
                    direction,
                )
                self.page.wait_for_timeout(250)
                continue

            # Laisse l'animation du carousel se finir avant de réacquérir
            # #tns-flashcards-next / #tns-flashcards-prev.
            self.page.wait_for_timeout(550)

        self.logger.info(
            "Flashcards : limite de %s clics atteinte sans bouton 'Suivant' "
            "(dernière direction=%s).",
            max_swipes,
            last_direction,
        )
        return False

    def _find_content_action(self, kind):
        keywords = CONTENT_ACTION_KEYWORDS.get(kind, ())
        if not keywords:
            return None, None, None

        for el, text, frame_url in self._visible_controls():
            value = normalize(text)

            # Exclure explicitement les actions de progression,
            # traitées ailleurs.
            if any(word in value for word in tuple(normalize(w) for w in NEXT_WORDS + SKIP_WORDS)):
                continue

            if any(normalize(word) in value for word in keywords):
                return el, text, frame_url

        return None, None, None

    def _advance_content_until_progress(self, kind, max_steps=15):
        """
        Pour les écrans mémo/audio :
        - si Next/Skip est visible -> on clique ;
        - sinon on clique le contrôle spécifique (play, mémo, etc.)
          jusqu'à apparition de Next/Skip.
        """
        seen = set()

        for step in range(max_steps):
            action = self.click_progress_action(wait=False)
            if action is not None:
                return True

            if self.has_answerable_question():
                return False

            el, text, frame_url = self._find_content_action(kind)
            if el is None:
                # Si aucun contrôle spécifique n'est visible, on attend un peu
                # qu'un bouton de progression apparaisse.
                action = self.click_progress_action(wait=True)
                return action is not None

            signature = (normalize(text), frame_url)
            if signature in seen and step > 1:
                action = self.click_progress_action(wait=True)
                return action is not None

            seen.add(signature)

            self.logger.info(
                "Flow : contenu %s, clic interne (%s) frame=%s",
                kind,
                text,
                frame_url,
            )

            if not safe_click(el):
                return False

            self.page.wait_for_timeout(650)

        return self.click_progress_action(wait=True) is not None

    # ---------------------------------------------------------------
    # Main loop
    # ---------------------------------------------------------------

    def advance_until_question(self, max_steps=80):
        for step in range(max_steps):
            kind = self.detect_screen_kind()
            self.logger.info(
                "Flow : étape %s/%s, écran détecté=%s",
                step + 1,
                max_steps,
                kind,
            )

            if kind == "result":
                self.logger.info(
                    "Résultat détecté ('Votre score'). Recherche de la sortie..."
                )

                # Cas normal : "Passer à la suite".
                if self.click_result_continue(wait=False):
                    continue

                # Fallback immédiat : Suivant / Skip / Validate.
                fallback = self.click_result_fallback(wait=False)
                if fallback is not None:
                    continue

                # Watchdog borné : on ne tourne jamais silencieusement.
                total_wait_ms = 0
                watchdog_limit_ms = 6500

                while total_wait_ms < watchdog_limit_ms:
                    self.logger.info(
                        "Résultat : CTA introuvable, nouvelle tentative (%sms/%sms).",
                        total_wait_ms,
                        watchdog_limit_ms,
                    )

                    self.page.wait_for_timeout(500)
                    total_wait_ms += 500

                    if self.click_result_continue(wait=False):
                        break

                    fallback = self.click_result_fallback(wait=False)
                    if fallback is not None:
                        break
                else:
                    self.logger.info(
                        "Résultat : aucun bouton exploitable après le watchdog."
                    )
                    self._save_blocked_diagnostic()
                    return {
                        "state": "finished_without_action",
                        "steps": step,
                        "screen_kind": kind,
                        "controls": self.debug_controls(),
                    }

                # Une action du watchdog a fonctionné : réanalyse de l'écran.
                continue

            if kind == "exercise":
                return {
                    "state": "question",
                    "steps": step,
                    "screen_kind": kind,
                }

            if kind == "flashcard":
                self.logger.info(
                    "Flow : flashcard détectée, parcours du carousel via "
                    "#tns-flashcards-next/#tns-flashcards-prev."
                )

                reached_next = self.swipe_flashcards_until_progress()

                if reached_next:
                    suivant, text, frame_url = self._find_exact_suivant()

                    if suivant is not None and self._click_and_confirm_progress(
                        suivant,
                        f"Suivant flashcards ({text})",
                        frame_url,
                        min_wait_ms=650,
                        max_wait_ms=4000,
                    ):
                        continue

                # Si le carousel n'a pas permis de faire apparaître Suivant,
                # on ne boucle pas silencieusement : fallback puis diagnostic.
                action = self.click_progress_action(wait=False)
                if action is not None:
                    continue

                self.logger.info(
                    "Flashcards : aucun 'Suivant' exploitable après parcours."
                )

            if kind == "memo":
                if self._advance_content_until_progress("memo"):
                    continue

            if kind == "audio":
                if self._advance_content_until_progress("audio"):
                    continue

            # Fallback transition / écran neutre
            action = self.click_progress_action(wait=False)
            if action is not None:
                continue

            action = self.click_progress_action(wait=True)
            if action is not None:
                continue

            self._save_blocked_diagnostic()
            return {
                "state": "blocked",
                "steps": step,
                "screen_kind": kind,
                "controls": self.debug_controls(),
            }

        self._save_blocked_diagnostic()
        return {
            "state": "max_steps",
            "steps": max_steps,
            "screen_kind": self.detect_screen_kind(),
            "controls": self.debug_controls(),
        }
