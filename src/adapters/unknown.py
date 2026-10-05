from .base import ExerciseAdapter


class UnknownAdapter(ExerciseAdapter):
    name = "unknown"
    priority = -999

    def matches(self):
        return True

    def analyze(self):
        return {
            "adapter": self.name,
            "exercise_type": "unknown",
            "question": None,
            "answers": [],
        }
