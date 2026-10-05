from enum import Enum, auto
from exercise_detector import detect_exercise


class State(Enum):
    ANALYZE = auto()
    WAITING_FOR_ANSWER = auto()
    ANSWER_SELECTED = auto()
    VALIDATED = auto()
    READY_FOR_NEXT = auto()
    UNKNOWN = auto()


class ExerciseStateMachine:
    """
    Machine à états pour piloter un exercice.
    """

    def __init__(self, page, logger, tracker=None):
        self.page = page
        self.logger = logger
        self.tracker = tracker
        self.state = State.ANALYZE

    def print_status(self, exercise):
        print("\n=== Analyse ===")
        print(f"État : {self.state.name}")
        print(f"Type : {exercise['type']}")
        print(
            f"Question : "
            f"{exercise['question'] or 'Non détectée'}"
        )

        if exercise["answers"]:
            print("\nRéponses :")
            for i, answer in enumerate(
                exercise["answers"],
                start=1
            ):
                print(
                    f"{i}. {answer['text']} "
                    f"[{answer['kind']}]"
                )

        if exercise["feedback"]:
            print("\nFeedback détecté :")
            for line in exercise["feedback"]:
                print(f"- {line}")

        if exercise["actions"]:
            print("\nActions :")
            for action in exercise["actions"]:
                print(
                    f"- {action['text']} "
                    f"[{action['kind']}]"
                )

    def _record_error(self, message):
        if self.tracker:
            self.tracker.record_error(message)

    def _click_answer(self, answer):
        kind = answer.get("kind")

        try:
            if kind in ("radio", "checkbox"):
                label_index = answer.get("label_index")

                if label_index is not None:
                    labels = self.page.locator("label")
                    if label_index < labels.count():
                        labels.nth(label_index).click()

                        if self.tracker:
                            self.tracker.record_answer(
                                answer.get("text", "")
                            )

                        return True

                input_index = answer.get("input_index")

                if input_index is not None:
                    inputs = self.page.locator(
                        "input[type='radio'], "
                        "input[type='checkbox']"
                    )

                    if input_index < inputs.count():
                        inputs.nth(input_index).click()

                        if self.tracker:
                            self.tracker.record_answer(
                                answer.get("text", "")
                            )

                        return True

            if kind == "button":
                button_index = answer.get(
                    "button_index",
                    0
                )

                buttons = self.page.locator(
                    "[class*='answer'] button, "
                    "[class*='option'] button, "
                    "[role='option']"
                )

                if button_index < buttons.count():
                    buttons.nth(button_index).click()

                    if self.tracker:
                        self.tracker.record_answer(
                            answer.get("text", "")
                        )

                    return True

        except Exception as exc:
            self._record_error(exc)
            self.logger.exception(
                "Échec lors du clic sur une réponse."
            )

        return False

    def select_answer_interactive(self, exercise):
        answers = exercise.get("answers", [])

        if not answers:
            print("Aucune réponse sélectionnable détectée.")
            self.state = State.UNKNOWN
            return

        self.print_status(exercise)

        try:
            value = int(
                input(
                    "\nNuméro de la réponse "
                    "à sélectionner : "
                )
            )
            index = value - 1
        except ValueError:
            print("Entrée invalide.")
            return

        if index < 0 or index >= len(answers):
            print("Index hors limites.")
            return

        if self._click_answer(answers[index]):
            print(
                "Réponse sélectionnée : "
                f"{answers[index]['text']}"
            )
            self.state = State.ANSWER_SELECTED
        else:
            print(
                "Impossible de cliquer sur cette réponse."
            )
            self.state = State.UNKNOWN

    def _find_action_button(self, kind):
        exercise = detect_exercise(self.page)

        for action in exercise.get("actions", []):
            if action["kind"] != kind:
                continue

            target_text = action["text"]

            locator = self.page.get_by_role(
                "button",
                name=target_text,
                exact=False,
            )

            if locator.count() > 0:
                return locator.first

            fallback = self.page.locator(
                "button, [role='button'], "
                "input[type='submit']"
            ).filter(has_text=target_text)

            if fallback.count() > 0:
                return fallback.first

        return None

    def click_validate(self):
        button = self._find_action_button(
            "validate"
        )

        if button is None:
            print(
                "Bouton de validation non détecté."
            )
            return False

        try:
            button.click()
            self.page.wait_for_timeout(500)

            if self.tracker:
                self.tracker.record_validation()

            print("Validation effectuée.")
            self.state = State.VALIDATED
            return True

        except Exception as exc:
            self._record_error(exc)
            self.logger.exception(
                "Échec validation : %s",
                exc
            )
            print(
                "Impossible de cliquer sur Valider."
            )
            self.state = State.UNKNOWN
            return False

    def click_next(self):
        button = self._find_action_button(
            "next"
        )

        if button is None:
            print("Bouton suivant non détecté.")
            return False

        try:
            button.click()
            self.page.wait_for_timeout(500)

            if self.tracker:
                self.tracker.record_next()

            print(
                "Passage à la question suivante."
            )
            self.state = State.ANALYZE
            return True

        except Exception as exc:
            self._record_error(exc)
            self.logger.exception(
                "Échec suivant : %s",
                exc
            )
            print(
                "Impossible de cliquer sur Suivant."
            )
            self.state = State.UNKNOWN
            return False

    def step(self):
        exercise = detect_exercise(self.page)

        if self.tracker:
            self.tracker.record_analysis(exercise)

        self.print_status(exercise)

        has_validate = any(
            action["kind"] == "validate"
            for action in exercise.get(
                "actions",
                []
            )
        )

        has_next = any(
            action["kind"] == "next"
            for action in exercise.get(
                "actions",
                []
            )
        )

        if exercise.get("feedback") and has_next:
            self.state = State.READY_FOR_NEXT
            print(
                "\nÉtape auto : "
                "feedback détecté -> suivant"
            )
            self.click_next()
            return detect_exercise(self.page)

        if has_next and not has_validate:
            self.state = State.READY_FOR_NEXT
            print(
                "\nÉtape auto : "
                "bouton suivant disponible"
            )
            self.click_next()
            return detect_exercise(self.page)

        if exercise.get("answers"):
            if self.state in (
                State.ANALYZE,
                State.WAITING_FOR_ANSWER,
            ):
                print(
                    "\nÉtape auto : sélection "
                    "de la première réponse (test)."
                )

                if self._click_answer(
                    exercise["answers"][0]
                ):
                    self.state = (
                        State.ANSWER_SELECTED
                    )
                    return detect_exercise(
                        self.page
                    )

        if (
            self.state == State.ANSWER_SELECTED
            and has_validate
        ):
            print(
                "\nÉtape auto : validation."
            )
            self.click_validate()
            return detect_exercise(self.page)

        if has_validate:
            self.state = (
                State.WAITING_FOR_ANSWER
            )
            print(
                "\nLe bot attend "
                "une réponse sélectionnée."
            )
        else:
            self.state = State.UNKNOWN
            print("\nÉtat non reconnu.")

        return exercise
