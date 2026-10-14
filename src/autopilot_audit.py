"""Journal d'exécution et protection contre les validations en double.

Données conservées : identifiants de questions, chemins de navigation sans paramètres,
actions et états techniques. Aucun cookie, mot de passe ni contenu de question.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


def safe_path(url):
    """Garde uniquement le chemin URL, sans query-string ni fragments."""
    try:
        value = urlsplit(str(url or ""))
        return value.path or "/"
    except Exception:
        return "/"


class QuestionRunGuard:
    """Bloque une seconde soumission de la même question dans une session."""

    def __init__(self):
        self._states = {}

    @staticmethod
    def key(url, question_id):
        # Conserve le chemin complet : question identique dans deux activités
        # différentes ne doit pas être confondue.
        if not question_id:
            return None
        return safe_path(url), str(question_id)

    def state(self, key):
        if key is None:
            return None
        return self._states.get(key)

    def begin(self, key):
        if key is None or self.state(key) is not None:
            return False
        self._states[key] = "inflight"
        return True

    def finish(self, key, status="submitted"):
        if key is not None:
            self._states[key] = status

    def count(self):
        return len(self._states)


class AutoPilotAudit:
    """Enregistre un JSONL autonome et des événements lisibles dans bot.log."""

    FIELDS = {
        "question_id", "exercise_type", "source", "action", "steps",
        "outcome", "learned", "attempt_id", "status", "reason", "from_path",
        "to_path", "screen", "cycle", "confidence", "state", "result",
        "count", "confirm", "error", "finish_action", "confirmed",
    }

    LABELS = {
        "question_detected": "QUESTION",
        "answer_used": "REPONSE",
        "validation": "VALIDATION",
        "correction": "CORRECTION",
        "sqlite": "SQLITE",
        "navigation": "NAVIGATION",
        "duplicate_prevented": "VERROU",
        "block": "BLOCAGE",
        "exception": "ERREUR",
        "run_start": "SESSION",
        "run_end": "BILAN",
    }

    def __init__(self, directory, logger, timestamp=None):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stamp = re.sub(r"[^A-Za-z0-9_-]", "", stamp)
        self.path = directory / ("autopilot_trace_" + stamp + ".jsonl")
        self.logger = logger
        self.totals = {"questions": 0, "submitted": 0, "skipped": 0,
                       "sqlite_saved": 0, "learned": 0, "duplicates_prevented": 0}

    def emit(self, event, **values):
        clean = {name: values[name] for name in self.FIELDS if name in values}
        obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": event,
            **clean,
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
        if event == "question_detected":
            self.totals["questions"] += 1
        elif event == "validation" and values.get("status") == "clicked":
            self.totals["submitted"] += 1
            if values.get("finish_action") == "skip":
                self.totals["skipped"] += 1
        elif event == "sqlite" and values.get("status") == "saved":
            self.totals["sqlite_saved"] += 1
            if values.get("learned"):
                self.totals["learned"] += 1
        elif event == "duplicate_prevented":
            self.totals["duplicates_prevented"] += 1
        label = self.LABELS.get(event, event.upper())
        summary = " ".join(f"{key}={val}" for key, val in clean.items())
        self.logger.info("[%s] %s", label, summary)
        return obj

    def summary(self):
        return dict(self.totals)
