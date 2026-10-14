# V0.10.14 — Infrastructure PostgreSQL/API (prototype local)

## Ce qui fonctionne

- API REST avec `X-API-Key` individuel (clé aléatoire générée par l'administrateur, seul son SHA-256 est conservé dans PostgreSQL).
- Validation stricte du protocole `src/community_protocol.py` avant stockage ; seuls les SHA-256 des questions et choix, un type, une source *déclarée* et des métadonnées sont stockés.
- Une voix par identité et par question. Une voix en double est ignorée ; une nouvelle réponse contradictoire de la même identité est rejetée.
- Quota quotidien par identité, en base, avec verrou transactionnel ; paramètres `COMMUNITY_READ_LIMIT_DAY` / `COMMUNITY_WRITE_LIMIT_DAY`.
- Une réponse n'est distribuée que si au moins 3 identités distinctes concordent **et** qu'aucune voix contradictoire n'existe (`consensus`). Sinon : `pending`, `disputed` ou `not_found`.
- Aucune synchronisation côté bot, aucun upload implicite, aucun remplacement de SQLite.

## Important — pas encore un service public

**Par défaut `COMMUNITY_WRITES_ENABLED=false`.** L'API refuse alors toute écriture, même avec clé valide. Le serveur n'a aucun moyen de certifier qu'une preuve de correction déclarée est authentique. Trois comptes sous contrôle d'une seule personne peuvent polluer le consensus ; les empreintes de textes connus sont réidentifiables par dictionnaire. Il n'existe pas encore de consentement applicatif audité, de modération humaine, de retrait public, de détection Sybil, de mécanisme de suppression à la demande ou de revue des droits sur les contenus GlobalExam.

**Ne pas déployer publiquement ou activer les contributions réelles avant :** examen des CGU/droits sur les données dérivées, règles RGPD, consentement explicite indépendant pour chaque contributeur, modération et retrait, validation des corrections à partir de preuves indépendantes, revue sécurité, HTTPS devant le serveur, limitation réseau et séparation des rôles SQL. L'absence de texte brut n'autorise pas automatiquement le partage. Les mots de passe des bases PostgreSQL ne doivent jamais être intégrés dans un logiciel client.

## Démarrer pour des tests locaux (Docker Desktop requis)

1. Extraire le projet ; conserver l'ancien `data/`, `profile/`, `models/`.
2. Copier `server/.env.example` en `server/.env` et choisir un mot de passe fort **alphanumérique** ; conserver `COMMUNITY_WRITES_ENABLED=false`.
3. Dans un terminal **à la racine du projet**, exécuter :

```powershell
docker compose --env-file server/.env -f server/compose.yaml up -d --build
docker compose --env-file server/.env -f server/compose.yaml run --rm api python -m server.admin init-db
docker compose --env-file server/.env -f server/compose.yaml run --rm api python -m server.admin create-client --label "poste-test"
```

La clé est affichée une fois, dans ton terminal ; garde-la privée. Pour révoquer :

```powershell
docker compose --env-file server/.env -f server/compose.yaml run --rm api python -m server.admin revoke-client --id <UUID_CLIENT>
```

`GET http://127.0.0.1:8000/healthz` répondra avec `writes_enabled:false`. On pourra tester les GET avec une clé valide via `X-API-Key`.

## API

- `GET /healthz` : serveur joignable (ne certifie pas la disponibilité PostgreSQL).
- `GET /v1/status` : nécessite `X-API-Key` ; version, drapeau écriture, minimum de confirmations, nombre de contributions de ce client.
- `GET /v1/answers/{question_fingerprint}` : nécessite `X-API-Key` ; réponse `consensus`/`pending`/`disputed`/`not_found` ; aucun texte brut.
- `POST /v1/contributions` : `X-API-Key` + JSON `{ "schema_version":"1.0", "platform":"globalexam", "records":[...] }`. Limitée à 25 enregistrements et 64 Kio de corps. **Interdite par défaut.**

**Ne pas envoyer** directement `data/community_preview.json` : son en-tête `network_upload:false` est un signal qu'il est destiné uniquement au disque. Le serveur refusera sa structure. Avant toute évolution permettant des uploads, développer un client opt-in distinct avec consentement explicite, gestion de retrait et politique de droits documentée.

## Validations

Tests HTTP isolés dans `server/tests/test_api.py`, sans base réelle. Une intégration sur PostgreSQL peut être exercée avec Docker en environnement de développement ; elle n'a pas encore été testée contre une instance accessible publiquement.

## Révocation et correction d'une contribution

`revoke-client --id UUID` invalide la clé et retire toutes les contributions associées de PostgreSQL, afin qu'elles ne puissent plus influencer les réponses. Une interface de gestion fine des retraits individuels reste à développer avant toute utilisation publique.
