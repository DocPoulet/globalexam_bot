from urllib.parse import urljoin
import random
import re
import unicodedata

from safety_clicks import is_forbidden_element, safe_click

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

    def _current_is_result(self):
        """
        Un exercice déjà terminé peut s'ouvrir directement sur son écran
        de résultat, sans changement d'URL suffisamment distinct pour le
        lanceur.

        Le marqueur fiable observé est "Votre score".
        """
        for selector in ("main", "[role='main']", "body"):
            try:
                locator = self.page.locator(selector)
                if locator.count() == 0:
                    continue

                text = normalize(locator.first.inner_text())
                if "votre score" in text:
                    return True
            except Exception:
                pass

        return False

    def _launch_target_reached(self):
        """
        Le launcher a terminé son travail dès qu'on est :
        - sur une URL d'activité ;
        - ou directement sur un écran résultat "Votre score".
        """
        return self._current_is_activity() or self._current_is_result()

    def _quick_launch_click(self, element, force=False):
        """
        Clic spécifique au lanceur avec timeout court.

        Le timeout Playwright par défaut (~30 s) était beaucoup trop long :
        sur une SPA, le clic peut déjà avoir changé d'écran alors que
        Locator.click() attend encore.

        En cas d'exception, on vérifie donc d'abord si la cible a quand même
        été atteinte avant de considérer le clic comme raté.
        """
        if is_forbidden_element(element):
            return False

        try:
            element.click(force=force, timeout=2500)
            return True
        except Exception:
            if self._launch_target_reached():
                return True
            return False

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

            if is_forbidden_element(control):
                continue

            if safe_click(control):
                self.page.wait_for_timeout(500)

                if self._menu_is_expanded(menu):
                    return True

        # Sinon clic direct sur la card.
        if is_forbidden_element(menu):
            return False

        if not safe_click(menu):
            return False

        self.page.wait_for_timeout(500)
        return self._menu_is_expanded(menu)

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

    def _click_target_from_text_node(self, node):
        """
        Transforme un texte/span/div en vraie cible cliquable si possible.
        """
        try:
            clickable = node.locator(
                "xpath=ancestor-or-self::*["
                "self::button or self::a or "
                "@role='button' or @tabindex='0' or "
                "contains(@class,'cursor-pointer') or "
                "@data-action"
                "][1]"
            )

            if clickable.count() > 0:
                target = clickable.first
            else:
                target = node
        except Exception:
            target = node

        if is_forbidden_element(target):
            return None

        return target

    def _nearby_start_targets(self, menu, block):
        """
        Cherche Commencer/Continuer/etc. dans tout le menu actif puis
        choisit les CTA les plus proches VISUELLEMENT du bloc exercice.

        Nécessaire car, sur certaines cartes GlobalExam, le CTA "Continuer"
        est un sibling du bloc mb-10/lg:mb-16 et non son descendant.
        """
        try:
            block_box = block.bounding_box()
        except Exception:
            block_box = None

        candidates = []
        seen = set()

        # Recherche textuelle : permet de trouver aussi les <span>/<div>.
        for word in START_WORDS:
            try:
                matches = menu.get_by_text(word, exact=True)
            except Exception:
                continue

            for i in range(matches.count()):
                node = matches.nth(i)

                try:
                    if not node.is_visible():
                        continue
                except Exception:
                    continue

                target = self._click_target_from_text_node(node)
                if target is None:
                    continue

                try:
                    text = (
                        target.inner_text().strip()
                        or node.inner_text().strip()
                        or (target.get_attribute("aria-label") or "").strip()
                    )
                except Exception:
                    text = word

                if not text or self._is_excluded_text(text):
                    continue

                try:
                    box = target.bounding_box()
                except Exception:
                    box = None

                # Distance verticale entre centres.
                distance = 999999.0
                if block_box and box:
                    block_y = block_box["y"] + block_box["height"] / 2
                    target_y = box["y"] + box["height"] / 2
                    distance = abs(target_y - block_y)

                # Un CTA à plusieurs écrans de distance ne correspond
                # vraisemblablement pas à ce bloc.
                if distance > 700:
                    continue

                try:
                    signature = target.evaluate(
                        """e => [
                            e.tagName,
                            e.getAttribute('class') || '',
                            e.getAttribute('href') || '',
                            e.getAttribute('role') || '',
                            e.getAttribute('data-action') || '',
                            e.getAttribute('data-testid') || '',
                            (e.innerText || '').trim()
                        ].join('|')"""
                    )
                except Exception:
                    signature = f"{word}|{i}|{distance}"

                if signature in seen:
                    continue

                seen.add(signature)
                candidates.append((distance, target, text))

        # Plus proche en premier.
        candidates.sort(key=lambda item: item[0])
        return candidates

    def _try_nearby_start_control(self, menu, block):
        """
        Essaie le CTA Commencer/Continuer le plus proche du bloc.
        """
        candidates = self._nearby_start_targets(menu, block)

        for distance, target, text in candidates:
            self.logger.info(
                "CTA lancement proche détecté : %s | distance=%.1fpx",
                text[:120],
                distance,
            )

            try:
                target.scroll_into_view_if_needed()
            except Exception:
                pass

            if self._quick_launch_click(target):
                self.page.wait_for_timeout(300)

                if self._launch_target_reached():
                    self.logger.info(
                        "CTA proche '%s' a ouvert l'activité/résultat.",
                        text[:120],
                    )
                    return True

                # Certains CTA mettent à jour le DOM avant la navigation.
                self._wait_after_launch_click()

                if self._launch_target_reached():
                    return True

            elif self._launch_target_reached():
                return True

        return False

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
                if is_forbidden_element(link) or not self._quick_launch_click(link):
                    raise RuntimeError("clic refusé")
                self.page.wait_for_timeout(350)

                if self._launch_target_reached():
                    return True
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

            if self._launch_target_reached():
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
        # Recherche textuelle en premier pour supporter :
        # <span>Continuer</span>, <div>Commencer</div>, etc.
        for word in START_WORDS:
            try:
                matches = block.get_by_text(word, exact=True)
            except Exception:
                continue

            for i in range(matches.count()):
                node = matches.nth(i)

                try:
                    if not node.is_visible():
                        continue
                except Exception:
                    continue

                target = self._click_target_from_text_node(node)
                if target is None:
                    continue

                try:
                    text = (
                        target.inner_text().strip()
                        or node.inner_text().strip()
                        or word
                    )
                except Exception:
                    text = word

                self.logger.info("Bouton lancement texte : %s", text)

                if self._quick_launch_click(target):
                    self.page.wait_for_timeout(300)

                    if self._launch_target_reached():
                        return True

                    if self._try_activity_link_in_block(block):
                        return True
                elif self._launch_target_reached():
                    return True

        # Ancienne détection button/role=button/a conservée en fallback.
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

            if is_forbidden_element(locator):
                continue

            if not self._quick_launch_click(locator):
                if self._launch_target_reached():
                    return True
                continue

            self.page.wait_for_timeout(350)

            if self._launch_target_reached():
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
            self.page.wait_for_timeout(450)
        except Exception:
            pass

        # Sur une SPA Vue, domcontentloaded peut déjà être passé.
        # Timeout court uniquement.
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=900)
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

                if is_forbidden_element(el):
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

            if is_forbidden_element(el):
                continue

            before_url = self.page.url

            if not self._quick_launch_click(el):
                if self._launch_target_reached():
                    return True
                continue

            # Vérification immédiate AVANT toute attente longue.
            self.page.wait_for_timeout(250)

            if self._launch_target_reached():
                self.logger.info(
                    "Écran d'activité/résultat atteint après clic interne."
                )
                return True

            self._wait_after_launch_click()

            if self._launch_target_reached():
                return True

            # Certains clics ouvrent un détail intermédiaire qui expose ensuite
            # un vrai lien/bouton de lancement.
            if self.page.url != before_url:
                if self._launch_target_reached():
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

        if is_forbidden_element(block):
            return False

        if not self._quick_launch_click(block):
            # Seulement pour les cas où un élément décoratif intercepte
            # le clic alors que le bloc lui-même est le composant interactif.
            if self._launch_target_reached():
                return True

            if not self._quick_launch_click(block, force=True):
                if self._launch_target_reached():
                    return True
                return False

        # Vérification immédiate avant le wait de stabilisation.
        self.page.wait_for_timeout(250)

        if self._launch_target_reached():
            self.logger.info(
                "Écran d'activité/résultat atteint après clic bloc."
            )
            return True

        self._wait_after_launch_click()

        if self._launch_target_reached():
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
        if self._launch_target_reached():
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
            first_block = normal_blocks[0]

            # IMPORTANT :
            # sur certaines cartes, le bouton "Continuer" n'est PAS
            # à l'intérieur du bloc exercice. Il est adjacent dans le menu.
            # On le cherche donc d'abord par proximité visuelle.
            if self._try_nearby_start_control(menu, first_block):
                return True

            return self._try_block(first_block)

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


    # ---------------------------------------------------------------
    # V0.8.14 — deterministic launcher
    # ---------------------------------------------------------------

    def is_list_page(self):
        url = (self.page.url or "").lower()
        return "/levels/content/" in url

    def _exact_start_nodes(self, scope):
        """
        Textes de lancement exacts uniquement.
        Aucun titre/card générique n'est considéré comme CTA.
        """
        result = []
        seen = set()

        for word in START_WORDS:
            try:
                matches = scope.get_by_text(word, exact=True)
            except Exception:
                continue

            for i in range(matches.count()):
                node = matches.nth(i)

                try:
                    if not node.is_visible():
                        continue
                except Exception:
                    continue

                target = self._click_target_from_text_node(node)
                if target is None:
                    continue

                try:
                    signature = target.evaluate(
                        """e => [
                            e.tagName,
                            e.getAttribute('href') || '',
                            e.getAttribute('role') || '',
                            e.getAttribute('data-action') || '',
                            e.getAttribute('class') || '',
                            (e.innerText || '').trim()
                        ].join('|')"""
                    )
                except Exception:
                    signature = f"{word}:{i}"

                if signature in seen:
                    continue

                seen.add(signature)
                result.append((target, word))

        return result

    def _structural_start_targets(self, menu, block):
        """
        Associe un CTA au bloc par structure DOM avant toute proximité visuelle.

        1. CTA dans le bloc ;
        2. CTA dans le plus proche parent contenant au maximum un bloc exercice ;
        3. CTA visuellement proche en dernier recours.
        """
        result = []
        seen = set()

        def add(target, label, source, distance=0.0):
            try:
                signature = target.evaluate(
                    """e => [
                        e.tagName,
                        e.getAttribute('href') || '',
                        e.getAttribute('role') || '',
                        e.getAttribute('data-action') || '',
                        e.getAttribute('class') || '',
                        (e.innerText || '').trim()
                    ].join('|')"""
                )
            except Exception:
                signature = f"{source}:{label}:{distance}"

            if signature in seen:
                return

            seen.add(signature)
            result.append((source, distance, target, label))

        # 1) Descendant exact du bloc.
        for target, label in self._exact_start_nodes(block):
            add(target, label, "inside", 0.0)

        # 2) Parents successifs. On refuse un parent englobant plusieurs exos,
        # car son CTA pourrait appartenir à une autre carte.
        current = block
        for depth in range(1, 7):
            try:
                parent = current.locator("xpath=..")
                if parent.count() == 0:
                    break
                parent = parent.first
            except Exception:
                break

            try:
                exercise_count = parent.locator(
                    '[class~="mb-10"][class~="lg:mb-16"]'
                ).count()
            except Exception:
                exercise_count = 99

            if exercise_count <= 1:
                for target, label in self._exact_start_nodes(parent):
                    add(target, label, f"ancestor-{depth}", float(depth))

            # Arrête après avoir atteint le menu ou un conteneur trop global.
            try:
                cls = parent.get_attribute("class") or ""
                if all(c in cls.split() for c in MENU_REQUIRED_CLASSES):
                    break
            except Exception:
                pass

            current = parent

        # 3) Proximité géométrique stricte, exact CTA seulement.
        try:
            block_box = block.bounding_box()
        except Exception:
            block_box = None

        if block_box:
            bx = block_box["x"] + block_box["width"] / 2
            by = block_box["y"] + block_box["height"] / 2

            for target, label in self._exact_start_nodes(menu):
                try:
                    box = target.bounding_box()
                except Exception:
                    box = None

                if not box:
                    continue

                tx = box["x"] + box["width"] / 2
                ty = box["y"] + box["height"] / 2

                dx = abs(tx - bx)
                dy = abs(ty - by)

                # Beaucoup plus strict que l'ancienne limite de 700 px.
                if dy <= 300 and dx <= 900:
                    add(target, label, "nearby", dy)

        source_order = {
            "inside": 0,
            "ancestor-1": 1,
            "ancestor-2": 2,
            "ancestor-3": 3,
            "ancestor-4": 4,
            "ancestor-5": 5,
            "ancestor-6": 6,
            "nearby": 20,
        }

        result.sort(
            key=lambda item: (
                source_order.get(item[0], 50),
                item[1],
            )
        )
        return result

    def _try_structural_start_control(self, menu, block):
        candidates = self._structural_start_targets(menu, block)

        self.logger.info(
            "Launcher déterministe : %s CTA explicite(s) associé(s) au premier exercice.",
            len(candidates),
        )

        for source, distance, target, label in candidates:
            self.logger.info(
                "Launcher : essai CTA '%s' source=%s distance=%.1f",
                label,
                source,
                distance,
            )

            try:
                target.scroll_into_view_if_needed(timeout=1200)
            except Exception:
                pass

            if self._quick_launch_click(target):
                # Ne jamais enchaîner un autre clic avant de savoir si
                # l'application a changé d'état.
                for _ in range(12):
                    self.page.wait_for_timeout(150)

                    if self._launch_target_reached():
                        self.logger.info(
                            "Launcher : CTA '%s' -> activité/résultat atteint.",
                            label,
                        )
                        return True

                    # Une URL d'activité est le signal le plus fiable.
                    if self._current_is_activity():
                        return True

            if self._launch_target_reached():
                return True

        return False

    def _block_title_text(self, block):
        """
        Extrait le titre humain du bloc exercice.

        On ignore les compteurs numériques/progression afin de garder
        par exemple "Ready, Set, Go!" dans :
            4
            10
            Ready, Set, Go!
        """
        raw = self._text(block)
        lines = [
            line.strip()
            for line in (raw or "").splitlines()
            if line.strip()
        ]

        for line in lines:
            normalized = normalize(line)

            if not normalized:
                continue

            if self._is_excluded_text(line):
                continue

            # Compteurs purs : 4, 10, 4/10, 10/12, etc.
            if re.fullmatch(r"\d+", normalized):
                continue

            if re.fullmatch(r"\d+\s*/\s*\d+", normalized):
                continue

            if "activites terminees" in normalized:
                continue

            if normalized in ("termine", "terminee"):
                continue

            return line

        return lines[-1] if lines else ""

    def _try_title_activation(self, block):
        """
        Fallback déterministe utilisé seulement si aucun CTA explicite
        n'existe.

        On clique uniquement le titre exact du PREMIER bloc exercice.
        C'est le comportement qui ouvrait effectivement l'activité dans
        les versions précédentes.

        Aucun clic sur toute la carte.
        """
        title = self._block_title_text(block)

        if not title:
            self.logger.info(
                "Launcher : aucun titre exploitable dans le premier bloc."
            )
            return False

        self.logger.info(
            "Launcher : fallback titre exact '%s'.",
            title,
        )

        try:
            matches = block.get_by_text(title, exact=True)
        except Exception:
            matches = None

        if matches is None or matches.count() == 0:
            self.logger.info(
                "Launcher : texte exact du titre introuvable dans le bloc."
            )
            return False

        seen = set()

        for i in range(matches.count()):
            node = matches.nth(i)

            try:
                if not node.is_visible():
                    continue
            except Exception:
                continue

            target = self._click_target_from_text_node(node)
            if target is None:
                continue

            try:
                signature = target.evaluate(
                    """e => [
                        e.tagName,
                        e.getAttribute('href') || '',
                        e.getAttribute('role') || '',
                        e.getAttribute('tabindex') || '',
                        e.getAttribute('class') || '',
                        (e.innerText || '').trim()
                    ].join('|')"""
                )
            except Exception:
                signature = f"{title}:{i}"

            if signature in seen:
                continue
            seen.add(signature)

            self.logger.info(
                "Launcher : clic contrôlé sur le titre '%s'.",
                title,
            )

            try:
                target.scroll_into_view_if_needed(timeout=1200)
            except Exception:
                pass

            before_url = self.page.url

            if not self._quick_launch_click(target):
                if self._launch_target_reached():
                    return True
                continue

            # Vérifie rapidement si le clic a réellement lancé l'activité.
            for _ in range(15):
                self.page.wait_for_timeout(150)

                if self._launch_target_reached():
                    self.logger.info(
                        "Launcher : titre '%s' -> activité/résultat atteint.",
                        title,
                    )
                    return True

                if self.page.url != before_url:
                    if self._launch_target_reached():
                        return True

            # Le clic sur le titre peut seulement révéler "Continuer".
            # Le caller refera alors immédiatement un scan CTA.
            self.logger.info(
                "Launcher : clic titre sans navigation ; nouveau scan CTA."
            )

        return False

    def launch_first_available(self):
        """
        V0.8.15 : lancement déterministe avec fallback titre contrôlé.

        Ordre :
        1. lien /activity/ explicite ;
        2. CTA Commencer/Continuer/... ;
        3. titre exact du premier exercice ;
        4. nouveau scan CTA, car le clic titre peut révéler Continuer.

        Jamais de clic sur toute la carte.
        """
        if self._launch_target_reached():
            return True

        menu = self.choose_active_menu()

        if menu is None:
            self.logger.info("Launcher : aucun menu actif.")
            return False

        normal_blocks = self._exercise_blocks_in_menu(
            menu,
            include_checkpoint=False,
        )

        self.logger.info(
            "%s exercice(s) normal(aux) dans le menu actif.",
            len(normal_blocks),
        )

        if normal_blocks:
            block = normal_blocks[0]

            # 1) Lien d'activité explicite.
            if self._try_activity_link_in_block(block):
                return True

            # 2) CTA explicite.
            if self._try_structural_start_control(menu, block):
                return True

            # 3) Aucun CTA : clic contrôlé sur le TITRE exact.
            if self._try_title_activation(block):
                return True

            # 4) Le clic titre peut avoir fait apparaître Continuer.
            self.page.wait_for_timeout(250)

            if self._try_structural_start_control(menu, block):
                return True

            self.logger.info(
                "Launcher : impossible de lancer le premier exercice '%s'.",
                self._block_title_text(block) or self._text(block)[:120],
            )
            return False

        # Checkpoint seulement si aucun exercice normal.
        all_blocks = self._exercise_blocks_in_menu(
            menu,
            include_checkpoint=True,
        )

        for block in all_blocks:
            text = self._text(block)

            if not self._is_checkpoint_text(text):
                continue

            if self._try_activity_link_in_block(block):
                return True

            if self._try_structural_start_control(menu, block):
                return True

            if self._try_title_activation(block):
                return True

        return False
