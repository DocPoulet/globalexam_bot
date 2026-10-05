# Changelog

## v0.7

### Architecture
- création d'un système d'adaptateurs ;
- registre automatique d'adaptateurs ;
- séparation du routage de page et de la détection d'exercice ;
- séparation des actions communes.

### Adaptateurs
- `ordering_dragdrop` validé depuis les diagnostics ;
- `qcm` générique ;
- `select` générique ;
- `text_input` générique ;
- fallback `unknown`.

### Diagnostics analysés
- accueil GlobalExam ;
- exercice de classement chronologique ;
- frames analytics/publicitaires ignorées dans la logique métier.

## v0.6.1
- détection `.draggable-item` ;
- type `ordering_dragdrop`.
