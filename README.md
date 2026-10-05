# GlobalExam Bot — v0.7.10

## Progression automatique hors-question

Cette version ajoute une boucle dédiée aux écrans où il n'y a rien à répondre.

### Résultat / score / fin

Quand la page indique un résultat, un score ou une fin d'étape :

1. tentative de `Next` / `Suivant` / `Continuer` ;
2. sinon tentative de `Skip` / `Passer`.

### Flashcards

Le bot détecte :

- `tns-flashcards-prev`
- `tns-flashcards-next`

comme ID ou classe.

Tant que le bouton Next général n'est pas apparu, il parcourt les flashcards,
en privilégiant `tns-flashcards-next`.

Dès que Next apparaît, il clique dessus.

### Tant qu'il n'y a aucune question

Ordre de traitement :

1. question détectée -> arrêt ;
2. écran fini/score -> Next ou Skip ;
3. Next visible -> clic ;
4. flashcards -> parcours jusqu'à Next ;
5. Skip visible -> clic ;
6. sinon arrêt pour éviter de cliquer à l'aveugle.

## Automatique

La progression est lancée :

- juste après l'ouverture d'un exercice ;
- après un `next` ou `skip` manuel ;
- après une sélection si la question disparaît.

## Nouvelle commande

`advance`

Force la progression jusqu'à la prochaine vraie question.

## Commandes principales

- `launch`
- `advance`
- `menus`
- `active`
- `blocks`
- `a`
- `select X`
- `fallback X`
- `validate`
- `next`
- `skip`
- `list`
- `r`
- `q`
