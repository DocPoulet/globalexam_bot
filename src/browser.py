from pathlib import Path
from playwright.sync_api import sync_playwright

GLOBAL_EXAM_URL = "https://general.global-exam.com/"
AUTH_HOST = "auth.global-exam.com"


class BrowserSession:
    """Gère un profil Chromium persistant pour conserver la connexion."""

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
            args=["--start-maximized"],
        )

        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def open_global_exam(self):
        self.logger.info("Ouverture de %s", GLOBAL_EXAM_URL)
        self.page.goto(
            GLOBAL_EXAM_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        self.wait_until_stable()

    def wait_until_stable(self, delay_ms=1800):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass

        try:
            self.page.wait_for_timeout(delay_ms)
        except Exception:
            pass

    def is_login_required(self):
        url = self.page.url.lower()

        if AUTH_HOST in url:
            return True

        if any(marker in url for marker in ("/login", "/signin", "/sign-in", "/connexion")):
            return True

        for frame in self.page.frames:
            try:
                password = frame.locator("input[type='password']")
                if password.count() and password.first.is_visible():
                    return True
            except Exception:
                pass

        return False

    def wait_for_login(self, timeout_ms=300000):
        """Attend que l'utilisateur termine une connexion manuelle."""
        try:
            self.page.wait_for_url(
                lambda url: AUTH_HOST not in url.lower(),
                timeout=timeout_ms,
            )
        except Exception:
            pass

        self.wait_until_stable()
        return not self.is_login_required()

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.context:
                self.context.close()
        finally:
            if self.playwright:
                self.playwright.stop()
