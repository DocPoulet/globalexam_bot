"""Pont minimal entre le nouveau catalogue et l'ancien moteur d'exercices.

Seule la sélection dans /levels/content est spécifique à la nouvelle UI.
Aucun ancien sélecteur de menu n'est utilisé par ce lanceur.
"""
from exercise_launcher import ExerciseLauncher
from site_v2.catalog import module_list, ensure_module_open, list_activities, open_completed_activity
from site_v2.page_router import kind_from_url


class NewCatalogLauncher(ExerciseLauncher):
    """Lance des activités ordinaires en cours, puis laisse agir AutoPilot.

    Les activités terminées peuvent être autorisées sur demande explicite,
    sans être relancées plusieurs fois dans la même session automatique.
    """

    def __init__(self, page, logger, allow_completed=False):
        super().__init__(page, logger)
        self.allow_completed = bool(allow_completed)
        self._visited = set()
        self._failed = set()

    def is_list_page(self):
        """Reconnaît exactement /levels/content (pas seulement /levels/content/)."""
        return kind_from_url(self.page.url) == "catalog"

    def _module_numbers(self):
        """Modules ouverts d'abord, dans l'ordre du parcours."""
        modules = module_list(self.page)
        opened = [m["number"] for m in modules if m.get("expanded")]
        closed = [m["number"] for m in modules if not m.get("expanded")]
        return opened + closed

    @staticmethod
    def _task_key(module_number, activity):
        return (int(module_number), str(activity.get("title", "")))

    def _on_activity(self):
        return kind_from_url(self.page.url) in ("exercise", "result", "correction")

    def _confirm_open(self, timeout_ms=3800):
        """Un clic n'est pas une ouverture : la route d'activité doit apparaître."""
        for _ in range(max(1, timeout_ms // 200)):
            if self._on_activity():
                return True
            self.page.wait_for_timeout(200)
        return self._on_activity()

    def _attempt(self, module_number, item):
        key = self._task_key(module_number, item)
        self.logger.info(
            "Catalogue V2 : module=%s activité=%s état=%s",
            module_number, item.get("title"), item.get("state"),
        )
        before = self.page.url
        action = open_completed_activity(self.page, module_number, item["index"])
        if not action.get("ok"):
            self._failed.add(key)
            self.logger.info(
                "Catalogue V2 : refus/ouverture impossible '%s' : %s",
                item.get("title"), action.get("reason"),
            )
            return False

        if not self._confirm_open():
            # Évite de choisir la même carte en boucle si le clic n'a rien fait.
            self._failed.add(key)
            self.logger.info(
                "Catalogue V2 : clic effectué sans activité confirmée : %s (route=%s)",
                item.get("title"), self.page.url,
            )
            return False

        self._visited.add(key)
        self.logger.info(
            "Catalogue V2 : activité ouverte depuis %s -> %s",
            before, self.page.url,
        )
        return True

    def launch_first_available(self):
        """Sélectionne un exercice ordinaire (jamais verrouillé/spécial)."""
        if self._on_activity():
            return True
        if not self.is_list_page():
            self.logger.info("Catalogue V2 : pas sur /levels/content, aucun clic.")
            return False

        modules = self._module_numbers()
        if not modules:
            self.logger.info("Catalogue V2 : aucun module visible.")
            return False

        states = ("in_progress", "completed") if self.allow_completed else ("in_progress",)
        # Globalement, priorité aux activités en cours (et non à la première
        # terminée du premier module). On explore donc par état, puis module.
        for wanted_state in states:
            for number in modules:
                if not self.is_list_page():
                    return self._on_activity()
                if not ensure_module_open(self.page, number):
                    continue
                result = list_activities(self.page, number)
                if not result.get("ok"):
                    continue
                for item in result.get("activities", []):
                    if item.get("state") != wanted_state:
                        continue
                    key = self._task_key(number, item)
                    if key in self._visited or key in self._failed:
                        continue
                    if self._attempt(number, item):
                        return True
                    if not self.is_list_page():
                        # Une navigation intermédiaire n'autorise pas à cliquer
                        # sur une carte de l'ancien catalogue devenu obsolète.
                        return self._on_activity()

        self.logger.info(
            "Catalogue V2 : plus d'activité admissible non essayée "
            "(états=%s, déjà ouvertes=%s, échecs=%s).",
            states, len(self._visited), len(self._failed),
        )
        return False

    def describe_menus(self):
        """Compatibilité de l'ancienne commande `menus`."""
        return [
            {"index": item["number"], "text": item["title"],
             "visible": True, "expanded": item["expanded"]}
            for item in module_list(self.page)
        ]

    def describe_blocks(self):
        """Compatibilité de l'ancienne commande `blocks` sur un module ouvert."""
        result = []
        for module in module_list(self.page):
            if not module.get("expanded"):
                continue
            found = list_activities(self.page, module["number"])
            for activity in found.get("activities", []):
                result.append({
                    "index": activity["index"],
                    "text": f"Module {module['number']} · {activity['title']} · {activity['state']}",
                    "checkpoint": False,
                    "visible": True,
                })
        return result
