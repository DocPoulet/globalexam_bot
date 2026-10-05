from pathlib import Path
from playwright.sync_api import sync_playwright

GLOBAL_EXAM_URL = "https://global-exam.com/"

class BrowserSession:
    """
    Gère le navigateur Playwright et la persistance de session.

    Entrées :
        session_file : chemin du fichier JSON de session.
        logger       : instance de logger.

    Sorties :
        Fournit un objet page Playwright via self.page.
    """

    def __init__(self, session_file: Path, logger):
        self.session_file = Path(session_file)
        self.logger = logger
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def __enter__(self):
        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=False
        )

        if self.session_file.exists():
            self.logger.info("Chargement de la session existante.")
            self.context = self.browser.new_context(
                storage_state=str(self.session_file)
            )
        else:
            self.logger.info("Aucune session existante, création d'une nouvelle session.")
            self.context = self.browser.new_context()

        self.page = self.context.new_page()
        return self

    def open_home(self):
        self.logger.info("Ouverture de GlobalExam.")
        self.page.goto(GLOBAL_EXAM_URL, wait_until="domcontentloaded")

    def save_session(self):
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.context.storage_state(path=str(self.session_file))
        self.logger.info("Session sauvegardée dans %s", self.session_file)

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if self.context:
                self.save_session()
        finally:
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
