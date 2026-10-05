def snapshot(page, adapter):
    try:
        analysis = adapter.analyze()
    except Exception:
        analysis = {}

    try:
        from common_actions import find_actions
        actions = find_actions(page)
    except Exception:
        actions = []

    return {
        "url": page.url,
        "adapter": analysis.get("adapter"),
        "exercise_type": analysis.get("exercise_type"),
        "answers_count": len(analysis.get("answers", [])),
        "placed_count": analysis.get("placed_count"),
        "remaining": analysis.get("remaining"),
        "actions": [
            {
                "kind": item["kind"],
                "text": item["text"],
                "disabled": item["disabled"],
            }
            for item in actions
        ],
    }


def diff(before, after):
    changes = []

    for key in (
        "url",
        "answers_count",
        "placed_count",
        "remaining",
    ):
        if before.get(key) != after.get(key):
            changes.append(
                f"{key}: {before.get(key)} -> {after.get(key)}"
            )

    if before.get("actions") != after.get("actions"):
        changes.append("actions visibles modifiées")

    return changes
