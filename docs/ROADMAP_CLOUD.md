# GlobalExam Bot — Roadmap actualisée : mémoire communautaire sur Railway

**Référence :** V0.10.15 (2026-10-14)  
**Décision d'architecture :** hébergement cloud sur **Railway** pour l'API FastAPI et PostgreSQL ; **aucun ordinateur d'utilisateur ne sert de serveur**.  
**Statut :** plan de développement uniquement. Aucun service Railway n'a encore été provisionné ni mis en production.

## Architecture cible

```text
Poste A : bot Python + GGUF local + SQLite ──┐
Poste B : bot Python + GGUF local + SQLite ──┼── HTTPS ──> Railway : FastAPI
Poste C : bot Python + GGUF local + SQLite ──┘                   │
                                                                │ réseau privé
                                                                ▼
                                                        Railway : PostgreSQL
```

- **Côté utilisateur :** l'exécution des exercices, le modèle GGUF, les données personnelles et SQLite restent locaux ; une indisponibilité du cloud ne bloque pas le bot.
- **Côté cloud :** seule l'API FastAPI dispose de `DATABASE_URL` et accède à PostgreSQL ; la base n'a pas d'accès TCP public. Chaque client utilise une clé d'API révocable et ne reçoit jamais les identifiants SQL.
- **Données partagées :** uniquement les enregistrements minimisés acceptés par le protocole V1, et seulement dans le cadre de droits/consentements dûment vérifiés. Les empreintes peuvent parfois être réidentifiées par dictionnaire : **hashé ne veut pas dire anonyme**.
- **Sécurité par défaut :** `COMMUNITY_WRITES_ENABLED=false`, aucune synchronisation ni publication automatique depuis les bots. L'infrastructure en ligne n'implique pas l'autorisation de partager des contenus sous droits.

## État déjà réalisé

| Version | Contenu | État |
|---|---|---|
| V0.10.10 | Raccord catalogue V2 et AutoPilot existant | Implémenté |
| V0.10.11 | Journal, anti-double validation et transitions | Implémenté |
| V0.10.12 | Contrôle qualité, corrections vérifiées/contestées | Implémenté |
| V0.10.13 | Format d'empreintes et export local contrôlé | Implémenté |
| V0.10.14 | Prototype FastAPI + PostgreSQL, clés et consensus | Implémenté ; PostgreSQL réel non validé en cloud |
| V0.10.15 | Dockerfile Railway, port, migration pre-deploy, health SQL, documentation | Implémenté et testé hors ligne ; non déployé |

## Prochaines versions (V0.10.15 réalisée techniquement, pas encore déployée)

### V0.10.15 — Déploiement Railway prêt à l'emploi (implémenté ; non déployé)

**But :** rendre le serveur V0.10.14 déployable sur Railway, **sans lancer encore le partage public**.

- Ajouter une configuration Railway maintenable (documentation du tableau de bord et Dockerfile, car `railway.json` est déprécié en 2026), avec chemin explicite vers `server/Dockerfile` depuis la racine du dépôt.
- Rendre le port HTTP configurable via `$PORT` et exposer seulement l'API ; conserver PostgreSQL sur le réseau privé Railway.
- Utiliser un PostgreSQL provisionné dans Railway et référencer son `DATABASE_URL` comme variable de service, sans secret codé en dur.
- Prévoir une commande idempotente d'initialisation/migration du schéma (`server.admin init-db`) distincte du démarrage de l'API.
- Vérifier le démarrage et les probes de santé/readiness ; une réponse HTTP ne doit pas être interprétée à tort comme preuve que la base fonctionne.
- Fournir un guide pas à pas : création du projet Railway, ajout des deux services, variables, domaines HTTPS, migrations et dépannage ; le déploiement effectif nécessitera l'action du propriétaire du compte Railway.
- Documenter les coûts potentiels et les mesures de limitation des dépenses, sans supposer un tarif ou une gratuité permanents.

**Critère de sortie :** une installation de test sur Railway peut exposer `/healthz`, obtenir une connexion PostgreSQL privée et effectuer les migrations sans utiliser le PC comme serveur. **Écritures bloquées.**

### V0.10.16 — Staging cloud et tests PostgreSQL réels

**But :** valider la sécurité et la stabilité de l'infrastructure hébergée.

