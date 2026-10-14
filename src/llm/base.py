import json
import re
from abc import ABC, abstractmethod


class LLMSolver(ABC):
    """Interface minimale d'un solveur linguistique."""

    SUPPORTED_TYPES = {
        "qcm_single",
        "qcm_multiple",
        "button_choice",
        "span_choice",
    }

    def __init__(self, config, logger=None):
        self.config = config or {}
        self.logger = logger

    def supports(self, packet):
        return packet.get("exercise_type") in self.SUPPORTED_TYPES

    @staticmethod
    def _question_payload(packet):
        return {
            "exercise_type": packet.get("exercise_type"),
            "instruction": packet.get("instruction", ""),
            "context": packet.get("context", ""),
            "choices": [
                {
                    "index": item.get("index"),
                    "text": item.get("text", ""),
                }
                for item in packet.get("choices", []) or []
                if not item.get("disabled")
            ],
        }

    @classmethod
    def build_messages(cls, packet):
        payload = cls._question_payload(packet)
        exercise_type = packet.get("exercise_type")

        if exercise_type == "qcm_multiple":
            cardinality = (
                "There may be one or several correct choices. Return every "
                "choice that should be selected."
            )
        else:
            cardinality = "Exactly one choice must be selected."

        system = (
            "You solve language-learning exercises accurately. "
            "Use the instruction, context and choices. "
            f"{cardinality} "
            "Return ONLY one JSON object, with no markdown and no explanation. "
            "The JSON schema is: "
            '{"choice_indices":[0],"confidence":0.95}. '
            "choice_indices are the ZERO-BASED indices supplied in the input. "
            "confidence must be a number from 0 to 1. "
            "Never return an index that is not present in the input."
        )

        user = json.dumps(payload, ensure_ascii=False, indent=2)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    @staticmethod
    def _parse_json_object(value):
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            raise ValueError("LLM response is not text/JSON")

        text = value.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        # Tolère du texte parasite autour du premier objet JSON.
        decoder = json.JSONDecoder()
        for pos, char in enumerate(text):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(text[pos:])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        raise ValueError("No JSON object found in LLM response")

    @staticmethod
    def _normalise_indices(obj):
        indices = obj.get("choice_indices")
        if indices is None:
            indices = obj.get("indices")
        if indices is None and obj.get("choice_index") is not None:
            indices = [obj.get("choice_index")]

        if isinstance(indices, int):
            indices = [indices]
        if not isinstance(indices, list):
            raise ValueError("choice_indices missing or invalid")

        result = []
        for item in indices:
            if isinstance(item, bool):
                raise ValueError("boolean is not a valid choice index")
            try:
                idx = int(item)
            except Exception as exc:
                raise ValueError(f"invalid choice index: {item!r}") from exc
            if idx not in result:
                result.append(idx)
        return result

    @classmethod
    def validate_answer(cls, packet, raw):
        obj = cls._parse_json_object(raw)
        indices = cls._normalise_indices(obj)
        valid = {
            item.get("index")
            for item in packet.get("choices", []) or []
            if not item.get("disabled")
        }

        if not indices:
            raise ValueError("LLM returned no choice")
        if any(idx not in valid for idx in indices):
            raise ValueError(f"LLM returned invalid index: {indices}")

        exercise_type = packet.get("exercise_type")
        if exercise_type in ("qcm_single", "button_choice", "span_choice"):
            if len(indices) != 1:
                raise ValueError("single-choice exercise requires exactly one index")

        confidence = obj.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        return {
            "kind": "choice_indices",
            "indices": indices,
            "confidence": confidence,
        }

    @abstractmethod
    def solve(self, packet):
        raise NotImplementedError
