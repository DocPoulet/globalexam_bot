# V0.10.13 — Contrat local de synchronisation (aucun serveur)

## Objectif

Préparer un format **minimal** de contribution communautaire sans remplacer la mémoire SQLite existante. Aucun serveur, compte, clé d'API, appel HTTP ou import réseau n'est installé dans cette version.

Le bot fonctionne toujours comme en V0.10.12. `run_auto.bat` reste identique côté navigation/LLM.

## Contrat V1

Fichier JSON validé avec `docs/community_contribution_v1.schema.json`.

Une contribution contient :

- `question_fingerprint`: empreinte SHA-256 déterministe de la forme normalisée de la question (instruction + contexte + type + langue + ensemble des choix/éléments) ;
- `exercise_type`: famille d'exercice ;
- `answer`: liste d'empreintes **des libellés des bons choix**, pas des indices locaux ; pour ordering, ordre des empreintes ; pour select, empreinte du choix par champ ;
- `evidence_category`: origine **déclarée** de la vérification ;
- `record_fingerprint`: empreinte de la contribution (pour déduplication).

Les empreintes sont calculées par `src/community_protocol.py`, avec normalisation Unicode NFKC, casse et espaces. Les indices de boutons ne servent pas d'identité, ce qui évite d'associer la mauvaise réponse si les choix sont permutés.

### Données volontairement absentes

Aucune URL, instruction ou correction en clair, texte des choix, identifiant de question local, `attempt_id`, nom d'utilisateur, cookie, profil, trace ou timestamp individuel ne figure dans un export. Les champs supplémentaires sont **refusés** par le validateur.

⚠️ **Les hash SHA-256 ne sont PAS une anonymisation** : les textes courts sont vulnérables aux attaques par dictionnaire, et les empreintes révèlent une correspondance entre utilisateurs. Ils ne doivent **pas** être diffusés sans vérification des droits et de la confidentialité. Le protocole V1 est un aperçu local, non une autorisation de republier GlobalExam.

### Filtres

- Seules les réponses `answer_verifications.status='verified'`, dont la source figure dans la liste des preuves explicites, sont candidates.
- L'attempt de vérification doit correspondre à l'attempt de la réponse mémorisée.
- Les réponses `legacy_unverified`, `disputed`, les sources faibles et les suggestions sont exclues.
- `text_input` est exclu : aucun texte libre n'est publié, même comme hash de réponse.
- Les choix identiques/ambigus et les questions possiblement personnalisées (email, numéro, URL, etc.) sont exclus.
- Les captures et l'ensemble de `result_reviews` ne sont jamais lus par cet exportateur.

**Une source `verified` vient du client local et n'est pas une preuve indépendante** : le futur serveur devra valider indépendamment, résister aux contributions manipulées et gérer les contradictions. Un hash ne prouve rien sur la véracité d'une solution.

## Commandes Windows

Double-cliquer `community_status.bat` : affiche le nombre de contributions localement admissibles et les motifs d'exclusion.

Dans la racine du projet :

```powershell
python src/community_cli.py status
python src/community_cli.py export --confirm-review
python src/community_cli.py validate --input data/community_preview.json
```

`export --confirm-review` ne fait qu'écrire **un fichier local** `data/community_preview.json` (il refuse d'écraser un fichier existant). Ouvrir ce JSON et le vérifier avant tout usage externe. Ne pas l'envoyer au projet ou à des tiers sans autorisation explicite de partage des données dérivées.

## API future (V0.10.14+, NON IMPLÉMENTÉE)

- `POST /v1/contributions` : authentification, quotas, consentement explicite, validation côté serveur, modération et vérification des droits ;
- `GET /v1/answers/{fingerprint}` : accès seulement aux données légalement publiables, gestion des conflits et mécanisme de retrait ;
- `GET /v1/health` : contrôle de disponibilité.

Contrôles requis : droits sur les contenus du service tiers, protection contre les attaques par dictionnaire et l'empoisonnement, authentification sans exposer de secret serveur côté client, politique de suppression, journal de consentement et conditions d'utilisation. À décider **avant** tout upload effectif.

## Continuité

Les dossiers `profile/`, `data/` et `models/` de la version précédente restent inchangés. Les options `community.enabled` et `community.upload_confirmed_answers` restent `false`, et **aucun réseau communautaire n'est sollicité**.
