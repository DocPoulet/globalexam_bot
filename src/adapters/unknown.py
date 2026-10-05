from .base import ExerciseAdapter
from dom_utils import extract_question_text


class UnknownAdapter(ExerciseAdapter):
    name = "unknown"
    priority = -999

    def matches(self):
        return True

    def analyze(self):
        return {
            "adapter": self.name,
            "exercise_type": "unknown",
            "question": extract_question_text(self.page),
            "answers": [],
        }
