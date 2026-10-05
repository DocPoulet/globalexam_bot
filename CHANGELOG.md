# Changelog

## v0.5

### Corrigé

- URL principale remplacée par `https://general.global-exam.com/`.
- ancienne persistance `storage_state` remplacée par un profil Chromium persistant.
- détection de connexion renforcée.
- analyse du DOM entièrement revue.

### Ajouté

- profil Chromium complet dans `profile/`;
- inspection structurée de jusqu'à 2000 éléments visibles ;
- collecte des classes, IDs, rôles ARIA et data-testid ;
- classement de plusieurs questions candidates ;
- détection plus large des réponses ;
- export HTML complet ;
- export JSON complet ;
- capture d'écran de diagnostic ;
- `reset_profile.bat`.

## v0.4

- session persistante via storage_state ;
- statistiques ;
- historique de session.
