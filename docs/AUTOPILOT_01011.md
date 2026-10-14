# V0.10.11 — Comment lire les événements AutoPilot

| Événement | Signification |
|---|---|
| `question_detected` | Question identifiable observée (pas de validation) |
| `answer_used` | Mécanique de réponse tentée ; `source=memory` ou `llm` si disponible |
| `validation` | `status=clicked` : clic signalé par le moteur, **pas encore preuve de progression** |
| `correction` | `outcome=unknown` si GlobalExam n'a pas fourni de verdict lisible |
| `sqlite` | `status=saved` quand un `attempt_id` SQLite est confirmé |
| `navigation` | `confirmed=true` si l'écran a effectivement changé (URL ou texte) |
| `duplicate_prevented` | Même question/écran reconnu : nouvelle soumission interdite |
| `block` | Après cycles sans progrès, diagnostic dans `diagnostics/` |

Les événements sont écrits au format JSON Lines dans `logs/` ; une ligne par
événement avec l'heure UTC. L'historique est conservé d'une exécution à l'autre.
Les URLs sont réduites à leur chemin, sans paramètre ni fragment.

**À noter :** une réponse LLM à faible confiance peut encore entraîner le
fallback AutoQ historique. L'analyse exacte des bonnes réponses et la
conversion des corrections en mémoire structurée restent prévues pour V0.10.12.

**Test rapide** : une question ne doit jamais déclencher deux événements
`validation` avec le même `question_id` et le même chemin d'exercice au cours
d'une exécution. Si l'écran ne progresse pas, chercher `[VERROU]` ou
`[BLOCAGE]` et conserver le JSONL correspondant.
