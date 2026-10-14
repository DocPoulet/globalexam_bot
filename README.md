# GlobalExam Bot v0.10.15 — Préparation Railway

**Nouveau :** le serveur FastAPI peut être configuré sur Railway avec une base PostgreSQL privée. Le Dockerfile écoute maintenant `$PORT`, le contrôle `/healthz` teste réellement PostgreSQL et une migration SQL idempotente s'exécute en *pre-deploy* (commande documentée).

**[Guide Railway](docs/DEPLOIEMENT_RAILWAY_01015.md)** : étapes de déploiement, variables, migration, santé, vérification et sécurité.

**Ce qui ne change pas :** AutoPilot, nouveau catalogue V2, LLM GGUF et SQLite locaux. Aucun partage automatique, aucune base ou compte Railway créés, et `COMMUNITY_WRITES_ENABLED=false`.

Pour utiliser le bot : `run_auto.bat`. En changeant de version, conserver `profile/`, `data/` et `models/`.

---

Conserve intégralement la V0.10.13 : catalogue V2, AutoPilot, GGUF local et SQLite.

**Nouveau :** serveur expérimental FastAPI + PostgreSQL dans `server/`. Il accepte uniquement des empreintes V1 validées, jamais le HTML, le texte brut, les identifiants GlobalExam ou les cookies. Aucune contribution n'est envoyée par le bot, et les écritures du serveur sont désactivées par défaut.

Voir **`docs/SERVEUR_COMMUNAUTAIRE_01014.md`** pour le lancement local, les limites de sécurité, les droits à vérifier et les commandes Docker. Il faut créer soi-même les comptes/clé côté serveur : aucune clé administrateur n'est embarquée dans le ZIP.

## Tester le bot classique

`run_auto.bat` (inchangé). Conserver `profile/`, `data/`, `models/` lors d'un changement de version.

## Prévisualisation locale (sans envoi)

`community_status.bat` ou `python src/community_cli.py status`.

## Démarrage rapide (Windows + Docker Desktop)

Copier `server/.env.example` vers `server/.env`, remplacer `POSTGRES_PASSWORD`, puis double-cliquer `server_start_local.bat`. Une fois démarré, `http://127.0.0.1:8000/healthz` affiche l'état du serveur. La création d'une clé client reste une opération réservée à l'administrateur, documentée dans `docs/SERVEUR_COMMUNAUTAIRE_01014.md`.

## Roadmap actualisée : hébergement Railway (documentaire)

La production communautaire est désormais prévue sur **Railway** : FastAPI public en HTTPS, PostgreSQL privé, clients avec SQLite et LLM local. Le PC de l'utilisateur **ne sera pas serveur**. Voir `docs/ROADMAP_CLOUD.md` pour les jalons V0.10.15 à V0.10.20.

Cette archive est **la V0.10.14 sans modification fonctionnelle**, complétée uniquement par la roadmap. Rien n'est encore déployé sur Railway et les contributions restent désactivées.
