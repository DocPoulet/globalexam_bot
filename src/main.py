from pathlib import Path
from browser import BrowserSession
from page_analyzer import analyze_page
from logger import setup_logger

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_FILE = BASE_DIR / "data" / "session.json"

def main():
    logger = setup_logger()

    logger.info("Démarrage de GlobalExam Bot v0.1")

    with BrowserSession(session_file=SESSION_FILE, logger=logger) as session:
        page = session.page

        print("\n=== GlobalExam Bot v0.1 ===")
        print("1. Le navigateur va s'ouvrir.")
        print("2. Connecte-toi manuellement si nécessaire.")
        print("3. Va sur une page d'exercice.")
        print("4. Reviens dans ce terminal et appuie sur Entrée.\n")

        session.open_home()

        input("Appuie sur Entrée quand tu es sur une page à analyser... ")

        result = analyze_page(page)

        print("\n=== Analyse de la page ===")
        print(f"Titre : {result['title']}")
        print(f"URL   : {result['url']}")
        print(f"Boutons détectés : {len(result['buttons'])}")
        print(f"Inputs détectés  : {len(result['inputs'])}")
        print(f"Radios détectés  : {len(result['radios'])}")
        print(f"Checkboxes       : {len(result['checkboxes'])}")

        if result["headings"]:
            print("\nTitres / questions possibles :")
            for item in result["headings"][:10]:
                print(f"- {item}")

        print("\nSession sauvegardée.")
        input("Appuie sur Entrée pour fermer le navigateur... ")

if __name__ == "__main__":
    main()
