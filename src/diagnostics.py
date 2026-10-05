import json
from datetime import datetime
from pathlib import Path


def save_diagnostics(page, result, diagnostics_dir: Path):
    """
    Sauvegarde plusieurs formes de diagnostic afin de pouvoir
    corriger les sélecteurs à partir d'un vrai exercice.
    """

    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_path = diagnostics_dir / f"page_{stamp}.json"
    html_path = diagnostics_dir / f"page_{stamp}.html"
    screenshot_path = diagnostics_dir / f"page_{stamp}.png"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    html_path.write_text(
        page.content(),
        encoding="utf-8",
    )

    try:
        page.screenshot(
            path=str(screenshot_path),
            full_page=True,
        )
    except Exception:
        pass

    # Alias pratiques : toujours la dernière analyse.
    (diagnostics_dir / "last_page.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (diagnostics_dir / "last_page.html").write_text(
        page.content(),
        encoding="utf-8",
    )
