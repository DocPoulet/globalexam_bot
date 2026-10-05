import json
from datetime import datetime
from pathlib import Path


def save_diagnostics(page, result, diagnostics_dir: Path):
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    json_text = json.dumps(result, ensure_ascii=False, indent=2)

    (diagnostics_dir / f"page_{stamp}.json").write_text(
        json_text, encoding="utf-8"
    )
    (diagnostics_dir / "last_page.json").write_text(
        json_text, encoding="utf-8"
    )

    # HTML principal.
    try:
        html = page.content()
        (diagnostics_dir / f"page_{stamp}.html").write_text(
            html, encoding="utf-8"
        )
        (diagnostics_dir / "last_page.html").write_text(
            html, encoding="utf-8"
        )
    except Exception:
        pass

    # HTML de chaque iframe accessible.
    for index, frame in enumerate(page.frames):
        try:
            frame_html = frame.content()
            (diagnostics_dir / f"frame_{index}_{stamp}.html").write_text(
                frame_html, encoding="utf-8"
            )
        except Exception:
            pass

    try:
        page.screenshot(
            path=str(diagnostics_dir / f"page_{stamp}.png"),
            full_page=True,
        )
        page.screenshot(
            path=str(diagnostics_dir / "last_page.png"),
            full_page=True,
        )
    except Exception:
        pass
