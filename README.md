# GlobalExam Bot — v0.9.1

## CorrectionLearner : mémoire automatique

La V0.9.1 ajoute une mémoire locale persistante autour du `QuestionExtractor`
de la V0.9.0.

À chaque validation, le bot enregistre automatiquement :

- le `question_id` stable ;
- le type de question et l'adaptateur ;
- la consigne, le contexte et le paquet de question ;
- la réponse réellement sélectionnée/saisie ;
- le texte et les indices DOM visibles sur l'écran de correction ;
- le résultat : `correct`, `incorrect` ou `unknown` ;
- la réponse correcte lorsqu'elle peut être démontrée ;
- l'URL avant/après validation.

Un skip est également journalisé avec le résultat `skipped`.

## Base locale

La mémoire est stockée automatiquement dans :

```text
data/knowledge.sqlite3
```

SQLite est inclus dans Python : aucune dépendance supplémentaire n'est
nécessaire.

Tables principales :

```text
questions
attempts
learned_answers
```

### `questions`

Une ligne par `question_id`, avec le paquet sémantique et le nombre de fois où
la question a été rencontrée.

### `attempts`

Une ligne par validation/skip : réponse envoyée, résultat, correction et
preuves utilisées.

### `learned_answers`

Contient seulement les réponses que le bot a pu apprendre avec suffisamment
de certitude.

Une correction ambiguë n'est jamais transformée arbitrairement en bonne
réponse : elle reste `unknown` et le snapshot de correction est conservé pour
améliorer le parseur plus tard.

## Apprentissage

Si une tentative est explicitement reconnue comme correcte, la réponse donnée
peut devenir la réponse apprise pour ce `question_id`.

Si une tentative est incorrecte et que le DOM permet d'identifier clairement
la bonne réponse, celle-ci peut également être mémorisée.

Une réponse vide n'est jamais enregistrée comme réponse correcte.

## Types de réponses capturés

- QCM simple/multiple ;
- boutons et spans ;
- ordering ;
- selects ;
- champs texte ;
- fallback `unknown`.

Le `QuestionExtractor` améliore aussi la détection de sélection pour les
boutons/spans via `data-state` et `aria-pressed`.

## Commandes

```text
packet
```

Affiche le paquet sémantique courant.

```text
savepacket
```

Sauvegarde manuellement un paquet de diagnostic.

```text
learnstats
```

Affiche le nombre de questions, tentatives, réponses apprises et les résultats
observés.

```text
history 10
```

Affiche les 10 dernières tentatives mémorisées.

```text
known
```

Affiche la réponse déjà apprise pour la question actuellement affichée.

## AutoPilot

La mémoire est branchée directement dans `QuestionEngine`, donc elle fonctionne
aussi avec AutoQ/AutoPilot : il n'est pas nécessaire d'utiliser les commandes
manuelles pour remplir la base.

Le flow navigateur et la navigation flashcards de la V0.8.18 sont conservés.

## Suite prévue

V0.9.2 : premier `LLMSolver` pour QCM / button_choice / span_choice, avec ordre
de priorité :

```text
réponse déjà apprise
        ↓ sinon
LLM
        ↓
réponse
        ↓
validation
        ↓
CorrectionLearner
```
