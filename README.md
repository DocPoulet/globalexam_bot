# GlobalExam Bot — v0.7

La v0.7 remplace le gros détecteur unique par une architecture
d'adaptateurs spécialisés.

## Ce que montrent les diagnostics du dépôt

Les diagnostics actuellement présents couvrent réellement :

1. l'accueil GlobalExam ;
2. une activité de classement chronologique.

L'activité observée utilise :

```text
button.draggable-item
```

Les autres frames observées sont principalement des frames publicitaires,
analytics ou tracking et ne correspondent pas au contenu pédagogique.

## Architecture

```text
src/
├── adapters/
│   ├── base.py
│   ├── ordering.py
│   ├── qcm.py
│   ├── select.py
│   ├── text_input.py
│   └── unknown.py
├── adapter_registry.py
├── browser.py
├── common_actions.py
├── diagnostics.py
├── logger.py
├── main.py
└── page_router.py
```

## Adaptateurs

### ordering_dragdrop

Validé à partir des diagnostics réels.

Détecte :

```text
button.draggable-item
```

Commandes :

```text
drag 1 3
```

### qcm

Préparé pour :

```text
input[type="radio"]
input[type="checkbox"]
```

Commande :

```text
choose 2
```

### select

Préparé pour les listes HTML `<select>`.

Commande :

```text
select 1 3
```

### text_input

Préparé pour :

```text
textarea
input[type="text"]
```

Commande :

```text
fill 1 réponse
```

## Actions communes

```text
skip
validate
next
```

## Important

Les adaptateurs QCM/select/text sont génériques pour le moment :
ils devront être ajustés à partir de diagnostics réels de ces types
d'activités GlobalExam.

Le seul adaptateur actuellement validé avec le DOM réel est
`ordering_dragdrop`.
