import json
from datetime import datetime
from pathlib import Path


def save_diagnostics(page, result, diagnostics_dir: Path):
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_text = json.dumps(result, ensure_ascii=False, indent=2)

    (diagnostics_dir / f"analysis_{stamp}.json").write_text(
        json_text, encoding="utf-8"
    )
    (diagnostics_dir / "last_analysis.json").write_text(
        json_text, encoding="utf-8"
    )

    try:
        page.screenshot(
            path=str(diagnostics_dir / "last_page.png"),
            full_page=True,
        )
    except Exception:
        pass
