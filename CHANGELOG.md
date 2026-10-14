# Changelog

## V0.10.15 — Railway ready (non déployé)

- Respecte le port injecté `$PORT` en cloud ; conserve `8000` en développement Docker Compose.
- `/healthz` : vérifie que PostgreSQL répond et que les 3 tables requises existent ; HTTP 503 sinon.
- Migration idempotente `python -m server.admin init-db --wait-seconds 60`, protégée par verrou SQL ; configurable comme pre-deploy Railway.
- Exemple de variables non secrètes `server/railway.env.example` et guide complet de déploiement.
- N'utilise pas l'ancien format Railway `railway.json` déprécié en 2026.
- Aucun changement du bot, de la mémoire ou du LLM local ; pas de serveur hébergé sans intervention utilisateur.

# Révision de roadmap — 2026-10-14 (documentation uniquement)

- Hébergement de production décidé : Railway avec FastAPI et PostgreSQL sur réseau privé.
- Étapes planifiées V0.10.15–V0.10.20, séparation du cloud, de la connexion client et des contributions.
- Ajout de `docs/ROADMAP_CLOUD.md`. Aucune modification de comportement du bot ni du serveur V0.10.14.

# Changelog

## v0.10.14 — Infrastructure communautaire expérimentale

- Serveur FastAPI + PostgreSQL séparé de l'AutoPilot ; aucune connexion activée côté bot.
- Réutilisation du validateur `src/community_protocol.py` pour refuser tout champ supplémentaire.
- Clés API individuelles générées côté admin, stockage du SHA-256 des clés et révocation.
- Quotas journaliers et sérialisation des accès concurrents par client.
- Une seule contribution par question et par client ; duplicates idempotents, désaccords non écrasés.
- Consensus de 3 clients indépendants par défaut ; tout conflit → `disputed` sans réponse renvoyée.
- Écriture désactivée par défaut, réponse 403 avant revue de droit et déploiement.
- Docker Compose PostgreSQL 17 + API, exécution locale uniquement par défaut.
- Tests unitaires/simulations API (pas de promesse de test sur infrastructure hébergée).

## v0.10.13 — Empreintes et aperçu local

Conservée sans changement fonctionnel.
