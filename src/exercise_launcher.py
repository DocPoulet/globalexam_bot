from urllib.parse import urljoin
import random
import unicodedata

ACTIVITY_MARKERS = ("/activity/", "/activities/")

START_WORDS = (
    "commencer", "continuer", "lancer", "démarrer", "demarrer",
    "start", "continue", "launch",
)

EXCLUDED_CONTENT = (
    "conversation ia",
    "conversation avec l ia",
    "conversation avec l'ia",
    "conversation ai",
    "ai conversation",
    "je relève le défi",
    "je releve le defi",
)

GENERIC_IGNORE = (
    "certification",
    "kiosque",
    "test de niveau",
    "formulaire de retour",
    "service clients",
)

CHECKPOINT_WORDS = (
    "checkpoint",
    "point de contrôle",
    "point de controle",
)

MENU_REQUIRED_CLASSES = (
    "card",
    "overflow-hidden",
    "scroll-below-chrome",
)

EXERCISE_REQUIRED_CLASSES = (
    "mb-10",
    "lg:mb-16",
)


def normalize(text):
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


class ExerciseLauncher:
    """
    Lance un vrai exercice GlobalExam à partir d'UN seul menu de contenu.

    Règle v0.7.8 :
    - s'il existe déjà un menu ouvert, on utilise celui-ci ;
    - sinon on choisit un menu au hasard et on l'ouvre ;
    - on lance ensuite le premier exercice normal de CE menu ;
    - checkpoint uniquement si ce menu ne contient aucun exercice normal.
    """

    def __init__(self, page, logger):
        self.page = page
        self.logger = logger

    # ---------------------------------------------------------------
    # OUTILS
    # ---------------------------------------------------------------

    def _is_visible(self, locator):
        try:
            return locator.is_visible()
        except Exception:
            return False

    def _is_disabled(self, locator):
        try:
            return locator.is_disabled()
        except Exception:
            return False

    def _current_is_activity(self):
        return "/activity/" in self.page.url.lower()

    def _is_excluded_text(self, text):
        value = normalize(text)
        return any(normalize(marker) in value for marker in EXCLUDED_CONTENT)

    def _is_generic_ignored(self, text):
        value = normalize(text)
        return any(normalize(marker) in value for marker in GENERIC_IGNORE)

    def _is_checkpoint_text(self, text):
        value = normalize(text)
        return any(normalize(marker) in value for marker in CHECKPOINT_WORDS)

    def _has_classes(self, element, required):
        try:
            return element.evaluate(
                """(e, classes) => classes.every(c => e.classList.contains(c))""",
                list(required),
            )
        except Exception:
            return False

    def _text(self, element):
        try:
            return element.inner_text().strip()
        except Exception:
            return ""

    # ---------------------------------------------------------------
    # MENUS
    # ---------------------------------------------------------------

    def _content_menus(self):
        """
        Menus du corps :
        class contient simultanément
        card + overflow-hidden + scroll-below-chrome
        """
        locator = self.page.locator('[class~="card"]')
        result = []

        for i in range(locator.count()):
            menu = locator.nth(i)

            if not self._has_classes(menu, MENU_REQUIRED_CLASSES):
                continue

            if not self._is_visible(menu):
                continue

            text = self._text(menu)

            if self._is_excluded_text(text):
                continue

            result.append(menu)

        return result

    def _menu_is_expanded(self, menu):
        """
        Détermine si CE menu est actuellement ouvert.
        """

        # 1. aria-expanded directement sur la carte
        try:
            value = menu.get_attribute("aria-expanded")
            if value == "true":
                return True
            if value == "false":
                return False
        except Exception:
            pass

        # 2. contrôle interne aria-expanded
        try:
            controls = menu.locator(
                'button[aria-expanded], [role="button"][aria-expanded]'
            )
            for i in range(controls.count()):
                value = controls.nth(i).get_attribute("aria-expanded")
                if value == "true":
                    return True
                if value == "false":
                    return False
        except Exception:
            pass

        # 3. présence d'un bloc exercice visible à l'intérieur
        try:
            candidates = menu.locator('[class~="mb-10"]')
            for i in range(candidates.count()):
                item = candidates.nth(i)

                if (
                    self._has_classes(item, EXERCISE_REQUIRED_CLASSES)
                    and self._is_visible(item)
                ):
                    return True
        except Exception:
            pass

        return False

    def _expanded_menu(self):
        """
        Retourne le premier menu actuellement ouvert.
        La page ne doit en avoir qu'un à la fois.
        """
        for menu in self._content_menus():
            if self._menu_is_expanded(menu):
                return menu

        return None

    def _click_menu(self, menu):
        """
        Ouvre un menu fermé.
        """

        if self._menu_is_expanded(menu):
            return True

        try:
            menu.scroll_into_view_if_needed()
        except Exception:
            pass

        # Priorité au toggle interne.
        controls = menu.locator(
            'button[aria-expanded="false"], '
            '[role="button"][aria-expanded="false"], '
            'summary'
        )

        for i in range(controls.count()):
            control = controls.nth(i)

            if not self._is_visible(control) or self._is_disabled(control):
                continue

            try:
                control.click()
                self.page.wait_for_timeout(500)

                if self._menu_is_expanded(menu):
                    return True
            except Exception:
                pass

        # Sinon clic direct sur la card.
        try:
            menu.click()
            self.page.wait_for_timeout(500)
            return self._menu_is_expanded(menu)
        except Exception:
            return False

    def choose_active_menu(self):
        """
        1. Réutilise le menu déjà ouvert s'il existe.
        2. Sinon choisit un menu au hasard et l'ouvre.
        """
        opened = self._expanded_menu()

        if opened is not None:
            self.logger.info(
                "Menu déjà ouvert utilisé : %s",
                self._text(opened)[:120],
            )
            return opened

        menus = self._content_menus()

        if not menus:
            self.logger.info("Aucun menu de contenu détecté.")
            return None

        menu = random.choice(menus)

        self.logger.info(
            "Aucun menu ouvert. Choix aléatoire : %s",
            self._text(menu)[:120],
        )

        if not self._click_menu(menu):
            self.logger.info("Impossible d'ouvrir le menu choisi.")
            return None

        # Le DOM peut être réorganisé après clic.
        # On récupère à nouveau le menu officiellement ouvert.
        self.page.wait_for_timeout(250)
        opened = self._expanded_menu()

        return opened if opened is not None else menu

    def describe_menus(self):
        result = []

        for index, menu in enumerate(self._content_menus(), start=1):
            result.append({
                "index": index,
                "text": self._text(menu)[:500],
                "visible": self._is_visible(menu),
                "expanded": self._menu_is_expanded(menu),
            })

        return result

    # ---------------------------------------------------------------
    # EXERCICES D'UN MENU DONNÉ
    # ---------------------------------------------------------------

    def _exercise_blocks_in_menu(self, menu, include_checkpoint=True):
        """
        Ne cherche JAMAIS globalement.
        Les exercices doivent appartenir au menu sélectionné/ouvert.
        """
        locator = menu.locator('[class~="mb-10"]')

        normal = []
        checkpoints = []

        for i in range(locator.count()):
            block = locator.nth(i)

            if not self._has_classes(block, EXERCISE_REQUIRED_CLASSES):
                continue

            if not self._is_visible(block):
                continue

            text = self._text(block)

            if self._is_excluded_text(text):
                continue

            if self._is_generic_ignored(text):
                continue

            if self._is_checkpoint_text(text):
                checkpoints.append(block)
            else:
                normal.append(block)

        if include_checkpoint:
            return normal + checkpoints

        return normal

    def describe_blocks(self):
        """
        Affiche uniquement les exercices du menu actuellement ouvert.
        """
        menu = self._expanded_menu()

        if menu is None:
            return []

        result = []

        blocks = self._exercise_blocks_in_menu(
            menu,
            include_checkpoint=True,
        )

        for index, block in enumerate(blocks, start=1):
            text = self._text(block)

            result.append({
                "index": index,
                "text": text[:500],
                "checkpoint": self._is_checkpoint_text(text),
                "visible": self._is_visible(block),
            })

        return result

    # ---------------------------------------------------------------
    # LANCEMENT D'UN BLOC
    # ---------------------------------------------------------------

    def _try_activity_link_in_block(self, block):
        links = block.locator("a[href]")

        for i in range(links.count()):
            link = links.nth(i)

            if not self._is_visible(link):
                continue

            href = link.get_attribute("href") or ""

            if not any(marker in href.lower() for marker in ACTIVITY_MARKERS):
                continue

            text = self._text(link)

            if self._is_excluded_text(text):
                continue

            self.logger.info(
                "Lien activité trouvé : %s",
                text or href,
            )

            try:
                link.click()
                self.page.wait_for_timeout(800)
            except Exception:
                try:
                    self.page.goto(
                        urljoin(self.page.url, href),
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    self.page.wait_for_timeout(800)
                except Exception:
                    continue

            if self._current_is_activity():
                return True

        return False

    def _start_controls_in_block(self, block):
        result = []

        normalized_start_words = tuple(normalize(x) for x in START_WORDS)

        for selector in ("button", "[role='button']", "a"):
            locator = block.locator(selector)

            for i in range(locator.count()):
                el = locator.nth(i)

                if not self._is_visible(el) or self._is_disabled(el):
                    continue

                text = (
                    self._text(el)
                    or (el.get_attribute("aria-label") or "").strip()
                )

                if not text or self._is_excluded_text(text):
                    continue

                lowered = normalize(text)

                if lowered in normalized_start_words:
                    score = 100
                elif any(word in lowered for word in normalized_start_words):
                    score = 60
                else:
                    continue

                result.append((score, selector, i, text))

        result.sort(key=lambda item: item[0], reverse=True)
        return result

    def _try_start_control_in_block(self, block):
        for _, selector, index, text in self._start_controls_in_block(block):
            locator = block.locator(selector).nth(index)

            if not self._is_visible(locator) or self._is_disabled(locator):
                continue

            self.logger.info(
                "Bouton lancement : %s",
                text,
            )

            try:
                locator.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                locator.click()
                self.page.wait_for_timeout(900)
            except Exception:
                continue

            if self._current_is_activity():
                return True

            if self._try_activity_link_in_block(block):
                return True

        return False

    def _page_state(self):
        return {
            "url": self.page.url,
            "title": self.page.title(),
        }

    def _wait_after_launch_click(self):
        """
        Attend brièvement une navigation ou une mise à jour SPA.
        """
        try:
            self.page.wait_for_timeout(900)
        except Exception:
            pass

        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass

    def _clickable_descendants(self, block):
        """
        Retourne les descendants susceptibles d'être le vrai contrôle
        d'ouverture de l'exercice.

        On inclut notamment les wrappers Vue/SPA avec cursor-pointer,
        tabindex ou role=button.
        """
        selectors = (
            "a[href]",
            "button",
            "[role='button']",
            "[tabindex='0']",
            "[class*='cursor-pointer']",
        )

        result = []
        seen = set()

        for selector in selectors:
            locator = block.locator(selector)

            for i in range(locator.count()):
                el = locator.nth(i)

                try:
                    if not el.is_visible():
                        continue
                except Exception:
                    continue

                try:
                    disabled = el.is_disabled()
                except Exception:
                    disabled = False

                if disabled:
                    continue

                try:
                    text = (
                        el.inner_text().strip()
                        or (el.get_attribute("aria-label") or "").strip()
                    )
                except Exception:
                    text = ""

                if self._is_excluded_text(text):
                    continue

                # Evite les doublons quand un même élément matche plusieurs sélecteurs.
                try:
                    signature = el.evaluate(
                        """(e) => [
                            e.tagName,
                            e.getAttribute('href') || '',
                            e.getAttribute('role') || '',
                            e.getAttribute('tabindex') || '',
                            e.innerText || ''
                        ].join('|')"""
                    )
                except Exception:
                    signature = f"{selector}:{i}:{text}"

                if signature in seen:
                    continue

                seen.add(signature)
                result.append(el)

        return result

    def _try_generic_clickables_in_block(self, block):
        """
        Essaie les contrôles cliquables internes non détectés comme
        bouton Commencer ou lien /activity/.
        """
        before_url = self.page.url

        for el in self._clickable_descendants(block):
            try:
                text = (
                    el.inner_text().strip()
                    or (el.get_attribute("aria-label") or "").strip()
                )
            except Exception:
                text = ""

            lowered = normalize(text)

            # Ne pas déclencher des contrôles manifestement non liés au lancement.
            if any(
                bad in lowered
                for bad in (
                    "conversation ia",
                    "je releve le defi",
                    "feedback",
                    "retour",
                )
            ):
                continue

            self.logger.info(
                "Tentative contrôle cliquable interne : %s",
                text[:120] or "(sans texte)",
            )

            try:
                el.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                el.click()
            except Exception:
                continue

            self._wait_after_launch_click()

            if self._current_is_activity():
                return True

            # Certains clics ouvrent un détail intermédiaire qui expose ensuite
            # un vrai lien/bouton de lancement.
            if self.page.url != before_url:
                if self._current_is_activity():
                    return True

            # Si ce clic a modifié le DOM du bloc, on retente les méthodes précises.
            if self._try_activity_link_in_block(block):
                return True

            if self._try_start_control_in_block(block):
                return True

        return False

    def _try_direct_block_click(self, block):
        """
        Dernier fallback : le composant exercice lui-même peut gérer @click.
        """
        before = self._page_state()

        self.logger.info(
            "Tentative clic direct sur le bloc exercice : %s",
            self._text(block)[:120],
        )

        try:
            block.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            block.click()
        except Exception:
            try:
                # Seulement pour les cas où un élément décoratif intercepte
                # le clic alors que le bloc lui-même est le composant interactif.
                block.click(force=True)
            except Exception:
                return False

        self._wait_after_launch_click()

        if self._current_is_activity():
            return True

        after = self._page_state()

        self.logger.info(
            "Après clic bloc : url %s -> %s | title %s -> %s",
            before["url"],
            after["url"],
            before["title"],
            after["title"],
        )

        # Un clic de carte peut ouvrir une vue intermédiaire dans la même URL.
        if self._try_activity_link_in_block(block):
            return True

        if self._try_start_control_in_block(block):
            return True

        return False

    def _try_block(self, block):
        """
        Ordre de tentative :
        1. lien /activity/ ;
        2. bouton Commencer/Continuer/etc. ;
        3. autre descendant réellement cliquable ;
        4. clic direct sur le bloc exercice.
        """
        try:
            block.scroll_into_view_if_needed()
        except Exception:
            pass

        if self._try_activity_link_in_block(block):
            return True

        if self._try_start_control_in_block(block):
            return True

        if self._try_generic_clickables_in_block(block):
            return True

        if self._try_direct_block_click(block):
            return True

        return False

    # ---------------------------------------------------------------
    # LANCEMENT GLOBAL
    # ---------------------------------------------------------------

    def launch_first_available(self):
        """
        Nouvelle logique :

        - si un menu est déjà ouvert :
            lancer le premier exercice normal de ce menu ;
        - sinon :
            ouvrir un menu au hasard puis lancer son premier exercice ;
        - checkpoint uniquement si le menu sélectionné ne contient
          aucun exercice normal.
        """
        if self._current_is_activity():
            return True

        menu = self.choose_active_menu()

        if menu is None:
            return False

        normal_blocks = self._exercise_blocks_in_menu(
            menu,
            include_checkpoint=False,
        )

        self.logger.info(
            "%s exercice(s) normal(aux) dans le menu actif.",
            len(normal_blocks),
        )

        # "Premier exo du menu"
        if normal_blocks:
            return self._try_block(normal_blocks[0])

        # Pas d'exercice normal : checkpoint éventuel du même menu.
        all_blocks = self._exercise_blocks_in_menu(
            menu,
            include_checkpoint=True,
        )

        for block in all_blocks:
            text = self._text(block)

            if not self._is_checkpoint_text(text):
                continue

            self.logger.info(
                "Aucun exercice normal dans ce menu : tentative checkpoint."
            )
            return self._try_block(block)

        return False
