from adapters import ADAPTERS


class AdapterRegistry:
    """
    Sélectionne automatiquement l'adaptateur le plus prioritaire
    correspondant à la page courante.
    """

    def __init__(self, page):
        self.page = page

    def detect(self):
        candidates = sorted(
            ADAPTERS,
            key=lambda cls: cls.priority,
            reverse=True,
        )

        for adapter_cls in candidates:
            adapter = adapter_cls(self.page)

            try:
                if adapter.matches():
                    return adapter
            except Exception:
                continue

        return None

    @staticmethod
    def available():
        return [
            {
                "name": cls.name,
                "priority": cls.priority,
            }
            for cls in sorted(
                ADAPTERS,
                key=lambda c: c.priority,
                reverse=True,
            )
        ]
