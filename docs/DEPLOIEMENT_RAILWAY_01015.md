# V0.10.15 — Déployer l'API communautaire sur Railway

**Statut de livraison :** prêt à configurer, **pas encore déployé**. Aucun compte Railway, projet PostgreSQL, domaine public ni secret n'a été créé. Les clients restent exclusivement locaux et les écritures sont désactivées.

## Architecture

```text
Bot local (SQLite + GGUF) -- PAS CONNECTÉ --> HTTPS Railway (FastAPI)
                                                  |
                                                  +-- réseau privé --> PostgreSQL Railway
```

Seule l'API possède la chaîne de connexion SQL. Ne jamais créer de TCP Proxy ou de domaine public pour PostgreSQL. La base de données reste un service Railway séparé. Conserver les sauvegardes et la supervision pour la V0.10.16.

## Déploiement pas à pas dans l'interface Railway

1. Héberger les **fichiers de cette V0.10.15** dans un dépôt GitHub privé, par exemple sur une branche de test. **Ne pas publier** `data/`, `models/`, `profile/`, `server/.env` ni des diagnostics privés. Aucune action de publication ou de déploiement n'est réalisée par l'archive.
2. Sur https://railway.com/ créer un **projet vide** (de préférence environnement de test). Ajouter **Database → PostgreSQL** ; conserver la base privée (pas de `Public Access` / TCP Proxy).
3. Ajouter un service **GitHub Repo** pour cette version. Appeler le service `api` par exemple. Dans **Settings → Build**, garder **Root Directory** = `/` (racine du dépôt) et définir **Dockerfile Path** = `/server/Dockerfile`. Le Dockerfile copie `server/` **et** `src/`, donc ne pas choisir `/server` comme racine.
4. Dans les variables du service API, ajouter :

   ```text
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   COMMUNITY_WRITES_ENABLED=false
   COMMUNITY_MIN_CONFIRMATIONS=3
   COMMUNITY_READ_LIMIT_DAY=500
   COMMUNITY_WRITE_LIMIT_DAY=200
   ```

   Le nom `Postgres` doit être remplacé si tu as nommé le service PostgreSQL autrement. Utilise de préférence **Add Reference Variable** dans Railway plutôt que copier une URL contenant un mot de passe. Ne jamais utiliser `DATABASE_PUBLIC_URL` côté API.
5. **Settings → Deploy → Pre-deploy Command :** `python -m server.admin init-db --wait-seconds 60`. Configure un *pre-deploy timeout* raisonnable (par exemple 120 secondes). Cette migration idempotente est séparée du démarrage HTTP : si elle échoue, le déploiement doit échouer. Pas d'initialisation par le bot.
6. **Settings → Deploy → Healthcheck Path :** `/healthz`. Railway injecte `PORT`, écouté par `uvicorn` à `0.0.0.0`. Le contrôle de santé vérifie la présence des tables et la connexion SQL, pas seulement HTTP. En cas de base indisponible : **503**, pas faux 200.
7. Sous **Settings → Networking** du service **API seulement**, choisir **Generate Domain** pour disposer d'un domaine HTTPS (ex. `https://...up.railway.app`). Aucun accès public à PostgreSQL.
8. Vérifier le **deploy log** (migration `Tables PostgreSQL prêtes.`) puis ouvrir `https://<domaine-api>/healthz`. Attendu : `{"status":"ready","writes_enabled":false}`. Une erreur **503** signale une base non prête ; revoir les variables, la migration et les logs du pre-deploy.
9. `GET /v1/status` **sans clé** doit répondre **401** ; cela confirme le contrôle d'accès des routes métiers. Les requêtes d'écriture `POST /v1/contributions` sont **interdites par défaut**, y compris avec une clé valide.

**Option administration :** avec le CLI Railway authentifié, `railway ssh --service api -- python -m server.admin create-client --label "client-test"` exécute l'outil côté conteneur cloud. Il affiche la clé une fois : ne pas copier sa sortie dans un journal public et ne pas l'ajouter à un ZIP. Ce n'est pas nécessaire pour le test `/healthz`.

## Choix de configuration pour 2026

Le `railway.json` / `railway.toml` historique est **déprécié pour les nouveaux services**. Nous utilisons donc les réglages du tableau de bord et le Dockerfile **existant** de la V0.10.14, sans importer de configuration legacy. Une évolution ultérieure pourra utiliser l'Infrastructure as Code Railway `.railway/railway.ts` une fois son déploiement réellement vérifié.

Le serveur peut toujours être testé via `server/compose.yaml` en développement local, **mais il n'est pas prévu que les utilisateurs hébergent la base chez eux**.

## Limites et confidentialité

- Aucune synchronisation du bot n'est implémentée à cette version. La clé API et `DATABASE_URL` ne doivent jamais aller dans `config.json`, SQLite ou le dépôt Git.
- Les empreintes SHA-256 peuvent être ré-identifiables par dictionnaire. Avant d'activer les écritures, il faut examiner les droits sur les contenus, le consentement, la modération, les retraits et l'authenticité des corrections : un consensus entre comptes ne suffit pas.
- Le déploiement cloud lui-même peut générer des coûts. Activer alertes/budget, sauvegardes PostgreSQL et tests de restauration à la **V0.10.16** avant de passer en production.
- En cas de panne Railway, le bot local fonctionne comme avant (il n'utilise pas encore l'API).

## Dépannage

- **Railway cherche le mauvais Dockerfile :** Root `/`, Dockerfile Path `/server/Dockerfile` ; pas de racine `/server`.
- **Pre-deploy échoue :** vérifier la référence `DATABASE_URL`, l'état PostgreSQL et les logs de la commande. Ne pas exposer publiquement la base comme contournement.
- **502 / 503 :** vérifier `PORT`, healthcheck `/healthz`, table SQL et `DATABASE_URL` privé. 503 est volontaire en cas de problème SQL.
- **401 sur `/v1/status` :** normal sans `X-API-Key` valide.
- **403 sur contributions :** normal, `COMMUNITY_WRITES_ENABLED=false`.

## Documentation officielle

- https://docs.railway.com/guides/fastapi
- https://docs.railway.com/builds/dockerfiles
- https://docs.railway.com/databases/postgresql
- https://docs.railway.com/deployments/pre-deploy-command
- https://docs.railway.com/deployments/healthchecks
- https://docs.railway.com/config-as-code
