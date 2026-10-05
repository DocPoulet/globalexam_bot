from abc import ABC, abstractmethod


class ExerciseAdapter(ABC):
    """
    Interface commune à tous les types d'exercices.
    """

    name = "base"
    priority = 0

    def __init__(self, page):
        self.page = page

    @abstractmethod
    def matches(self):
        """Retourne True si l'adaptateur reconnaît l'exercice."""
        raise NotImplementedError

    @abstractmethod
    def analyze(self):
        """Retourne une représentation structurée de l'exercice."""
        raise NotImplementedError

    def actions(self):
        """Actions propres à l'adaptateur, à surcharger si nécessaire."""
        return {}
