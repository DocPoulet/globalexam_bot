import re
import hashlib
import json

from adapter_registry import AdapterRegistry
from common_actions import click_common_action, find_actions
from safety_clicks import normalize, is_forbidden_element, safe_click
from question_extractor import QuestionExtractor


class QuestionEngine:
    """
    API commune pour tous les formats de question.

    Cette version automatise la mécanique de réponse, pas le choix
    sémantique de la bonne réponse.
    """

    def __init__(self, page, logger, diagnostics=None, flow=None, learner=None, answer_engine=None):
        self.page = page
        self.logger = logger
        self.registry = AdapterRegistry(page)
        self.diagnostics = diagnostics
        self.flow = flow
        self.extractor = QuestionExtractor(page, logger)
        self.learner = learner
        self.answer_engine = answer_engine
        self._pending_packet = None

    def adapter(self):
        return self.registry.detect()

    def inspect(self, save_unknown=True):
        adapter = self.adapter()
        analysis = adapter.analyze()

        analysis["actions"] = [
            {
                "kind": action["kind"],
                "text": action["text"],
                "disabled": action["disabled"],
            }
            for action in find_actions(self.page)
        ]

        if (
            save_unknown
            and analysis.get("exercise_type") == "unknown"
            and self.diagnostics is not None
        ):
            self.diagnostics.save_unknown(
                self.page,
                analysis,
                reason="no_matching_adapter",
            )

        return analysis

    def extract_packet(self):
        """
        Produit le paquet sémantique standard destiné au futur LLM.
        Aucun clic n'est effectué.
        """
        analysis = self.inspect(save_unknown=False)
        actions = analysis.get("actions", [])
        return self.extractor.extract(analysis, actions=actions)

    def _start_attempt(self):
        """Mémorise la question AVANT la première interaction."""
        try:
            current = self.extract_packet()
        except Exception:
            return self._pending_packet

        if (
            self._pending_packet is None
            or self._pending_packet.get("question_id") != current.get("question_id")
        ):
            self._pending_packet = current

        return self._pending_packet

    def _answer_packet(self):
        try:
            return self.extract_packet()
        except Exception:
            return self._pending_packet

    def _finish_learning_validation(self, original_packet, answered_packet):
        if self.learner is None or original_packet is None or answered_packet is None:
            return None

        try:
            return self.learner.record_validation(
                self.page,
                original_packet,
                answered_packet,
            )
        except Exception as exc:
            self.logger.exception("Learner : erreur enregistrement validation : %s", exc)
            return {
                "outcome": "unknown",
                "learned": False,
                "error": str(exc),
            }

    def _find_exact_correction_action(self):
        """
        Cherche un contrôle interactif dont le libellé est exactement
        "Correction" dans le document principal et les frames.
        """
        frames = []
        try:
            frames = list(self.page.frames)
        except Exception:
            frames = [self.page]

        selectors = (
            "button",
            "[role='button']",
            "a",
            "[role='link']",
        )

        for frame in frames:
            for selector in selectors:
                try:
                    locator = frame.locator(selector)
                except Exception:
                    continue

                for i in range(min(locator.count(), 200)):
                    el = locator.nth(i)

                    try:
                        if not el.is_visible():
                            continue

                        if is_forbidden_element(el):
                            continue

                        text = (
                            (el.inner_text(timeout=800) or "").strip()
                            or (el.get_attribute("aria-label") or "").strip()
                            or (el.get_attribute("title") or "").strip()
                        )

                        if normalize(text) != "correction":
                            continue

                        try:
                            if el.is_disabled():
                                continue
                        except Exception:
                            pass

                        try:
                            if normalize(el.get_attribute("aria-disabled") or "") == "true":
                                continue
                        except Exception:
                            pass

                        return el, text
                    except Exception:
                        continue

        return None, None

    def _open_correction_and_learn(
        self,
        original_packet,
        answered_packet,
        learning,
    ):
        """
        Si GlobalExam propose explicitement "Correction", ouvre la correction
        et enrichit la tentative déjà enregistrée.

        Le bouton est traité comme un signal explicite qu'une correction
        détaillée est disponible.
        """
        if self.learner is None or original_packet is None:
            return learning

        if not re.search(r"/content/[^/]+/correction(?:[?#].*)?$", self.page.url):
            self.logger.info("Learner : attente de la route correction, sans présumer une erreur")
            return learning
        el, text = self._find_exact_correction_action()
        if el is None:
            return learning

        self.logger.info(
            "Learner : bouton 'Correction' détecté après validation."
        )

        before = ""
        try:
            before = self.learner._main_text(self.page)
        except Exception:
            pass

        if not safe_click(el, timeout=2500):
            self.logger.info(
                "Learner : impossible de cliquer sur 'Correction'."
            )
            return learning

        self.logger.info("Learner : clic sur 'Correction'.")
        self.page.wait_for_timeout(450)

        # Laisse le contenu de correction se rendre sans faire avancer
        # l'exercice.
        try:
            self.learner._wait_for_correction_render(
                self.page,
                before,
                timeout_ms=2600,
            )
        except Exception:
            self.page.wait_for_timeout(500)

        try:
            enriched = self.learner.record_explicit_correction(
                self.page,
                original_packet,
                answered_packet,
                attempt_id=(learning or {}).get("attempt_id"),
            )
        except Exception as exc:
            self.logger.exception(
                "Learner : erreur lecture correction explicite : %s",
                exc,
            )
            return learning

        if not learning:
            return enriched

        merged = dict(learning)
        merged.update({
            "outcome": merged.get("outcome", "unknown"),
            "correct_answer": enriched.get(
                "correct_answer",
                merged.get("correct_answer"),
            ),
            "learned": enriched.get("learned", merged.get("learned", False)),
            "explicit_correction": True,
            "correction_saved": enriched.get("correction_saved", False),
            "verification_status": enriched.get("verification_status"),
        })
        return merged

    def _finish_learning_skip(self, original_packet, answered_packet):
        if self.learner is None or original_packet is None or answered_packet is None:
            return None

        try:
            return self.learner.record_skip(
                self.page,
                original_packet,
                answered_packet,
            )
        except Exception as exc:
            self.logger.exception("Learner : erreur enregistrement skip : %s", exc)
            return {
                "outcome": "skipped",
                "learned": False,
                "error": str(exc),
            }

    def select(self, index):
        self._start_attempt()
        adapter = self.adapter()
        action = adapter.actions().get("select")

        if action is None:
            return {
                "ok": False,
                "reason": "select_not_supported",
                "analysis": adapter.analyze(),
            }

        ok = action(index)

        return {
            "ok": bool(ok),
            "reason": None if ok else "selection_failed",
            "analysis": self.adapter().analyze(),
        }

    def choose(self, field_index, option_index):
        self._start_attempt()
        adapter = self.adapter()
        action = adapter.actions().get("choose")

        if action is None:
            return {
                "ok": False,
                "reason": "choose_not_supported",
                "analysis": adapter.analyze(),
            }

        ok = action(field_index, option_index)

        return {
            "ok": bool(ok),
            "reason": None if ok else "choose_failed",
            "analysis": self.adapter().analyze(),
        }

    def fill(self, field_index, text):
        self._start_attempt()
        adapter = self.adapter()
        action = adapter.actions().get("fill")

        if action is None:
            return {
                "ok": False,
                "reason": "fill_not_supported",
                "analysis": adapter.analyze(),
            }

        ok = action(field_index, text)

        return {
            "ok": bool(ok),
            "reason": None if ok else "fill_failed",
            "analysis": self.adapter().analyze(),
        }

    def fallback(self, index):
        self._start_attempt()
        adapter = self.adapter()
        action = adapter.actions().get("drag_fallback")

        if action is None:
            return {
                "ok": False,
                "reason": "drag_fallback_not_supported",
                "analysis": adapter.analyze(),
            }

        try:
            ok = action(index)
        except Exception as exc:
            return {
                "ok": False,
                "reason": f"drag_fallback_exception:{exc}",
                "analysis": self.adapter().analyze(),
            }

        return {
            "ok": bool(ok),
            "reason": None if ok else "drag_fallback_failed",
            "analysis": self.adapter().analyze(),
        }

    def has_exact_skip_passer(self):
        """
        True si un bouton Skip actif affiche exactement "Passer".
        """
        for action in find_actions(self.page):
            if action["kind"] != "skip" or action["disabled"]:
                continue

            if normalize(action["text"]) == "passer":
                return True

        return False

    def has_validate_action(self):
        """
        True si une action Validate/Valider/Confirmer/etc. est visible.
        """
        for action in find_actions(self.page):
            if action["kind"] == "validate" and not action["disabled"]:
                return True

        return False

    def has_next_suivant(self):
        """
        True si une action Next affiche exactement "Suivant".
        """
        for action in find_actions(self.page):
            if action["kind"] != "next" or action["disabled"]:
                continue

            if normalize(action["text"]) == "suivant":
                return True

        return False

    def has_auto_question_marker(self):
        """
        Une question est considérée prête pour AutoQ si elle expose
        soit "Passer", soit une action Validate/Valider.
        """
        return self.has_exact_skip_passer() or self.has_validate_action()

    def wait_for_auto_marker_or_next(
        self,
        timeout_ms=1800,
        step_ms=120,
    ):
        """
        Attend brièvement la stabilisation de la question suivante.

        Retourne :
        - "next" si Suivant apparaît ;
        - "question" si Passer ou Validate apparaît ;
        - None sinon.
        """
        elapsed = 0

        while elapsed <= timeout_ms:
            if self.has_next_suivant():
                return "next"

            if self.has_auto_question_marker():
                return "question"

            if elapsed >= timeout_ms:
                break

            self.page.wait_for_timeout(step_ms)
            elapsed += step_ms

        return None

    def _state_signature(self):
        """
        Signature de l'état de la question.

        On combine :
        - URL
        - analyse de l'adaptateur
        - HTML du main

        Cela permet de voir si select/fallback a réellement modifié l'écran.
        """
        adapter = self.adapter()

        try:
            analysis = adapter.analyze()
        except Exception:
            analysis = {}

        try:
            root = self.page.locator("main")
            html = root.first.inner_html() if root.count() else self.page.content()
        except Exception:
            html = ""

        payload = json.dumps(
            {
                "url": self.page.url,
                "adapter": analysis,
                "html_hash": hashlib.sha256(
                    html.encode("utf-8", errors="ignore")
                ).hexdigest(),
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _try_semantic_answer(self, packet):
        """Tente mémoire/LLM puis applique la réponse avec l'adaptateur courant."""
        if self.answer_engine is None or packet is None:
            return {"worked": False, "reason": "answer_engine_disabled"}

        result = self.answer_engine.solve(packet)
        if not result.get("ok"):
            self.logger.info(
                "AnswerEngine : fallback AutoQ (%s)",
                result.get("reason"),
            )
            return {
                "worked": False,
                "reason": result.get("reason"),
                "source": result.get("source"),
            }

        answer = result.get("answer") or {}
        if answer.get("kind") != "choice_indices":
            return {"worked": False, "reason": "unsupported_answer_kind"}

        indices = answer.get("indices") or []
        adapter = self.adapter()
        select = adapter.actions().get("select")
        if select is None:
            return {"worked": False, "reason": "adapter_has_no_select"}

        steps = 0
        for idx in indices:
            try:
                ok = select(idx)
            except Exception as exc:
                self.logger.info(
                    "AnswerEngine : échec application index=%s : %s", idx, exc
                )
                return {
                    "worked": False,
                    "reason": f"select_exception:{exc}",
                    "steps": steps,
                }
            if not ok:
                return {
                    "worked": False,
                    "reason": f"select_failed:{idx}",
                    "steps": steps,
                }
            steps += 1

        self.logger.info(
            "AnswerEngine : réponse appliquée source=%s conf=%s indices=%s",
            result.get("source"),
            result.get("confidence"),
            indices,
        )
        return {
            "worked": steps > 0,
            "steps": steps,
            "source": result.get("source"),
            "confidence": result.get("confidence"),
            "reason": None,
        }

    def _attempt_repeated_action(self, action_name, max_steps=25):
        """
        Répète toujours l'action sur l'index 1 (index Python 0)
        tant que l'état change.

        Les signatures déjà vues empêchent les boucles de type checkbox
        coché/décoché/coché/décoché.
        """
        adapter = self.adapter()
        action = adapter.actions().get(action_name)

        if action is None:
            return {
                "worked": False,
                "steps": 0,
                "reason": f"{action_name}_not_supported",
            }

        seen = {self._state_signature()}
        changed_steps = 0

        for _ in range(max_steps):
            before = self._state_signature()

            try:
                ok = action(0)
            except Exception as exc:
                return {
                    "worked": changed_steps > 0,
                    "steps": changed_steps,
                    "reason": f"{action_name}_exception:{exc}",
                }

            if not ok:
                break

            self.page.wait_for_timeout(250)
            after = self._state_signature()

            # Aucun changement => l'action ne fait plus rien.
            if after == before:
                break

            changed_steps += 1

            # Cycle détecté => stop immédiatement.
            if after in seen:
                break

            seen.add(after)

        return {
            "worked": changed_steps > 0,
            "steps": changed_steps,
            "reason": None,
        }

    def auto_answer_passer_exercise(self, advance=True):
        """
        Heuristique automatique demandée :

        1. si "Passer" n'est pas visible => ne rien faire ;
        2. essayer select 1 ;
        3. si select 1 ne change rien => essayer fallback 1 ;
        4. répéter l'action qui fonctionne jusqu'à stabilisation ;
        5. tenter Validate ;
        6. si Validate ne fonctionne pas => Skip.
        """
        if not self.has_auto_question_marker():
            return {
                "handled": False,
                "reason": "no_passer_or_validate",
            }

        self.logger.info(
            "AutoQ : marqueur d'exercice détecté (Passer ou Validate)."
        )

        original_packet = self._start_attempt()

        semantic = self._try_semantic_answer(original_packet)
        if semantic.get("worked"):
            action_used = semantic.get("source") or "answer_engine"
            action_steps = semantic.get("steps", 0)
        else:
            selected = self._attempt_repeated_action("select")

            if selected["worked"]:
                action_used = "select"
                action_steps = selected["steps"]
            else:
                fallback = self._attempt_repeated_action("drag_fallback")

                if fallback["worked"]:
                    action_used = "drag_fallback"
                    action_steps = fallback["steps"]
                else:
                    action_used = None
                    action_steps = 0

        self.logger.info(
            "AutoQ : action=%s étapes=%s",
            action_used,
            action_steps,
        )

        # Validation prioritaire.
        answered_packet = self._answer_packet()
        validated = click_common_action(self.page, "validate")

        if validated:
            self.logger.info("AutoQ : validation effectuée.")
            self.page.wait_for_timeout(450)

            learning = self._finish_learning_validation(
                original_packet,
                answered_packet,
            )

            # Une mauvaise réponse peut faire apparaître un bouton
            # "Correction". On l'ouvre AVANT tout changement d'écran afin
            # d'enregistrer la vraie solution.
            if (learning or {}).get("outcome") == "incorrect":
                learning = self._open_correction_and_learn(
                    original_packet,
                    answered_packet,
                    learning,
                )

            self._pending_packet = None

            flow_result = None
            if advance and self.flow is not None:
                flow_result = self.flow.advance_until_question()

            return {
                "handled": True,
                "action": action_used,
                "action_steps": action_steps,
                "confidence": semantic.get("confidence") if semantic.get("worked") else None,
                "finish_action": "validate",
                "flow": flow_result,
                "learning": learning,
            }

        # Aucun bouton validate utilisable => skip.
        skipped = click_common_action(self.page, "skip")

        if skipped:
            self.logger.info("AutoQ : validate absent/inefficace => Skip.")
            self.page.wait_for_timeout(250)

            learning = self._finish_learning_skip(
                original_packet,
                answered_packet,
            )
            self._pending_packet = None

            flow_result = None
            if advance and self.flow is not None:
                flow_result = self.flow.advance_until_question()

            return {
                "handled": True,
                "action": action_used,
                "action_steps": action_steps,
                "confidence": semantic.get("confidence") if semantic.get("worked") else None,
                "finish_action": "skip",
                "flow": flow_result,
                "learning": learning,
            }

        return {
            "handled": True,
            "action": action_used,
            "action_steps": action_steps,
            "finish_action": None,
            "flow": None,
            "reason": "no_validate_or_skip",
        }

    def validate(self):
        original_packet = self._start_attempt()
        answered_packet = self._answer_packet()
        ok = click_common_action(self.page, "validate")

        if not ok:
            return {
                "ok": False,
                "reason": "validate_button_not_found",
            }

        self.page.wait_for_timeout(450)
        learning = self._finish_learning_validation(
            original_packet,
            answered_packet,
        )

        if (learning or {}).get("outcome") == "incorrect":
            learning = self._open_correction_and_learn(
                original_packet,
                answered_packet,
                learning,
            )

        self._pending_packet = None

        flow_result = None
        if self.flow is not None:
            flow_result = self.flow.advance_until_question()

        return {
            "ok": True,
            "reason": None,
            "flow": flow_result,
            "learning": learning,
        }

    def skip(self, advance=True):
        original_packet = self._start_attempt()
        answered_packet = self._answer_packet()
        ok = click_common_action(self.page, "skip")

        if not ok:
            return {
                "ok": False,
                "reason": "skip_button_not_found",
            }

        self.page.wait_for_timeout(250)
        learning = self._finish_learning_skip(
            original_packet,
            answered_packet,
        )
        self._pending_packet = None

        flow_result = None
        if advance and self.flow is not None:
            flow_result = self.flow.advance_until_question()

        return {
            "ok": True,
            "reason": None,
            "flow": flow_result,
            "learning": learning,
        }

    def learned_answer_for_current(self):
        if self.learner is None:
            return None

        packet = self.extract_packet()
        return self.learner.lookup(packet.get("question_id"))
