# Changelog

## v0.9.1

- ajout de `CorrectionLearner` ;
- base SQLite automatique `data/knowledge.sqlite3` ;
- sauvegarde automatique de chaque validation ;
- sauvegarde des réponses données et du snapshot de correction ;
- résultats `correct`, `incorrect`, `unknown`, `skipped` ;
- apprentissage d'une réponse seulement lorsqu'elle est suffisamment prouvée ;
- aucune réponse vide mémorisée comme correcte ;
- skips journalisés ;
- support automatique AutoQ/AutoPilot ;
- amélioration de la détection selected pour button/span choices ;
- commandes `learnstats`, `history N`, `known` ;
- fallback ordering routed through `QuestionEngine` pour conserver le contexte de tentative.

## v0.9.0

- QuestionExtractor universel ;
- paquet sémantique stable ;
- commandes `packet` et `savepacket`.
