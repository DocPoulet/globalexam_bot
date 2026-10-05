import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from safety_clicks import normalize


class CorrectionLearner:
    """
    Mémoire locale des tentatives et corrections.

    Principes :
    - chaque validation est persistée automatiquement ;
    - aucune correction n'est inventée ;
    - outcome = correct / incorrect seulement avec un signal suffisamment fort ;
    - sinon outcome = unknown ;
    - une réponse validée comme correcte devient une réponse apprise.
    """

    SCHEMA_VERSION = 1

    INCORRECT_PATTERNS = (
        r"\bmauvaise\s+reponse\b",
        r"\breponse\s+incorrecte\b",
        r"\bincorrect\s+answer\b",
        r"\bwrong\s+answer\b",
        r"\bnot\s+the\s+correct\s+answer\b",
        r"\bce\s+n['’]?est\s+pas\s+la\s+bonne\s+reponse\b",
        r"\bessaie\s+encore\b",
        r"\btry\s+again\b",
    )

    CORRECT_PATTERNS = (
        r"\bbonne\s+reponse\b",
        r"\breponse\s+correcte\b",
        r"\bcorrect\s+answer\b",
        r"\bwell\s+done\b",
        r"\bbravo\b",
        r"\bfelicitations\b",
    )

    def __init__(self, base_dir, logger=None):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "knowledge.sqlite3"
        self.logger = logger
        self._init_db()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS questions (
                    question_id TEXT PRIMARY KEY,
                    exercise_type TEXT,
                    adapter TEXT,
                    instruction TEXT,
                    context TEXT,
                    packet_json TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    times_seen INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    finish_action TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    answer_json TEXT,
                    correct_answer_json TEXT,
                    correction_evidence_json TEXT,
                    correction_text TEXT,
                    url_before TEXT,
                    url_after TEXT,
                    FOREIGN KEY(question_id) REFERENCES questions(question_id)
                );

                CREATE TABLE IF NOT EXISTS learned_answers (
                    question_id TEXT PRIMARY KEY,
                    answer_json TEXT NOT NULL,
                    source_attempt_id INTEGER,
                    learned_at TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    FOREIGN KEY(question_id) REFERENCES questions(question_id),
                    FOREIGN KEY(source_attempt_id) REFERENCES attempts(id)
                );

                CREATE INDEX IF NOT EXISTS idx_attempts_question
                ON attempts(question_id);

                CREATE INDEX IF NOT EXISTS idx_attempts_outcome
                ON attempts(outcome);
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                ("schema_version", str(self.SCHEMA_VERSION)),
            )

    @staticmethod
    def _clean_text(value):
        value = (value or "").replace("\xa0", " ")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _selected_choice(item):
        if item.get("selected"):
            return True

        state = normalize(str(item.get("state") or ""))
        if state in {"selected", "checked", "active", "on", "true"}:
            return True

        pressed = normalize(str(item.get("pressed") or ""))
        return pressed == "true"

    def answer_from_packet(self, packet):
        """Extrait uniquement la réponse actuellement saisie/sélectionnée."""
        exercise_type = packet.get("exercise_type")

        if exercise_type in (
            "qcm_single",
            "qcm_multiple",
            "button_choice",
            "span_choice",
        ):
            selected = [
                {
                    "index": item.get("index"),
                    "text": item.get("text", ""),
                    "value": item.get("value"),
                }
                for item in packet.get("choices", []) or []
                if self._selected_choice(item)
            ]
            return {
                "kind": "choice_indices",
                "indices": [item["index"] for item in selected],
                "choices": selected,
            }

        if exercise_type == "ordering":
            placed = (packet.get("ordering") or {}).get("already_placed", []) or []
            return {
                "kind": "ordering",
                "items": [
                    {
                        "index": item.get("index"),
                        "id": item.get("id"),
                        "text": item.get("text", ""),
                    }
                    for item in placed
                ],
            }

        if exercise_type == "select":
            fields = []
            for field in packet.get("fields", []) or []:
                selected = [
                    opt for opt in field.get("options", []) or []
                    if opt.get("selected")
                ]
                fields.append({
                    "field_index": field.get("index"),
                    "value": field.get("current_value"),
                    "selected_option_indices": [
                        opt.get("index") for opt in selected
                    ],
                    "selected_options": [
                        {
                            "index": opt.get("index"),
                            "text": opt.get("text", ""),
                            "value": opt.get("value"),
                        }
                        for opt in selected
                    ],
                })
            return {"kind": "select_options", "fields": fields}

        if exercise_type == "text_input":
            return {
                "kind": "text_fields",
                "fields": [
                    {
                        "field_index": field.get("index"),
                        "value": field.get("current_value", ""),
                    }
                    for field in packet.get("fields", []) or []
                ],
            }

        return {
            "kind": "unknown",
            "raw": packet.get("raw_answers", []),
        }

    @staticmethod
    def _answer_is_meaningful(answer):
        if not isinstance(answer, dict):
            return False

        kind = answer.get("kind")
        if kind == "choice_indices":
            return bool(answer.get("indices"))
        if kind == "ordering":
            return bool(answer.get("items"))
        if kind == "select_options":
            for field in answer.get("fields", []) or []:
                if field.get("selected_option_indices"):
                    return True
                if field.get("value") not in (None, ""):
                    return True
            return False
        if kind == "text_fields":
            return any(
                str(field.get("value", "")).strip()
                for field in answer.get("fields", []) or []
            )
        return bool(answer.get("raw"))

    def _main_text(self, page):
        for selector in ("main", "[role='main']", "body"):
            try:
                loc = page.locator(selector)
                if loc.count() == 0:
                    continue
                text = self._clean_text(loc.first.inner_text(timeout=1200))
                if text:
                    return text[:16000]
            except Exception:
                continue
        return ""

    def _wait_for_correction_render(self, page, before_text, timeout_ms=1800):
        elapsed = 0
        previous = self._main_text(page)
        changed = normalize(previous) != normalize(before_text)
        stable = 0

        while elapsed < timeout_ms:
            page.wait_for_timeout(150)
            elapsed += 150
            current = self._main_text(page)

            if normalize(current) != normalize(before_text):
                changed = True

            if current == previous:
                stable += 1
            else:
                stable = 0
                previous = current

            if changed and stable >= 2:
                break

        return previous

    def _selected_state_outcome(self, page):
        """Détecte correct/incorrect seulement sur un élément explicitement sélectionné."""
        selectors = (
            "[data-state='incorrect']",
            "[data-state='wrong']",
            "[data-state='correct']",
        )

        selected_states = []
        for frame in page.frames:
            for selector in selectors:
                try:
                    loc = frame.locator(selector)
                except Exception:
                    continue

                for i in range(min(loc.count(), 50)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                    except Exception:
                        continue

                    selected = False
                    for attr in ("aria-selected", "aria-checked", "aria-pressed", "data-selected"):
                        try:
                            if normalize(el.get_attribute(attr) or "") == "true":
                                selected = True
                        except Exception:
                            pass

                    try:
                        if el.locator("input:checked").count() > 0:
                            selected = True
                    except Exception:
                        pass

                    try:
                        cls = normalize(el.get_attribute("class") or "")
                        if "selected" in cls or "checked" in cls:
                            selected = True
                    except Exception:
                        pass

                    if not selected:
                        continue

                    state = normalize(el.get_attribute("data-state") or "")
                    selected_states.append(state)

        if any(state in ("incorrect", "wrong") for state in selected_states):
            return "incorrect", {"selected_states": selected_states}
        if any(state == "correct" for state in selected_states):
            return "correct", {"selected_states": selected_states}
        return None, {"selected_states": selected_states}

    def _text_outcome(self, text):
        norm = normalize(text)

        for pattern in self.INCORRECT_PATTERNS:
            if re.search(pattern, norm):
                return "incorrect", pattern

        for pattern in self.CORRECT_PATTERNS:
            if re.search(pattern, norm):
                return "correct", pattern

        return "unknown", None

    def _correct_candidates(self, page):
        selectors = (
            "[data-state='correct']",
            "[data-correct='true']",
            "[class~='correct']",
            "[class*='correct-answer']",
            "[class*='answer-correct']",
        )
        result = []
        seen = set()

        for frame in page.frames:
            for selector in selectors:
                try:
                    loc = frame.locator(selector)
                except Exception:
                    continue

                for i in range(min(loc.count(), 80)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                        text = self._clean_text(el.inner_text())
                        cls = normalize(el.get_attribute("class") or "")
                    except Exception:
                        continue

                    if not text or len(text) > 600:
                        continue
                    if "incorrect" in cls or "wrong" in cls:
                        continue

                    key = normalize(text)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    result.append({"text": text, "selector": selector})

        return result[:30]

    def _map_correct_answer(self, packet, candidates):
        if not candidates:
            return None

        exercise_type = packet.get("exercise_type")
        candidate_keys = {normalize(item.get("text", "")) for item in candidates}

        if exercise_type in (
            "qcm_single",
            "qcm_multiple",
            "button_choice",
            "span_choice",
        ):
            matched = []
            for choice in packet.get("choices", []) or []:
                key = normalize(choice.get("text", ""))
                if key and key in candidate_keys:
                    matched.append({
                        "index": choice.get("index"),
                        "text": choice.get("text", ""),
                        "value": choice.get("value"),
                    })
            if matched:
                return {
                    "kind": "choice_indices",
                    "indices": [item["index"] for item in matched],
                    "choices": matched,
                }

        # On conserve les candidats bruts, mais on ne les présente pas comme
        # une réponse structurée certaine si le mapping n'est pas démontrable.
        return None

    def _upsert_question(self, conn, packet, now):
        qid = packet["question_id"]
        row = conn.execute(
            "SELECT question_id FROM questions WHERE question_id = ?",
            (qid,),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE questions
                SET exercise_type=?, adapter=?, instruction=?, context=?,
                    packet_json=?, last_seen_at=?, times_seen=times_seen+1
                WHERE question_id=?
                """,
                (
                    packet.get("exercise_type"),
                    packet.get("adapter"),
                    packet.get("instruction"),
                    packet.get("context"),
                    self._json(packet),
                    now,
                    qid,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO questions(
                    question_id, exercise_type, adapter, instruction, context,
                    packet_json, first_seen_at, last_seen_at, times_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    qid,
                    packet.get("exercise_type"),
                    packet.get("adapter"),
                    packet.get("instruction"),
                    packet.get("context"),
                    self._json(packet),
                    now,
                    now,
                ),
            )

    def record_validation(self, page, original_packet, answered_packet):
        """Enregistre une validation et apprend seulement si la preuve est suffisante."""
        before_text = answered_packet.get("source_text", "")
        correction_text = self._wait_for_correction_render(page, before_text)
        answer = self.answer_from_packet(answered_packet)

        state_outcome, state_evidence = self._selected_state_outcome(page)
        text_outcome, matched_pattern = self._text_outcome(correction_text)

        if state_outcome in ("correct", "incorrect"):
            outcome = state_outcome
            evidence_source = "selected_data_state"
        else:
            outcome = text_outcome
            evidence_source = "correction_text" if matched_pattern else "none"

        candidates = self._correct_candidates(page)
        mapped_correct = self._map_correct_answer(original_packet, candidates)

        if outcome == "correct" and self._answer_is_meaningful(answer):
            correct_answer = answer
        elif outcome == "incorrect" and mapped_correct is not None:
            correct_answer = mapped_correct
        else:
            correct_answer = None

        evidence = {
            "source": evidence_source,
            "matched_pattern": matched_pattern,
            **state_evidence,
            "correct_candidates": candidates,
        }

        now = self._now()
        with self._connect() as conn:
            self._upsert_question(conn, original_packet, now)
            cur = conn.execute(
                """
                INSERT INTO attempts(
                    question_id, created_at, finish_action, outcome,
                    answer_json, correct_answer_json,
                    correction_evidence_json, correction_text,
                    url_before, url_after
                ) VALUES (?, ?, 'validate', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    original_packet["question_id"],
                    now,
                    outcome,
                    self._json(answer),
                    self._json(correct_answer) if correct_answer is not None else None,
                    self._json(evidence),
                    correction_text[:16000],
                    original_packet.get("url"),
                    page.url,
                ),
            )
            attempt_id = cur.lastrowid

            if correct_answer is not None:
                confidence = 1.0 if outcome == "correct" else 0.95
                conn.execute(
                    """
                    INSERT INTO learned_answers(
                        question_id, answer_json, source_attempt_id,
                        learned_at, confidence
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(question_id) DO UPDATE SET
                        answer_json=excluded.answer_json,
                        source_attempt_id=excluded.source_attempt_id,
                        learned_at=excluded.learned_at,
                        confidence=excluded.confidence
                    """,
                    (
                        original_packet["question_id"],
                        self._json(correct_answer),
                        attempt_id,
                        now,
                        confidence,
                    ),
                )

        if self.logger:
            self.logger.info(
                "Learner : question=%s outcome=%s learned=%s attempt=%s",
                original_packet["question_id"],
                outcome,
                correct_answer is not None,
                attempt_id,
            )

        return {
            "attempt_id": attempt_id,
            "question_id": original_packet["question_id"],
            "outcome": outcome,
            "answer": answer,
            "correct_answer": correct_answer,
            "learned": correct_answer is not None,
            "evidence": evidence,
        }

    def record_skip(self, page, original_packet, answered_packet):
        answer = self.answer_from_packet(answered_packet)
        now = self._now()

        with self._connect() as conn:
            self._upsert_question(conn, original_packet, now)
            cur = conn.execute(
                """
                INSERT INTO attempts(
                    question_id, created_at, finish_action, outcome,
                    answer_json, correct_answer_json,
                    correction_evidence_json, correction_text,
                    url_before, url_after
                ) VALUES (?, ?, 'skip', 'skipped', ?, NULL, ?, '', ?, ?)
                """,
                (
                    original_packet["question_id"],
                    now,
                    self._json(answer),
                    self._json({"source": "skip"}),
                    original_packet.get("url"),
                    page.url,
                ),
            )
            attempt_id = cur.lastrowid

        if self.logger:
            self.logger.info(
                "Learner : question=%s outcome=skipped attempt=%s",
                original_packet["question_id"],
                attempt_id,
            )

        return {
            "attempt_id": attempt_id,
            "question_id": original_packet["question_id"],
            "outcome": "skipped",
            "answer": answer,
            "correct_answer": None,
            "learned": False,
        }

    def lookup(self, question_id):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT question_id, answer_json, source_attempt_id,
                       learned_at, confidence
                FROM learned_answers
                WHERE question_id=?
                """,
                (question_id,),
            ).fetchone()

        if row is None:
            return None

        return {
            "question_id": row["question_id"],
            "answer": json.loads(row["answer_json"]),
            "source_attempt_id": row["source_attempt_id"],
            "learned_at": row["learned_at"],
            "confidence": row["confidence"],
        }

    def stats(self):
        with self._connect() as conn:
            questions = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            learned = conn.execute("SELECT COUNT(*) FROM learned_answers").fetchone()[0]
            rows = conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM attempts GROUP BY outcome"
            ).fetchall()

        return {
            "questions": questions,
            "attempts": attempts,
            "learned_answers": learned,
            "outcomes": {row["outcome"]: row["n"] for row in rows},
            "database": str(self.db_path),
        }

    def recent_attempts(self, limit=10):
        limit = max(1, min(int(limit), 100))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT a.id, a.created_at, a.question_id, a.finish_action,
                       a.outcome, a.answer_json, a.correct_answer_json,
                       q.exercise_type, q.instruction
                FROM attempts a
                JOIN questions q ON q.question_id = a.question_id
                ORDER BY a.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        result = []
        for row in rows:
            result.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "question_id": row["question_id"],
                "finish_action": row["finish_action"],
                "outcome": row["outcome"],
                "exercise_type": row["exercise_type"],
                "instruction": row["instruction"],
                "answer": json.loads(row["answer_json"]) if row["answer_json"] else None,
                "correct_answer": (
                    json.loads(row["correct_answer_json"])
                    if row["correct_answer_json"] else None
                ),
            })
        return result
