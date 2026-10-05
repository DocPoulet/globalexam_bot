import json
from datetime import datetime
from pathlib import Path


class SessionTracker:
    """
    Suit les actions et statistiques d'une session.

    Données enregistrées :
    - durée ;
    - nombre d'analyses ;
    - réponses sélectionnées ;
    - validations ;
    - passages à la question suivante ;
    - erreurs ;
    - historique des sessions.
    """

    def __init__(self, history_file: Path):
        self.history_file = Path(history_file)
        self.started_at = None
        self.ended_at = None

        self.stats = {
            "analyses": 0,
            "answers_selected": 0,
            "validations": 0,
            "next_actions": 0,
            "errors": 0,
        }

        self.events = []

    def start(self):
        self.started_at = datetime.now()

    def stop(self):
        self.ended_at = datetime.now()

    def _event(self, kind, data=None):
        self.events.append({
            "time": datetime.now().isoformat(timespec="seconds"),
            "type": kind,
            "data": data or {},
        })

    def record_analysis(self, exercise):
        self.stats["analyses"] += 1
        self._event(
            "analysis",
            {
                "type": exercise.get("type"),
                "question": exercise.get("question"),
            }
        )

    def record_answer(self, answer_text):
        self.stats["answers_selected"] += 1
        self._event(
            "answer_selected",
            {"answer": answer_text}
        )

    def record_validation(self):
        self.stats["validations"] += 1
        self._event("validation")

    def record_next(self):
        self.stats["next_actions"] += 1
        self._event("next")

    def record_error(self, message):
        self.stats["errors"] += 1
        self._event(
            "error",
            {"message": str(message)}
        )

    def duration_seconds(self):
        if not self.started_at:
            return 0

        end = self.ended_at or datetime.now()
        return int((end - self.started_at).total_seconds())

    def current_session_data(self):
        return {
            "started_at": (
                self.started_at.isoformat(timespec="seconds")
                if self.started_at else None
            ),
            "ended_at": (
                self.ended_at.isoformat(timespec="seconds")
                if self.ended_at else None
            ),
            "duration_seconds": self.duration_seconds(),
            "stats": self.stats,
            "events": self.events,
        }

    def save(self):
        self.history_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        history = {"sessions": []}

        if self.history_file.exists():
            try:
                history = json.loads(
                    self.history_file.read_text(
                        encoding="utf-8"
                    )
                )
            except Exception:
                history = {"sessions": []}

        history.setdefault("sessions", [])
        history["sessions"].append(
            self.current_session_data()
        )

        self.history_file.write_text(
            json.dumps(
                history,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def print_stats(self):
        duration = self.duration_seconds()

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60

        print("\n=== Statistiques de session ===")
        print(
            f"Durée : {hours:02d}:{minutes:02d}:{seconds:02d}"
        )
        print(
            f"Analyses : {self.stats['analyses']}"
        )
        print(
            f"Réponses sélectionnées : "
            f"{self.stats['answers_selected']}"
        )
        print(
            f"Validations : {self.stats['validations']}"
        )
        print(
            f"Questions suivantes : "
            f"{self.stats['next_actions']}"
        )
        print(
            f"Erreurs : {self.stats['errors']}"
        )
