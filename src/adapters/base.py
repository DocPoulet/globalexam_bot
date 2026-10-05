from abc import ABC, abstractmethod


class ExerciseAdapter(ABC):
    name = "base"
    priority = 0

    def __init__(self, page):
        self.page = page

    @abstractmethod
    def matches(self):
        raise NotImplementedError

    @abstractmethod
    def analyze(self):
        raise NotImplementedError

    def select(self, index):
        return False

    def actions(self):
        return {}
