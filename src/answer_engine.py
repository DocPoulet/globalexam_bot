class AnswerEngine:
    """
    Choisit une réponse sémantique sans toucher au DOM.

    Priorité :
    1. mémoire locale apprise ;
    2. LLM ;
    3. aucun résultat -> ancien AutoQ prendra le relais.
    """

    SUPPORTED_TYPES = {
        "qcm_single",
        "qcm_multiple",
        "button_choice",
        "span_choice",
    }

    def __init__(self, learner=None, llm_solver=None, logger=None, min_confidence=0.35):
        self.learner = learner
        self.llm_solver = llm_solver
        self.logger = logger
        self.min_confidence = float(min_confidence)

    def _validate_choice_answer(self, packet, answer):
        if not isinstance(answer, dict):
            return None
        if answer.get("kind") != "choice_indices":
            return None

        indices = answer.get("indices")
        if not isinstance(indices, list) or not indices:
            return None

        valid = {
            item.get("index")
            for item in packet.get("choices", []) or []
            if not item.get("disabled")
        }
        cleaned = []
        for idx in indices:
            try:
                idx = int(idx)
            except Exception:
                return None
            if idx not in valid:
                return None
            if idx not in cleaned:
                cleaned.append(idx)

        if packet.get("exercise_type") in (
            "qcm_single", "button_choice", "span_choice"
        ) and len(cleaned) != 1:
            return None

        return {"kind": "choice_indices", "indices": cleaned}

    def solve(self, packet):
        if packet.get("exercise_type") not in self.SUPPORTED_TYPES:
            return {
                "ok": False,
                "source": "unsupported",
                "reason": "exercise_type_not_supported_yet",
            }

        question_id = packet.get("question_id")

        # 1) Mémoire locale.
        if self.learner is not None and question_id:
            try:
                known = self.learner.lookup(question_id)
            except Exception as exc:
                known = None
                if self.logger:
                    self.logger.info("AnswerEngine : lookup mémoire échoué : %s", exc)

            if known:
                answer = self._validate_choice_answer(packet, known.get("answer"))
                if answer is not None:
                    confidence = float(known.get("confidence") or 1.0)
                    if self.logger:
                        self.logger.info(
                            "AnswerEngine : réponse mémoire utilisée q=%s conf=%.2f indices=%s",
                            question_id,
                            confidence,
                            answer["indices"],
                        )
                    return {
                        "ok": True,
                        "source": "memory",
                        "confidence": confidence,
                        "answer": answer,
                    }

        # 2) LLM.
        if self.llm_solver is None:
            return {
                "ok": False,
                "source": "llm",
                "reason": "llm_disabled",
            }

        try:
            llm = self.llm_solver.solve(packet)
        except Exception as exc:
            if self.logger:
                self.logger.info("AnswerEngine : LLM indisponible/erreur : %s", exc)
            return {
                "ok": False,
                "source": "llm",
                "reason": f"llm_error:{exc}",
            }

        if not llm:
            return {
                "ok": False,
                "source": "llm",
                "reason": "llm_no_answer",
            }

        answer = self._validate_choice_answer(packet, llm)
        if answer is None:
            return {
                "ok": False,
                "source": "llm",
                "reason": "llm_answer_invalid",
            }

        confidence = float(llm.get("confidence", 0.5))
        if confidence < self.min_confidence:
            if self.logger:
                self.logger.info(
                    "AnswerEngine : LLM rejeté, confiance %.2f < %.2f",
                    confidence,
                    self.min_confidence,
                )
            return {
                "ok": False,
                "source": "llm",
                "reason": "confidence_too_low",
                "confidence": confidence,
            }

        if self.logger:
            self.logger.info(
                "AnswerEngine : LLM %s/%s conf=%.2f indices=%s",
                llm.get("provider"),
                llm.get("model"),
                confidence,
                answer["indices"],
            )

        return {
            "ok": True,
            "source": "llm",
            "confidence": confidence,
            "provider": llm.get("provider"),
            "model": llm.get("model"),
            "answer": answer,
        }
