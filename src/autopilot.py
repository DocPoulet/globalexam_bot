import json
from datetime import datetime
from pathlib import Path

from common_actions import click_common_action


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

    def _signature(self):
        try:
            text = self.flow._main_text()
        except Exception:
            text = ""

        return (
            self.page.url,
            (text or "")[:1800],
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
            "title": self.page.title(),
            "screen_kind": self.flow.detect_screen_kind(),
            "controls": self.flow.debug_controls(),
        }

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

    def _handle_question(self):
        self.logger.info("AutoPilot état=EXERCICE")

        # Laisse le temps à Passer / Validate / Suivant de finir de rendre.
        marker = self.questions.wait_for_auto_marker_or_next(
            timeout_ms=3500,
            step_ms=120,
        )

        if marker == "next":
            self.logger.info("AutoPilot : Suivant détecté sur exercice.")
            if click_common_action(self.page, "next"):
                self._settle()
                return True
            return False

        if marker != "question":
            self.logger.info(
                "AutoPilot : aucun marqueur Passer/Validate après stabilisation."
            )
            return False

        result = self.questions.auto_answer_passer_exercise(advance=False)

        learning = result.get("learning") or {}
        self.logger.info(
            "AutoPilot question : action=%s x%s fin=%s outcome=%s learned=%s",
            result.get("action"),
            result.get("action_steps", 0),
            result.get("finish_action"),
            learning.get("outcome"),
            learning.get("learned", False),
        )

        if not result.get("handled"):
            return False

        if result.get("finish_action") is None:
            # Un Suivant peut apparaître juste après les sélections.
            self.page.wait_for_timeout(450)
            if self.questions.has_next_suivant():
                if click_common_action(self.page, "next"):
                    self._settle()
                    return True
            return False

        self._settle()
        return True

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
                path = self._save_diagnostic(reason)
                return {
                    "state": "blocked",
                    "cycles": cycle,
                    "reason": reason,
                    "diagnostic": str(path),
                }

        path = self._save_diagnostic("max_cycles")
        return {
            "state": "max_cycles",
            "cycles": max_cycles,
            "reason": "max_cycles",
            "diagnostic": str(path),
        }
