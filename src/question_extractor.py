import hashlib
import json
import re
from copy import deepcopy

from safety_clicks import normalize


class QuestionExtractor:
    """
    Transforme l'état DOM/adaptateur courant en paquet sémantique stable.

    Le paquet est volontairement indépendant de Playwright : le futur moteur
    linguistique pourra le consommer sans connaître GlobalExam ni le DOM.
    """

    SCHEMA_VERSION = "1.0"
    MAX_SOURCE_TEXT = 12000
    MAX_CONTEXT_TEXT = 8000

    ACTION_WORDS = {
        "passer",
        "passer a la suite",
        "skip",
        "suivant",
        "next",
        "continuer",
        "continue",
        "valider",
        "validate",
        "verifier",
        "confirmer",
        "terminer",
        "submit",
        "precedent",
        "previous",
    }

    def __init__(self, page, logger=None):
        self.page = page
        self.logger = logger

    @staticmethod
    def _clean_text(text):
        text = (text or "").replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _main_text(self):
        for selector in ("main", "[role='main']", "body"):
            try:
                locator = self.page.locator(selector)
                if locator.count() == 0:
                    continue

                text = locator.first.inner_text(timeout=1800)
                text = self._clean_text(text)
                if text:
                    return text[: self.MAX_SOURCE_TEXT]
            except Exception:
                continue

        return ""

    def _html_language(self):
        try:
            value = self.page.locator("html").get_attribute("lang")
            return (value or "").strip() or None
        except Exception:
            return None

    @staticmethod
    def _answer_texts(analysis):
        result = []

        for item in analysis.get("answers", []) or []:
            if isinstance(item, dict) and item.get("options"):
                for option in item.get("options", []):
                    text = QuestionExtractor._clean_text(option.get("text"))
                    if text:
                        result.append(text)
            elif isinstance(item, dict):
                text = QuestionExtractor._clean_text(item.get("text"))
                if text:
                    result.append(text)

        for item in analysis.get("placed", []) or []:
            if isinstance(item, dict):
                text = QuestionExtractor._clean_text(item.get("text"))
                if text:
                    result.append(text)

        return result

    def _context_from_source(self, source_text, analysis, actions):
        """
        Produit un contexte utile au LLM sans prétendre comprendre le DOM.

        On retire seulement les lignes qui correspondent exactement à la
        consigne, aux choix de réponse et aux CTA connus. Tout le reste est
        conservé : paragraphe, dialogue, phrase à trous, exemple, etc.
        """
        instruction = self._clean_text(analysis.get("question"))
        answer_texts = self._answer_texts(analysis)
        action_texts = [
            self._clean_text(a.get("text"))
            for a in actions
            if isinstance(a, dict)
        ]

        excluded = {
            normalize(x)
            for x in [instruction, *answer_texts, *action_texts]
            if x
        }
        excluded.update(self.ACTION_WORDS)

        kept = []
        seen = set()

        for raw_line in source_text.splitlines():
            line = self._clean_text(raw_line)
            if not line:
                continue

            key = normalize(line)
            if not key:
                continue

            if key in excluded:
                continue

            # Progression pure : 4, 10, 4/10, 10/12 activités terminées...
            if re.fullmatch(r"\d+", key):
                continue
            if re.fullmatch(r"\d+\s*/\s*\d+", key):
                continue
            if re.fullmatch(r"\d+\s*/\s*\d+\s+activites?\s+terminees?", key):
                continue

            if key in seen:
                continue

            seen.add(key)
            kept.append(line)

        return "\n".join(kept)[: self.MAX_CONTEXT_TEXT]

    @staticmethod
    def _choice_contract(exercise_type, count):
        if exercise_type in ("qcm_single", "button_choice", "span_choice"):
            return {
                "kind": "choice_indices",
                "index_base": 0,
                "min_items": 1,
                "max_items": 1,
                "valid_indices": list(range(count)),
            }

        if exercise_type == "qcm_multiple":
            return {
                "kind": "choice_indices",
                "index_base": 0,
                "min_items": 1,
                "max_items": count,
                "valid_indices": list(range(count)),
            }

        return None

    @staticmethod
    def _build_payload_by_type(analysis):
        exercise_type = analysis.get("exercise_type") or "unknown"
        answers = deepcopy(analysis.get("answers", []) or [])

        # Retire les détails strictement DOM qui n'ont aucun sens pour le LLM.
        for item in answers:
            if isinstance(item, dict):
                item.pop("dom_index", None)
                for option in item.get("options", []) or []:
                    if isinstance(option, dict):
                        option.pop("dom_index", None)

        if exercise_type in (
            "qcm_single",
            "qcm_multiple",
            "button_choice",
            "span_choice",
        ):
            choices = []
            for i, item in enumerate(answers):
                if not isinstance(item, dict):
                    continue

                state = item.get("state")
                pressed = item.get("pressed")
                normalized_state = normalize(str(state or ""))
                normalized_pressed = normalize(str(pressed or ""))

                selected = bool(item.get("selected", False))
                selected = selected or normalized_state in {
                    "selected", "checked", "active", "on", "true"
                }
                selected = selected or normalized_pressed == "true"

                choices.append({
                    "index": item.get("index", i),
                    "text": item.get("text", ""),
                    "selected": selected,
                    "disabled": bool(item.get("disabled", False)),
                    "state": state,
                    "pressed": pressed,
                    "value": item.get("value"),
                })

            return {
                "choices": choices,
                "answer_contract": QuestionExtractor._choice_contract(
                    exercise_type,
                    len(choices),
                ),
            }

        if exercise_type == "ordering":
            available = [
                {
                    "index": item.get("index", i),
                    "id": item.get("id"),
                    "text": item.get("text", ""),
                }
                for i, item in enumerate(answers)
                if isinstance(item, dict)
            ]
            placed = [
                {
                    "index": item.get("index", i),
                    "id": item.get("id"),
                    "text": item.get("text", ""),
                }
                for i, item in enumerate(analysis.get("placed", []) or [])
                if isinstance(item, dict)
            ]

            return {
                "ordering": {
                    "available": available,
                    "already_placed": placed,
                },
                "answer_contract": {
                    "kind": "ordering_indices",
                    "index_base": 0,
                    "description": (
                        "Return the indices of the available items in the "
                        "desired order."
                    ),
                    "valid_indices": [x["index"] for x in available],
                },
            }

        if exercise_type == "select":
            fields = []
            for i, field in enumerate(answers):
                if not isinstance(field, dict):
                    continue

                fields.append({
                    "index": field.get("index", i),
                    "current_value": field.get("value"),
                    "options": [
                        {
                            "index": option.get("index", j),
                            "text": option.get("text", ""),
                            "value": option.get("value"),
                            "selected": bool(option.get("selected", False)),
                        }
                        for j, option in enumerate(field.get("options", []) or [])
                        if isinstance(option, dict)
                    ],
                })

            return {
                "fields": fields,
                "answer_contract": {
                    "kind": "select_options",
                    "index_base": 0,
                    "description": (
                        "Return one option index for each select field."
                    ),
                    "field_count": len(fields),
                },
            }

        if exercise_type == "text_input":
            fields = [
                {
                    "index": field.get("index", i),
                    "placeholder": field.get("placeholder", ""),
                    "current_value": field.get("value", ""),
                }
                for i, field in enumerate(answers)
                if isinstance(field, dict)
            ]

            return {
                "fields": fields,
                "answer_contract": {
                    "kind": "text_fields",
                    "description": "Return one text value for each field.",
                    "field_count": len(fields),
                },
            }

        return {
            "raw_answers": answers,
            "answer_contract": {
                "kind": "unknown",
                "description": "No stable answer contract is known yet.",
            },
        }

    @staticmethod
    def _stable_question_id(packet):
        """
        Empreinte indépendante de l'état de réponse courant.

        `selected`, current_value, state et la séparation
        available/already_placed ne doivent jamais changer l'identité.
        """
        choices = [
            {
                "index": item.get("index"),
                "text": item.get("text"),
                "value": item.get("value"),
            }
            for item in packet.get("choices", []) or []
        ]

        ordering = packet.get("ordering") or {}
        ordering_items = []
        for item in [
            *(ordering.get("available", []) or []),
            *(ordering.get("already_placed", []) or []),
        ]:
            ordering_items.append({
                "id": item.get("id"),
                "text": item.get("text"),
            })

        # L'ordre DOM des morceaux peut changer pendant l'interaction.
        ordering_items.sort(
            key=lambda item: (str(item.get("id")), str(item.get("text")))
        )

        fields = []
        for field in packet.get("fields", []) or []:
            stable_field = {
                "index": field.get("index"),
                "placeholder": field.get("placeholder"),
            }
            if field.get("options") is not None:
                stable_field["options"] = [
                    {
                        "index": option.get("index"),
                        "text": option.get("text"),
                        "value": option.get("value"),
                    }
                    for option in field.get("options", []) or []
                ]
            fields.append(stable_field)

        identity = {
            "exercise_type": packet.get("exercise_type"),
            "instruction": packet.get("instruction"),
            "context": packet.get("context"),
            "choices": choices,
            "ordering_items": ordering_items,
            "fields": fields,
        }

        raw = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def extract(self, analysis, actions=None):
        actions = deepcopy(actions or [])
        source_text = self._main_text()
        exercise_type = analysis.get("exercise_type") or "unknown"

        packet = {
            "schema_version": self.SCHEMA_VERSION,
            "source": "globalexam",
            "url": self.page.url,
            "page_title": self.page.title(),
            "html_language": self._html_language(),
            "adapter": analysis.get("adapter"),
            "exercise_type": exercise_type,
            "instruction": self._clean_text(analysis.get("question")),
            "context": self._context_from_source(
                source_text,
                analysis,
                actions,
            ),
            "source_text": source_text,
            "ui_actions": [
                {
                    "kind": action.get("kind"),
                    "text": action.get("text", ""),
                    "disabled": bool(action.get("disabled", False)),
                }
                for action in actions
            ],
        }

        packet.update(self._build_payload_by_type(analysis))
        packet["question_id"] = self._stable_question_id(packet)

        return packet
