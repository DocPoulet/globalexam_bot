import json
import hashlib
from datetime import datetime
from pathlib import Path

from common_actions import click_common_action
from autopilot_audit import AutoPilotAudit, QuestionRunGuard, safe_path


class AutoPilot:
    """
    Machine à états centrale.

    Le terminal n'est plus la "suite normale" du bot.
    Il n'est rendu à l'utilisateur que lorsque plusieurs tentatives
    déterministes n'ont produit aucun progrès.
    """

    def __init__(self, page, logger, launcher, flow, questions):
        self.page = page
        self.logger = logger
        self.launcher = launcher
        self.flow = flow
        self.questions = questions

        # Dernière question pour laquelle le rapport mémoire automatique
        # a été affiché. Permet de n'afficher le contrôle qu'une seule fois
        # par nouvelle question.
        self._last_memory_report_question_id = None
        self._question_guard = QuestionRunGuard()
        self._last_submitted_screen = None
        self.audit = AutoPilotAudit(
            Path(__file__).resolve().parent.parent / "logs", self.logger,
        )

    def _signature(self):
        try:
            text = self.flow._main_text()
        except Exception:
            text = ""

        # Compare tout le texte utile au lieu des 1800 premiers caractères.
        # Seule son empreinte est conservée dans la machine à états.
        content = (text or "")[:24000]
        return (
            safe_path(self.page.url),
            hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest(),
        )

    def _settle(self, min_ms=450, max_ms=2200, poll_ms=150):
        """
        Attend qu'une SPA arrête de changer pendant deux échantillons.
        """
        self.page.wait_for_timeout(min_ms)
        elapsed = min_ms
        previous = self._signature()
        stable = 0

        while elapsed < max_ms:
            self.page.wait_for_timeout(poll_ms)
            elapsed += poll_ms
            current = self._signature()

            if current == previous:
                stable += 1
                if stable >= 2:
                    return
            else:
                stable = 0
                previous = current

    def _save_diagnostic(self, reason):
        base_dir = Path(__file__).resolve().parent.parent / "diagnostics"
        base_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        payload = {
            "reason": reason,
            "url": self.page.url,
            "title": None,
            "screen_kind": None,
            "controls": [],
            "audit_trace": str(self.audit.path),
            "guarded_questions": self._question_guard.count(),
        }

        for name, function in (
            ("title", self.page.title),
            ("screen_kind", self.flow.detect_screen_kind),
            ("controls", self.flow.debug_controls),
        ):
            try:
                payload[name] = function()
            except Exception as exc:
                payload[name + "_error"] = str(exc)

        try:
            payload["question"] = self.questions.inspect(save_unknown=False)
        except Exception as exc:
            payload["question_error"] = str(exc)

        path = base_dir / f"autopilot_blocked_{stamp}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        try:
            self.page.screenshot(
                path=str(base_dir / f"autopilot_blocked_{stamp}.png"),
                full_page=True,
            )
        except Exception:
            pass

        self.logger.info("AutoPilot bloqué : diagnostic %s", path)
        return path

    def _handle_list(self):
        self.logger.info("AutoPilot état=LISTE")

        # Trois essais bornés. Pas de titre/card générique.
        for attempt in range(1, 4):
            self.logger.info(
                "AutoPilot : lancement exercice, tentative %s/3.",
                attempt,
            )

            if self.launcher.launch_first_available():
                self._settle()
                return True

            self.page.wait_for_timeout(700)

        return False

    def _auto_memory_report_for_new_question(self, packet=None):
        """
        Exécute automatiquement l'équivalent de `learnstats` lorsqu'une
        nouvelle question est détectée.

        Le question_id permet de distinguer deux questions successives même
        si GlobalExam conserve la même URL.
        """
        learner = getattr(self.questions, "learner", None)

        if learner is None:
            return

        try:
            packet = packet or self.questions.extract_packet()
        except Exception as exc:
            self.logger.info(
                "Mémoire auto : extraction question impossible : %s",
                exc,
            )
            return

        question_id = packet.get("question_id")
        if not question_id:
            return

        if question_id == self._last_memory_report_question_id:
            return

        self._last_memory_report_question_id = question_id

        try:
            stats = learner.stats()
        except Exception as exc:
            self.logger.info(
                "Mémoire auto : lecture learnstats impossible : %s",
                exc,
            )
            return

        self.logger.info(
            "=== AUTO LEARNSTATS | nouvelle question %s | type=%s ===",
            question_id,
            packet.get("exercise_type"),
        )
        self.logger.info(
            "Mémoire locale : questions=%s | tentatives=%s | "
            "réponses_apprises=%s | résultats=%s",
            stats.get("questions", 0),
            stats.get("attempts", 0),
            stats.get("learned_answers", 0),
            stats.get("outcomes", {}),
        )
        self.logger.info(
            "Mémoire vérifications : confirmées=%s anciennes_non_vérifiées=%s suggestions=%s litigieuses=%s",
            stats.get("verified_answers", 0),
            stats.get("legacy_unverified", 0),
            stats.get("provisional_suggestions", 0),
            stats.get("disputed_answers", 0),
        )
        self.logger.info(
            "Mémoire SQLite : %s",
            stats.get("database"),
        )

        # Petit history automatique : suffisamment pour vérifier que la
        # tentative précédente a bien été enregistrée sans inonder le log.
        try:
            rows = learner.recent_attempts(3)
        except Exception as exc:
            self.logger.info(
                "Mémoire auto : history impossible : %s",
                exc,
            )
            return

        if not rows:
            self.logger.info(
                "Mémoire auto : aucune tentative enregistrée pour le moment."
            )
            return

        for row in reversed(rows):
            instruction = (row.get("instruction") or "").replace("\n", " ")
            self.logger.info(
                "Mémoire auto history #%s : %s [%s] %s",
                row.get("id"),
                row.get("outcome"),
                row.get("exercise_type"),
                instruction[:100],
            )

    def _handle_question(self):
        """Traite une question au plus une fois ; trace chaque étape vérifiable."""
        self.logger.info("AutoPilot état=EXERCICE")
        marker = self.questions.wait_for_auto_marker_or_next(
            timeout_ms=3500,
            step_ms=120,
        )

        if marker == "next":
            before = self._signature()
            from_path = safe_path(self.page.url)
            clicked = click_common_action(self.page, "next")
            if clicked:
                self._settle()
            changed = clicked and self._signature() != before
            self.audit.emit(
                "navigation", action="suivant", status="confirmed" if changed else "unconfirmed",
                from_path=from_path, to_path=safe_path(self.page.url),
                confirmed=bool(changed),
            )
            return bool(changed)

        if marker != "question":
            self.logger.info("AutoPilot : aucun marqueur Passer/Validate après stabilisation.")
            self.audit.emit("block", reason="missing_question_marker", screen="exercise")
            return False

        # Le texte de feedback peut changer l'ID après validation.
        # Tant qu'aucun nouvel écran n'est apparu, une seconde réponse est bloquée.
        if self._last_submitted_screen == self._signature():
            self.audit.emit("duplicate_prevented", status="same_screen_after_submission",
                            reason="unchanged_post_submit_screen")
            return False

        # L'identifiant stable évite les doubles validations même si la page
        # conserve la même URL après un rendu asynchrone.
        try:
            packet = self.questions.extract_packet()
        except Exception as exc:
            self.logger.info("AutoPilot : extraction impossible : %s", exc)
            self.audit.emit("block", reason="question_packet_unavailable")
            return False

        qid = packet.get("question_id")
        key = self._question_guard.key(self.page.url, qid)
        if key is None:
            self.audit.emit("block", reason="missing_question_id")
            return False

        if not self._question_guard.begin(key):
            self.audit.emit(
                "duplicate_prevented", question_id=qid,
                status=self._question_guard.state(key), reason="already_attempted",
            )
            return False

        self._auto_memory_report_for_new_question(packet)
        self.audit.emit(
            "question_detected", question_id=qid,
            exercise_type=packet.get("exercise_type", "unknown"),
            from_path=safe_path(self.page.url),
        )
        before = self._signature()
        from_path = safe_path(self.page.url)
        try:
            result = self.questions.auto_answer_passer_exercise(advance=False)
        except Exception as exc:
            # Une exception pourrait survenir APRÈS un clic : ne pas retenter
            # automatiquement une soumission dont l'état est inconnu.
            self._question_guard.finish(key, "error_unknown_submission")
            self.logger.exception("AutoPilot : erreur pendant la réponse : %s", exc)
            self.audit.emit("exception", question_id=qid, error=type(exc).__name__)
            return False

        action_used = result.get("action")
        finish_action = result.get("finish_action")
        learning = result.get("learning") or {}
        self.audit.emit(
            "answer_used", question_id=qid, source=action_used or "none",
            steps=result.get("action_steps", 0),
            confidence=result.get("confidence"),
            status="applied" if action_used else "no_selection",
        )

        if not result.get("handled") or finish_action not in ("validate", "skip"):
            self._question_guard.finish(key, "unconfirmed_submission")
            self.audit.emit(
                "validation", question_id=qid, status="unconfirmed",
                reason=result.get("reason") or "no_finish_action",
                finish_action=finish_action,
            )
            # L'ancien moteur pouvait tenter "Suivant" ici, mais cela
            # dissimulait l'échec de validation : arrêt diagnostiqué préférable.
            return False

        self._question_guard.finish(key, "submitted")
        self.audit.emit(
            "validation", question_id=qid, status="clicked",
            finish_action=finish_action,
        )
        self.audit.emit(
            "correction", question_id=qid, outcome=learning.get("outcome", "unknown"),
            status=("saved" if learning.get("correction_saved") else
                    "not_available"),
            learned=bool(learning.get("learned", False)),
        )
        self.audit.emit(
            "sqlite", question_id=qid,
            attempt_id=learning.get("attempt_id"),
            status=("saved" if learning.get("attempt_id") else "not_confirmed"),
            learned=bool(learning.get("learned", False)),
            outcome=learning.get("outcome", "unknown"),
        )
        self.logger.info(
            "AutoPilot question : action=%s x%s fin=%s outcome=%s learned=%s",
            action_used, result.get("action_steps", 0), finish_action,
            learning.get("outcome"), learning.get("learned", False),
        )
        self._settle()
        after = self._signature()
        changed = after != before
        # Le prochain écran peut déjà être une NOUVELLE question : ne pas
        # le bloquer. La barrière "même écran" ne s'applique qu'en cas de
        # soumission sans progression observable.
        self._last_submitted_screen = after if not changed else None
        self.audit.emit(
            "navigation", question_id=qid, action=finish_action,
            status="confirmed" if changed else "unconfirmed",
            confirmed=changed, from_path=from_path,
            to_path=safe_path(self.page.url),
        )
        # Une validation sans changement visible n'est PAS la preuve que
        # l'exercice a progressé : le verrou interdit de la répéter.
        return changed

    def _handle_non_question(self, kind):
        self.logger.info("AutoPilot état=%s", kind.upper())

        result = self.flow.advance_until_question(max_steps=40)

        self.logger.info(
            "AutoPilot flow : state=%s steps=%s screen=%s",
            result.get("state"),
            result.get("steps"),
            result.get("screen_kind"),
        )

        self._settle()

        # Même un "blocked" du FlowController peut en réalité être la liste
        # d'exercices atteinte après une navigation. Le superviseur réévalue
        # toujours l'état global au tour suivant.
        if self.launcher.is_list_page():
            return True

        if result.get("state") == "question":
            return True

        if result.get("state") in ("blocked", "finished_without_action", "max_steps"):
            return False

        return True

    def run(self, max_cycles=10000):
        """
        Boucle autonome principale.

        On ne rend la main qu'après 3 cycles consécutifs sans progrès réel.
        """
        stagnant = 0
        self.audit.emit("run_start", status="started", from_path=safe_path(self.page.url))

        for cycle in range(1, max_cycles + 1):
            self._settle()
            before = self._signature()

            # Priorité absolue à la page liste.
            if self.launcher.is_list_page():
                progressed = self._handle_list()
                state = "list"
            else:
                kind = self.flow.detect_screen_kind()
                state = kind

                if kind == "exercise":
                    progressed = self._handle_question()
                else:
                    progressed = self._handle_non_question(kind)

            after = self._signature()

            # Une action peut être valide sans changer immédiatement la
            # signature ; 'progressed' compte donc aussi.
            if progressed and after != before:
                stagnant = 0
            elif progressed:
                stagnant += 1
            else:
                stagnant += 1

            self.logger.info(
                "AutoPilot cycle=%s état=%s progrès=%s stagnant=%s",
                cycle,
                state,
                progressed,
                stagnant,
            )

            if stagnant >= 3:
                reason = f"no_progress_3_cycles_state_{state}"
                self.audit.emit("block", reason=reason, cycle=cycle, screen=state)
                path = self._save_diagnostic(reason)
                self.audit.emit("run_end", status="blocked", count=cycle)
                return {
                    "state": "blocked",
                    "cycles": cycle,
                    "reason": reason,
                    "diagnostic": str(path),
                    "audit": str(self.audit.path),
                    "summary": self.audit.summary(),
                }

        self.audit.emit("run_end", status="max_cycles", count=max_cycles)
        path = self._save_diagnostic("max_cycles")
        return {
            "state": "max_cycles",
            "cycles": max_cycles,
            "reason": "max_cycles",
            "diagnostic": str(path),
            "audit": str(self.audit.path),
            "summary": self.audit.summary(),
        }
