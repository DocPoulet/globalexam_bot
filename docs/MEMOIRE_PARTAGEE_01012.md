# V0.10.12 — Qualité de la mémoire avant partage

## Ce qui est opérationnel

- La base `data/knowledge.sqlite3` reste la source locale.
- Migration automatique non destructive de la base : nouvelles tables
  `answer_verifications`, `correction_suggestions` et `correction_conflicts`.
- Les réponses préexistantes sont conservées et étiquetées
  `legacy_unverified` (réutilisables localement, **non validées pour le partage**).
- Une correction peut être `verified`, `provisional` ou `rejected`.
- Un texte apparu après un clic n'est **jamais** une preuve suffisante.
- `verified` uniquement avec marquage DOM explicite ou une ligne de
  correction affirmant explicitement une unique réponse correspondant
  exactement à un choix (ou après validation avec état correct marqué).
- Les listes `ordering` dont le DOM peut montrer l'ancienne réponse restent
  **provisoires**.
- Deux corrections explicitement confirmées mais contradictoires sont
  marquées `disputed`, et aucune réponse litigieuse n'est rejouée ni partageable.
- La lecture des corrections ne prouve ni la réussite ni l'échec : le verdict
  est conservé séparément.

## Commande

Au terminal manuel du bot : `learnstats`.

Les nouveaux compteurs sont :
- `Vérifiées` : réponses nouvellement confirmées ;
- `Anciennes non vérifiées` : réponses sauvegardées par les versions précédentes ;
- `Suggestions` : solutions plausibles non réutilisées automatiquement.
- `Contradictoires` : réponses confirmées incompatibles, mises en quarantaine.

## Sécurité / partage

`config.json` contient `community.enabled=false` et
`community.upload_confirmed_answers=false`. Aucun client réseau communautaire
n'est implémenté dans cette version et aucun contenu ne part du PC.

La prochaine version pourra définir un contrat d'API, une authentification
et une vérification de licence/consentement avant tout transfert. Les captures,
URLs complètes, cookies, profil Chromium et traces ne doivent jamais être publiés.

Les données extraites d'exercices d'un service tiers sont potentiellement
protégées : ne pas republier leurs textes ou leurs solutions sans autorisation.
