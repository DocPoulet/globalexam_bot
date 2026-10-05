from detector import clean_text


class ActivityActions:
    """
    Actions contrôlées sur l'activité courante.

    Cette version sait surtout interagir avec les éléments détectés.
    """

    def __init__(self, page):
        self.page = page

    def click_draggable(self, index):
        items = self.page.locator("button.draggable-item")

        if index < 0 or index >= items.count():
            return False

        items.nth(index).click()
        return True

    def drag_item(self, source_index, target_index):
        """
        Tente de déplacer un draggable vers un autre.

        Utile pour tester les exercices de classement.
        """
        items = self.page.locator("button.draggable-item")

        if source_index < 0 or target_index < 0:
            return False

        if source_index >= items.count() or target_index >= items.count():
            return False

        source = items.nth(source_index)
        target = items.nth(target_index)

        source.drag_to(target)
        return True

    def click_action(self, text):
        locator = self.page.get_by_role("button", name=text, exact=False)

        if locator.count() == 0:
            return False

        locator.first.click()
        return True
