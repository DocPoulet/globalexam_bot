"""Contrats d'adaptateurs indépendants du DOM de GlobalExam.

Futures implémentations pourront être versionnées par profil de site.
Aucun de ces adaptateurs n'agit sans implémentation validée.
"""
from abc import ABC, abstractmethod


class PageAdapter(ABC):
    """Reconnaît et extrait le contenu d'une famille d'écrans."""

    kind = "unknown"

    @abstractmethod
    def matches(self, page_snapshot):
        """Retourne True si le profil visuel correspond au type pris en charge."""

    @abstractmethod
    def inspect(self, page):
        """Retourne des données sémantiques, sans cliquer ni modifier la page."""


class ExerciseAdapter(PageAdapter):
    kind = "exercise"

    @abstractmethod
    def answer_contract(self, question):
        """Décrit les interactions permises pour répondre, sans les exécuter."""


class SiteProfile:
    """Choix de l'adaptateur selon les signatures structurelles capturées."""

    def __init__(self, adapters=()):
        self.adapters = list(adapters)

    def select(self, snapshot):
        for adapter in self.adapters:
            if adapter.matches(snapshot):
                return adapter
        return None
