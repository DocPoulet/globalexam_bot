"""Logique pure des réponses : conflits prioritaires sur tout consensus."""
import json


class QuotaExceeded(Exception):
    pass


class ClientConflict(Exception):
    pass


def compute_consensus(groups, min_confirmations=3):
    """Entrée : iterable (answer json/dict, nombre de clients indépendants)."""
    candidates = []
    for answer, contributors in groups:
        if isinstance(answer, str):
            answer = json.loads(answer)
        candidates.append({"answer": answer, "confirmations": int(contributors)})

    total = sum(item["confirmations"] for item in candidates)
    if not candidates:
        return {"status": "not_found", "confirmations": 0}
    if len(candidates) > 1:
        return {"status": "disputed", "confirmations": total, "variants": len(candidates)}

    only = candidates[0]
    if only["confirmations"] < min_confirmations:
        return {"status": "pending", "confirmations": only["confirmations"]}
    return {"status": "consensus", "confirmations": only["confirmations"], "answer": only["answer"]}
