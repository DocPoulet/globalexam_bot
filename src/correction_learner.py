import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from safety_clicks import normalize
from correction_quality import assess, labelled_choice


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

    SCHEMA_VERSION = 2

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

                CREATE TABLE IF NOT EXISTS answer_verifications (
                    question_id TEXT PRIMARY KEY,
                    attempt_id INTEGER,
                    status TEXT NOT NULL CHECK(status IN ('verified', 'legacy_unverified', 'disputed')),
                    evidence_source TEXT NOT NULL,
                    verified_at TEXT NOT NULL,
                    FOREIGN KEY(question_id) REFERENCES questions(question_id),
                    FOREIGN KEY(attempt_id) REFERENCES attempts(id)
                );

                CREATE TABLE IF NOT EXISTS correction_conflicts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT NOT NULL,
                    older_attempt_id INTEGER,
                    newer_attempt_id INTEGER NOT NULL,
                    older_answer_json TEXT NOT NULL,
                    newer_answer_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(question_id, newer_attempt_id),
                    FOREIGN KEY(question_id) REFERENCES questions(question_id)
                );

                CREATE TABLE IF NOT EXISTS correction_suggestions (
                    attempt_id INTEGER PRIMARY KEY,
                    question_id TEXT NOT NULL,
                    answer_json TEXT NOT NULL,
                    evidence_source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    FOREIGN KEY(attempt_id) REFERENCES attempts(id),
                    FOREIGN KEY(question_id) REFERENCES questions(question_id)
                );
                """
            )
            # Migration non destructive : conserver les anciennes réponses mais
            # NE JAMAIS les assimiler à des corrections vérifiées partageables.
            conn.execute("""
                INSERT OR IGNORE INTO answer_verifications(
                    question_id, attempt_id, status, evidence_source, verified_at
                )
                SELECT question_id, source_attempt_id, 'legacy_unverified',
                       'pre_0_10_12', learned_at FROM learned_answers
            """)
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
                if exercise_type in ("qcm_single", "button_choice", "span_choice") and len(matched) != 1:
                    return None
                if len(matched) == len(packet.get("choices", []) or []) and len(matched) > 1:
                    # Un conteneur 'correct' parent peut contenir TOUS les choix.
                    return None
                return {
                    "kind": "choice_indices",
                    "indices": [item["index"] for item in matched],
                    "choices": matched,
                }

        if exercise_type == "select":
            fields = packet.get("fields", []) or []
            assignments = {}
            used_candidates = set()

            for field in fields:
                field_index = field.get("index")
                matches = []

                for option in field.get("options", []) or []:
                    option_key = normalize(option.get("text", ""))
                    if not option_key or option_key not in candidate_keys:
                        continue

                    matches.append({
                        "index": option.get("index"),
                        "text": option.get("text", ""),
                        "value": option.get("value"),
                    })

                # La correction n'est considérée certaine que si exactement
                # une option correcte est identifiable pour ce champ.
                if len(matches) != 1:
                    return None

                chosen = matches[0]
                candidate_key = normalize(chosen.get("text", ""))
                if candidate_key in used_candidates:
                    # Même texte correct pour plusieurs champs : ambigu.
                    return None

                used_candidates.add(candidate_key)
                assignments[field_index] = chosen

            if fields and len(assignments) == len(fields):
                ordered = []
                for field in fields:
                    field_index = field.get("index")
                    chosen = assignments[field_index]
                    ordered.append({
                        "field_index": field_index,
                        "value": chosen.get("value"),
                        "selected_option_indices": [chosen.get("index")],
                        "selected_options": [chosen],
                    })

                return {
                    "kind": "select_options",
                    "fields": ordered,
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

    @staticmethod
    def _line_list(text):
        result = []
        seen = set()
        for raw in (text or "").splitlines():
            line = CorrectionLearner._clean_text(raw)
            key = normalize(line)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(line)
        return result

    def _correction_delta_lines(self, original_text, correction_text):
        before = {
            normalize(line)
            for line in self._line_list(original_text)
            if normalize(line)
        }
        return [
            line for line in self._line_list(correction_text)
            if normalize(line) not in before
        ]

    def _map_from_correction_delta(self, packet, delta_lines):
        if not delta_lines:
            return None

        exercise_type = packet.get("exercise_type")
        delta_norm = [normalize(x) for x in delta_lines]

        if exercise_type in (
            "qcm_single", "qcm_multiple", "button_choice", "span_choice"
        ):
            matched = []
            for choice in packet.get("choices", []) or []:
                key = normalize(choice.get("text", ""))
                if key and key in delta_norm:
                    matched.append({
                        "index": choice.get("index"),
                        "text": choice.get("text", ""),
                        "value": choice.get("value"),
                    })

            if exercise_type in ("qcm_single", "button_choice", "span_choice"):
                if len(matched) != 1:
                    return None
            else:
                if not matched:
                    return None
                if len(matched) == len(packet.get("choices", []) or []):
                    return None

            return {
                "kind": "choice_indices",
                "indices": [x["index"] for x in matched],
                "choices": matched,
            }

        if exercise_type == "ordering":
            ordering = packet.get("ordering") or {}
            items = [
                *(ordering.get("available", []) or []),
                *(ordering.get("already_placed", []) or []),
            ]
            if not items:
                return None

            by_key = {}
            for item in items:
                key = normalize(item.get("text", ""))
                if not key or key in by_key:
                    return None
                by_key[key] = item

            ordered = [by_key[line] for line in delta_norm if line in by_key]
            if len(ordered) != len(items):
                return None

            return {
                "kind": "ordering",
                "items": [
                    {
                        "index": item.get("index"),
                        "id": item.get("id"),
                        "text": item.get("text", ""),
                    }
                    for item in ordered
                ],
            }

        if exercise_type == "select":
            fields_out = []
            for field in packet.get("fields", []) or []:
                matches = [
                    option
                    for option in field.get("options", []) or []
                    if normalize(option.get("text", "")) in delta_norm
                ]
                if len(matches) != 1:
                    return None
                option = matches[0]
                fields_out.append({
                    "field_index": field.get("index"),
                    "value": option.get("value"),
                    "selected_option_indices": [option.get("index")],
                    "selected_options": [{
                        "index": option.get("index"),
                        "text": option.get("text", ""),
                        "value": option.get("value"),
                    }],
                })

            if fields_out:
                return {"kind": "select_options", "fields": fields_out}

        return None

    def _ordering_solution_from_dom(self, page, packet):
        """
        Tente de lire l'ordre corrigé dans la drop-zone GlobalExam.

        On n'accepte la solution que si tous les éléments de la question sont
        retrouvés exactement une fois.
        """
        if packet.get("exercise_type") != "ordering":
            return None

        ordering = packet.get("ordering") or {}
        original_items = [
            *(ordering.get("available", []) or []),
            *(ordering.get("already_placed", []) or []),
        ]

        if not original_items:
            return None

        by_text = {}
        for item in original_items:
            key = normalize(item.get("text", ""))
            if not key:
                return None
            by_text.setdefault(key, []).append(item)

        selectors = (
            "[data-name='user-answer-container'] [data-draggable-item-id]",
            "[data-name='user-answer-container'] button.draggable-item",
            ".ordering-drop-zone [data-draggable-item-id]",
            ".ordering-drop-zone button.draggable-item",
        )

        for frame in page.frames:
            for selector in selectors:
                try:
                    loc = frame.locator(selector)
                except Exception:
                    continue

                found = []
                seen_nodes = set()

                for i in range(min(loc.count(), 100)):
                    el = loc.nth(i)
                    try:
                        if not el.is_visible():
                            continue
                        text = self._clean_text(el.inner_text())
                    except Exception:
                        continue

                    key = normalize(text)
                    if not key or key not in by_text:
                        continue

                    try:
                        node_id = el.get_attribute("data-draggable-item-id") or f"{selector}:{i}"
                    except Exception:
                        node_id = f"{selector}:{i}"

                    if node_id in seen_nodes:
                        continue
                    seen_nodes.add(node_id)

                    candidates = by_text[key]
                    if len(candidates) != 1:
                        return None

                    src = candidates[0]
                    found.append({
                        "index": src.get("index"),
                        "id": src.get("id"),
                        "text": src.get("text", ""),
                    })

                if len(found) != len(original_items):
                    continue

                found_keys = [normalize(x.get("text", "")) for x in found]
                original_keys = [normalize(x.get("text", "")) for x in original_items]

                if sorted(found_keys) != sorted(original_keys):
                    continue

                return {
                    "kind": "ordering",
                    "items": found,
                }

        return None

    @staticmethod
    def _strong_correct_candidates(candidates):
        """Seuls les attributs sémantiques explicites constituent une preuve DOM."""
        return [item for item in candidates if item.get("selector") in (
            "[data-state='correct']", "[data-correct='true']",
        )]

    def _store_learned_answer(
        self,
        conn,
        question_id,
        correct_answer,
        attempt_id,
        confidence=1.0,
    ):
        if correct_answer is None:
            return False

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
                question_id,
                self._json(correct_answer),
                attempt_id,
                self._now(),
                confidence,
            ),
        )
        return True

    @staticmethod
    def _answer_identity(answer):
        """Identité sémantique : ignore les métadonnées affichées avec la réponse."""
        if not isinstance(answer, dict):
            return None
        kind = answer.get("kind")
        if kind == "choice_indices":
            return (kind, tuple(sorted(answer.get("indices", []))))
        if kind == "ordering":
            return (kind, tuple(
                (str(item.get("id") or ""), normalize(item.get("text", "")))
                for item in answer.get("items", [])
            ))
        if kind == "select_options":
            return (kind, tuple(
                (field.get("field_index"), tuple(field.get("selected_option_indices", [])))
                for field in answer.get("fields", [])
            ))
        if kind == "text_fields":
            return (kind, tuple(
                (field.get("field_index"), str(field.get("value", "")).strip())
                for field in answer.get("fields", [])
            ))
        return (kind, json.dumps(answer, sort_keys=True, default=str))

    def _store_verified_candidate(self, conn, question_id, answer, attempt_id, source):
        """N'écrase jamais silencieusement une solution vérifiée contradictoire."""
        previous = conn.execute("""
            SELECT l.answer_json, l.source_attempt_id, v.status
            FROM learned_answers l
            LEFT JOIN answer_verifications v ON v.question_id=l.question_id
            WHERE l.question_id=?
        """, (question_id,)).fetchone()
        candidate_json = self._json(answer)
        if previous and previous["status"] == "disputed":
            # Résolution manuelle / revue indépendante dans une future version.
            return False, "disputed"
        if (previous and previous["status"] == "verified"
                and self._answer_identity(json.loads(previous["answer_json"]))
                != self._answer_identity(answer)):
            conn.execute("""
                INSERT OR IGNORE INTO correction_conflicts(
                    question_id, older_attempt_id, newer_attempt_id,
                    older_answer_json, newer_answer_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (question_id, previous["source_attempt_id"], attempt_id,
                  previous["answer_json"], candidate_json, self._now()))
            conn.execute("""
                UPDATE answer_verifications SET status='disputed',
                    evidence_source='conflicting_explicit_corrections', verified_at=?
                WHERE question_id=?
            """, (self._now(), question_id))
            return False, "disputed"
        saved = self._store_learned_answer(
            conn, question_id, answer, attempt_id, confidence=1.0,
        )
        if saved:
            self._register_verification(conn, question_id, attempt_id, source)
        return saved, ("verified" if saved else "rejected")

    def _register_verification(self, conn, question_id, attempt_id, source):
        conn.execute("""
            INSERT INTO answer_verifications(
                question_id, attempt_id, status, evidence_source, verified_at
            ) VALUES (?, ?, 'verified', ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                attempt_id=excluded.attempt_id, status=excluded.status,
                evidence_source=excluded.evidence_source,
                verified_at=excluded.verified_at
        """, (question_id, attempt_id, source, self._now()))

    def _save_suggestion(self, conn, question_id, attempt_id, answer, source, reason):
        if answer is None:
            return
        conn.execute("""
            INSERT INTO correction_suggestions(
                attempt_id, question_id, answer_json, evidence_source, reason, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(attempt_id) DO UPDATE SET
                answer_json=excluded.answer_json,
                evidence_source=excluded.evidence_source,
                reason=excluded.reason,
                observed_at=excluded.observed_at
        """, (attempt_id, question_id, self._json(answer), source, reason, self._now()))

    def record_explicit_correction(
        self,
        page,
        original_packet,
        answered_packet,
        attempt_id=None,
        standalone=False,
    ):
        """
        Enrichit une tentative après clic explicite sur "Correction".

        L'onglet Correction existe aussi pour les réponses justes : son clic
        ne prouve donc jamais une mauvaise réponse. Le contenu reste
        sauvegardé. Une réponse structurée n'est apprise que si elle peut être
        reconstruite sans ambiguïté.
        """
        if not re.search(r"/content/[^/]+/correction(?:[?#].*)?$", page.url):
            raise RuntimeError("Pas sur la route /correction : solution non vérifiable")
        correction_text = self._main_text(page)
        candidates = self._correct_candidates(page)

        strong_candidates = self._strong_correct_candidates(candidates)
        correct_answer = self._map_correct_answer(original_packet, strong_candidates)
        extraction_source = "dom_correct_markers" if correct_answer is not None else None

        if correct_answer is None:
            correct_answer = self._map_correct_answer(original_packet, candidates)
            if correct_answer is not None:
                extraction_source = "dom_class_only"

        if correct_answer is None:
            correct_answer = labelled_choice(original_packet, correction_text)
            if correct_answer is not None:
                extraction_source = "labelled_correct_answer"

        if correct_answer is None:
            correct_answer = self._ordering_solution_from_dom(
                page,
                original_packet,
            )
            if correct_answer is not None:
                extraction_source = "ordering_corrected_dom"

        delta_lines = self._correction_delta_lines(
            answered_packet.get("source_text", ""),
            correction_text,
        )

        if correct_answer is None:
            correct_answer = self._map_from_correction_delta(
                original_packet,
                delta_lines,
            )
            if correct_answer is not None:
                extraction_source = "correction_text_delta"

        verification_status, verification_reason = assess(
            original_packet, correct_answer, extraction_source,
        )
        evidence = {
            "source": "explicit_correction_button",
            "extraction_source": extraction_source,
            "verification_status": verification_status,
            "verification_reason": verification_reason,
            "correct_candidates": candidates,
            "correction_delta_lines": delta_lines[:100],
            "structured_solution_found": correct_answer is not None,
        }

        now = self._now()

        with self._connect() as conn:
            self._upsert_question(conn, original_packet, now)

            target_attempt_id = attempt_id

            if target_attempt_id is None and not standalone:
                row = conn.execute(
                    """
                    SELECT id
                    FROM attempts
                    WHERE question_id=?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (original_packet["question_id"],),
                ).fetchone()
                target_attempt_id = row["id"] if row else None

            if target_attempt_id is not None:
                owned = conn.execute(
                    "SELECT id FROM attempts WHERE id=? AND question_id=?",
                    (target_attempt_id, original_packet["question_id"]),
                ).fetchone()
                if owned is None:
                    target_attempt_id = None

            if target_attempt_id is None:
                answer = self.answer_from_packet(answered_packet)
                cur = conn.execute(
                    """
                    INSERT INTO attempts(
                        question_id, created_at, finish_action, outcome,
                        answer_json, correct_answer_json,
                        correction_evidence_json, correction_text,
                        url_before, url_after
                    ) VALUES (?, ?, 'correction_review', 'unknown', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        original_packet["question_id"],
                        now,
                        self._json(answer),
                        self._json(correct_answer) if correct_answer is not None else None,
                        self._json(evidence),
                        correction_text[:16000],
                        original_packet.get("url"),
                        page.url,
                    ),
                )
                target_attempt_id = cur.lastrowid
            else:
                old_row = conn.execute(
                    """
                    SELECT correction_evidence_json
                    FROM attempts
                    WHERE id=? AND question_id=?
                    """,
                    (target_attempt_id, original_packet["question_id"]),
                ).fetchone()

                previous_evidence = {}
                if old_row and old_row["correction_evidence_json"]:
                    try:
                        previous_evidence = json.loads(
                            old_row["correction_evidence_json"]
                        )
                    except Exception:
                        previous_evidence = {}

                merged_evidence = {
                    **previous_evidence,
                    **evidence,
                }

                conn.execute(
                    """
                    UPDATE attempts
                    SET correct_answer_json=?,
                        correction_evidence_json=?,
                        correction_text=?,
                        url_after=?
                    WHERE id=? AND question_id=?
                    """,
                    (
                        self._json(correct_answer) if correct_answer is not None else None,
                        self._json(merged_evidence),
                        correction_text[:16000],
                        page.url,
                        target_attempt_id,
                        original_packet["question_id"],
                    ),
                )

            learned = False
            if verification_status == "verified":
                learned, verification_status = self._store_verified_candidate(
                    conn, original_packet["question_id"], correct_answer,
                    target_attempt_id, extraction_source,
                )
            elif verification_status == "provisional":
                self._save_suggestion(
                    conn, original_packet["question_id"], target_attempt_id,
                    correct_answer, extraction_source, verification_reason,
                )
            if verification_status == "disputed":
                evidence["verification_status"] = "disputed"
                evidence["verification_reason"] = "conflicting_verified_corrections"
                conn.execute(
                    "UPDATE attempts SET correction_evidence_json=? WHERE id=?",
                    (self._json(evidence), target_attempt_id),
                )

        if self.logger:
            self.logger.info(
                "Learner : correction explicite question=%s attempt=%s "
                "texte=%s chars delta=%s lignes source=%s statut=%s",
                original_packet["question_id"],
                target_attempt_id,
                len(correction_text or ""),
                len(delta_lines),
                extraction_source or "aucune",
                verification_status,
            )
            self.logger.info(
                "Learner : solution extraite=%s | learned=%s | answer=%s",
                correct_answer is not None,
                learned,
                self._json(correct_answer)[:1200] if correct_answer is not None else "None",
            )

        return {
            "attempt_id": target_attempt_id,
            "question_id": original_packet["question_id"],
            "outcome": "unknown",
            "correct_answer": correct_answer,
            "learned": learned,
            "correction_saved": True,
            "verification_status": verification_status,
            "evidence": evidence,
        }

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
        strong_candidates = self._strong_correct_candidates(candidates)
        mapped_correct = self._map_correct_answer(original_packet, strong_candidates)
        correction_marker_source = "dom_correct_markers"
        if mapped_correct is None:
            mapped_correct = self._map_correct_answer(original_packet, candidates)
            correction_marker_source = "dom_class_only"

        verification_source = None
        if outcome == "correct" and self._answer_is_meaningful(answer):
            correct_answer = answer
            verification_source = (
                "selected_data_state_correct"
                if evidence_source == "selected_data_state" else "text_verdict_correct"
            )
        elif outcome == "incorrect" and mapped_correct is not None:
            correct_answer = mapped_correct
            verification_source = correction_marker_source
        else:
            correct_answer = None

        verification_status, verification_reason = assess(
            original_packet, correct_answer, verification_source,
        )
        evidence = {
            "verification_status": verification_status,
            "verification_source": verification_source,
            "verification_reason": verification_reason,
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

            if verification_status == "verified":
                learned, verification_status = self._store_verified_candidate(
                    conn, original_packet["question_id"], correct_answer,
                    attempt_id, verification_source,
                )
            elif verification_status == "provisional":
                self._save_suggestion(
                    conn, original_packet["question_id"], attempt_id,
                    correct_answer, verification_source, verification_reason,
                )
            if verification_status == "disputed":
                evidence["verification_status"] = "disputed"
                evidence["verification_reason"] = "conflicting_verified_corrections"
                conn.execute(
                    "UPDATE attempts SET correction_evidence_json=? WHERE id=?",
                    (self._json(evidence), attempt_id),
                )

        if self.logger:
            self.logger.info(
                "Learner : question=%s outcome=%s learned=%s attempt=%s",
                original_packet["question_id"],
                outcome,
                verification_status == "verified",
                attempt_id,
            )

        return {
            "attempt_id": attempt_id,
            "question_id": original_packet["question_id"],
            "outcome": outcome,
            "answer": answer,
            "correct_answer": correct_answer,
            "learned": verification_status == "verified",
            "verification_status": verification_status,
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
                SELECT l.question_id, l.answer_json, l.source_attempt_id,
                       l.learned_at, l.confidence,
                       COALESCE(v.status, 'legacy_unverified') AS verification_status
                FROM learned_answers AS l
                LEFT JOIN answer_verifications AS v ON v.question_id=l.question_id
                WHERE l.question_id=?
                """,
                (question_id,),
            ).fetchone()

        if row is None or row["verification_status"] == "disputed":
            return None

        return {
            "question_id": row["question_id"],
            "answer": json.loads(row["answer_json"]),
            "source_attempt_id": row["source_attempt_id"],
            "learned_at": row["learned_at"],
            "confidence": row["confidence"],
            "verification_status": row["verification_status"],
        }

    def stats(self):
        with self._connect() as conn:
            questions = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
            attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            learned = conn.execute("SELECT COUNT(*) FROM learned_answers").fetchone()[0]
            verified = conn.execute(
                "SELECT COUNT(*) FROM answer_verifications WHERE status='verified'"
            ).fetchone()[0]
            legacy = conn.execute(
                "SELECT COUNT(*) FROM answer_verifications WHERE status='legacy_unverified'"
            ).fetchone()[0]
            suggestions = conn.execute(
                "SELECT COUNT(*) FROM correction_suggestions"
            ).fetchone()[0]
            disputed = conn.execute(
                "SELECT COUNT(*) FROM answer_verifications WHERE status='disputed'"
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT outcome, COUNT(*) AS n FROM attempts GROUP BY outcome"
            ).fetchall()

        return {
            "questions": questions,
            "attempts": attempts,
            "learned_answers": learned,
            "verified_answers": verified,
            "legacy_unverified": legacy,
            "provisional_suggestions": suggestions,
            "disputed_answers": disputed,
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