- Exécuter les tests d'intégration contre une véritable instance PostgreSQL de staging, avec jeux de données artificiels.
- Tester clés invalides, révocation, quotas, doublons, contradictions, migrations et indisponibilité de la base.
- Mettre en place journaux prudents (sans clés, URL de session ni données d'exercice), alarmes simples, sauvegardes et procédure de restauration.
- Vérifier séparément `healthz` (processus) et une sonde de disponibilité réelle de la base ; configurer les healthchecks Railway.
- Documenter une procédure de retour arrière et la séparation staging/production.

**Critère de sortie :** tous les scénarios d'intégration et un exercice de restauration passent. **Pas de contribution réelle.**

### V0.10.17 — Client connecté en lecture seule, facultatif

**But :** permettre aux installations de consulter le service sans dépendre de lui.

- Ajouter un connecteur HTTPS isolé du `QuestionEngine` et du LLM (URL du service, timeout, retries bornés, schéma validé).
- Stocker la clé client dans une variable d'environnement ou un stockage de secrets adapté, jamais dans le dépôt ni dans les logs.
- Activer la consultation seulement sur consentement explicite de l'utilisateur : même une empreinte peut révéler une activité.
- Distinguer `consensus`, `pending`, `disputed`, `not_found` et serveur indisponible ; ne jamais interpréter un résultat incertain comme réponse vérifiée.
- Priorité de décision projetée : SQLite locale vérifiée → consultation communautaire opt-in admissible → LLM local → repli existant. Aucune télémétrie ni publication automatique.

**Critère de sortie :** un client peut consulter une base de test, mais reste pleinement fonctionnel hors ligne. **Écritures client désactivées.**

### V0.10.18 — Gouvernance, droits et protection des données

**But :** définir si et comment de vraies contributions pourraient légalement et éthiquement être partagées.

- Vérifier les conditions d'utilisation, droits sur le contenu et droits sur les données dérivées ; ne pas présumer qu'un hash donne un droit de redistribution.
- Définir la finalité, la conservation, les droits d'accès/suppression et les responsabilités de traitement (RGPD si applicable).
- Ajouter consentement granulaire, retrait des contributions, possibilité de révocation/rotation des clés, transparence sur ce qui est envoyé.
- Définir les règles d'admission et de modération ; auditer les risques de réidentification et de pollution de la base.

**Critère de sortie :** revue des droits et politique de contribution approuvées avant toute activation du partage réel. Sinon : conserver durablement un service de test/lecture autorisée.

### V0.10.19 — Contributions volontaires et modération

**But :** activer progressivement l'upload **uniquement si le jalon V0.10.18 est satisfait**.

- Synchroniser en opt-in explicite, afficher un aperçu local avant le premier envoi, offrir un bouton d'arrêt/retrait.
- N'admettre que les réponses avec preuve forte ; réexaminer côté serveur les contributions au lieu de se fier aveuglément au champ `verified` déclaré par le client.
- Introduire quarantaine, anti-Sybil, contrôle des clients, supervision de la qualité et mécanismes de retrait individuel.
- Mettre les écritures à disposition d'un groupe pilote limité puis élargir si les indicateurs le justifient.

**Critère de sortie :** publication réversible et traçable, fausses réponses isolées, droits respectés ; pas d'activation automatique pour les utilisateurs existants.

### V0.10.20 — Production cloud, exploitation et coûts

**But :** rendre le service communautaire maintenable.

- Sauvegardes automatiques avec tests de restauration, mises à jour, surveillance de disponibilité, quotas, budget et alertes.
- Documenter rotation des clés, incident de sécurité, maintenance, rétention et suppression des données.
- Valider que l'arrêt ou la saturation de Railway n'interrompt jamais les bots locaux.
- Prévoir la migration vers un autre hébergeur PostgreSQL si nécessaire, sans réécrire les clients.

**Critère de sortie :** service exploitable à long terme avec niveau de disponibilité et budget définis.

## Après la branche cloud — V0.11.x

- Étendre progressivement le LLM local à `ordering`, `select`, `text_input` avec validation stricte des sorties.
- Mesurer les performances par type d'exercice, l'utilité de la mémoire et les erreurs de compréhension des corrections.
- Améliorer la robustesse aux changements du site sans dupliquer le moteur des réponses.

## Règles de développement conservées

1. **Pas de doublon :** le serveur réutilise le protocole V1 ; SQLite reste la mémoire locale de référence.
2. **Pas de secret partagé dans un ZIP ou GitHub :** les mots de passe PostgreSQL et les clés sont créés côté hébergement/utilisateur.
3. **Pas de serveur sur le PC de l'utilisateur :** Docker Compose local reste un moyen facultatif de développement/test, pas l'architecture de production.
4. **Aucun upload sans accord :** `COMMUNITY_WRITES_ENABLED=false` tant que les jalons juridiques, de confidentialité et de sécurité ne sont pas remplis.
5. **Chaque version a des critères de validation :** ne pas confondre tests simulés, intégration PostgreSQL réelle et disponibilité effective sur Railway.
6. **Conserver `profile/`, `data/`, `models/`** au passage d'une version à la suivante.

## Documentation de l'hébergeur (à revalider au déploiement)

- Railway, guide FastAPI : https://docs.railway.com/guides/fastapi
- Railway, PostgreSQL : https://docs.railway.com/databases/postgresql
- Railway, déploiement depuis Docker Compose : https://docs.railway.com/guides/docker-compose
- Railway, chemin de Dockerfile : https://docs.railway.com/builds/dockerfiles
- Railway, variables et références : https://docs.railway.com/variables

**Guide concret V0.10.15 :** `docs/DEPLOIEMENT_RAILWAY_01015.md`.
