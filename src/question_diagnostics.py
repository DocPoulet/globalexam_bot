import json
from datetime import datetime
from pathlib import Path


class QuestionDiagnostics:
    def __init__(self, directory: Path, logger):
        self.directory = Path(directory)
        self.logger = logger
        self.directory.mkdir(parents=True, exist_ok=True)
        self._last_signature = None

    def save_unknown(self, page, analysis, reason="unknown_question"):
        """
        Sauvegarde une seule fois un état inconnu identique.
        """
        signature = (
            page.url,
            analysis.get("question"),
            analysis.get("exercise_type"),
        )

        if signature == self._last_signature:
            return None

        self._last_signature = signature
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self.directory / f"question_{stamp}"

        payload = {
            "reason": reason,
            "url": page.url,
            "title": page.title(),
            "analysis": analysis,
        }

        json_path = prefix.with_suffix(".json")
        html_path = prefix.with_suffix(".html")
        png_path = prefix.with_suffix(".png")

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            html_path = None

        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception:
            png_path = None

        self.logger.info(
            "Diagnostic question inconnue sauvegardé : %s",
            json_path,
        )

        return str(json_path)
    def save_packet(self, packet):
        """Sauvegarde un paquet QuestionExtractor sans HTML/capture."""
        packet_dir = self.directory / "question_packets"
        packet_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        question_id = packet.get("question_id", "unknown")
        path = packet_dir / f"packet_{stamp}_{question_id}.json"

        path.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self.logger.info("Question packet sauvegardé : %s", path)
        return str(path)

