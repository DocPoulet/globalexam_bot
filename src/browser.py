from pathlib import Path
from playwright.sync_api import sync_playwright

GLOBAL_EXAM_URL = "https://general.global-exam.com/"


class BrowserSession:
    """
    Lance Chromium avec un profil utilisateur persistant.

    Contrairement à storage_state, un profil persistant conserve
    beaucoup plus fidèlement l'état du navigateur :
    cookies, localStorage, IndexedDB et autres données de site.
    """

    def __init__(self, profile_dir: Path, logger):
        self.profile_dir = Path(profile_dir)
        self.logger = logger
        self.playwright = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.playwright = sync_playwright().start()

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=False,
            viewport={"width": 1440, "height": 1000},
            args=[
                "--start-maximized",
            ],
        )

        pages = self.context.pages
        self.page = pages[0] if pages else self.context.new_page()

        return self

    def open_global_exam(self):
        self.logger.info("Ouverture de %s", GLOBAL_EXAM_URL)

        self.page.goto(
            GLOBAL_EXAM_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        self.wait_until_stable()

    def wait_until_stable(self):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        try:
            self.page.wait_for_timeout(1500)
        except Exception:
            pass

    def is_login_required(self):
        """
        Détection plus robuste d'une page d'authentification.
        """

        url = self.page.url.lower()

        if "auth.global-exam.com" in url:
            return True

        markers = (
            "/login",
            "/signin",
            "/sign-in",
            "/connexion",
        )

        if any(marker in url for marker in markers):
            return True

        password = self.page.locator("input[type='password']")

        try:
            if password.count() > 0 and password.first.is_visible():
                return True
        except Exception:
            pass

        return False

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.context:
                self.context.close()
        finally:
            if self.playwright:
                self.playwright.stop()
