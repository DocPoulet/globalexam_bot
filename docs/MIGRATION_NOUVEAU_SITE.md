# Migration GlobalExam — octobre 2026

## Confirmé par captures utilisateur

- Page parcours `/levels/content`.
- En-têtes de module `button`, texte `MODULE N`, état `aria-expanded`.
- Panneau grille frère de l'en-tête (`grid-rows-[1fr]`).
- Cartes terminées `div.relative.cursor-pointer` avec `Terminée` / `Voir`.
- Cartes verrouillées `div.relative.cursor-default` avec `À débloquer`.
- Module 5 : 5 terminées, 5 verrouillées, palier `À PASSER`, un bloc conversation `Lancer`.

## Reste à observer

- Carte d'exercice normal non terminé mais déverrouillé.
- Page accessible en cliquant sur `Voir` (question, résultat ou récapitulatif).
- Boutons du nouveau flux d'exercices et navigation après validation.

## Prudence

L'adaptateur n'ouvre que les activités déjà terminées en mode guidé et ne déclenche jamais l'activité de conversation, le palier ou les cartes verrouillées. Les outils de diagnostic doivent être relus avant partage.

## Diagnostic du 14 octobre 2026 et test demandé

Le module 5 et le module 13 peuvent être développés simultanément.
Le module 5 a bien cinq cartes cliquables terminées et une conversation
spéciale. Le fichier reçu (`module_ouvert`) montre encore la route
`/levels/content` : il ne montre **pas** la page d'activité ouverte.

Avec la V0.10.4, `voir 5 1` déclenche automatiquement la capture et l'export du
résultat du clic ; plus besoin de `capture` + `export` manuellement.


## v0.10.5 — Confirmation d’ouverture

Une action Playwright qui clique ne signifie pas qu’une activité est ouverte.
Le diagnostic exporte la preuve d’écran attendue et distingue les 3 étapes
URL initiale → catalogue prêt → destination finale.

## Relevé réel — 14 octobre 2026

`Protect And Serve` est accessible depuis la carte `Voir` du module 5,
avec une route `/activity/4503599673099410/result` et 10 questions.
L'écran comprend les boutons numérotés, les trois onglets `Vos réponses`,
`Correction`, `Explication`, et `Rejouer l'activité`.

À partir de la v0.10.6, `resultat` et `review` inspectent ces éléments
sans soumettre de réponse. `rejouer` capture le prochain écran de question
pour permettre la suite de la migration.
