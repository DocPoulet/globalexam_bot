# GlobalExam Bot — v0.6.1

Version construite à partir des diagnostics réels récupérés sur GlobalExam.

## Ce que les diagnostics ont montré

L'exercice observé utilise :

```text
button.draggable-item
```

pour les éléments à classer.

La consigne observée était :

```text
Organisez les informations dans l'ordre chronologique
```

La v0.6 classait donc cet exercice en `unknown`, car elle cherchait surtout
des radios, checkbox, listes et champs texte.

## Nouveautés v0.6.1

- distinction `login / home / activity / other` ;
- reconnaissance spécifique des URL `/activity/.../content/...` ;
- détection de `button.draggable-item` ;
- nouveau type `ordering_dragdrop` ;
- les éléments draggable apparaissent maintenant comme réponses ;
- détection de `Passer`, `Valider`, `Suivant`, etc. ;
- commande expérimentale `drag X Y` ;
- commande `click X` ;
- diagnostics plus courts et ciblés.

## Exemple attendu

```text
Page        : activity
Type        : ordering_dragdrop
Question    : Organisez les informations dans l'ordre chronologique
Nb réponses : 3

1. Paul: ... [draggable]
2. Céline: ... [draggable]
3. Céline: ... [draggable]
```

## Commandes

```text
a          analyser
drag 1 3   déplacer le premier élément vers le troisième
click 2    cliquer sur le deuxième élément
skip       cliquer sur Passer
r          recharger
url        URL courante
q          quitter
```

## Suite

La prochaine étape sera de collecter plusieurs formats d'exercices
(GlobalExam n'utilise visiblement pas un seul composant) et de créer
un adaptateur par type d'activité.
