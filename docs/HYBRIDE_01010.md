# V0.10.10 — Nouveau catalogue + ancien moteur

Cette version ne réécrit pas les exercices. Elle remplace le lanceur du
catalogue par un adaptateur aux modules observés le 14 octobre 2026.

- `run_auto.bat` : démarre l'ancien `AutoPilot` avec le nouveau catalogue.
- `run_v2.bat` : mode guidé V0.10.9 inchangé pour le diagnostic.
- Les routes `/activity/.../content/...` et `/activity/.../result` restent
  traitées par les moteurs QuestionEngine / FlowController existants.
- Sur `/levels/content`, on sélectionne d'abord un module ouvert, puis les
  autres modules, en recherchant **une carte ordinaire `En cours / Continuer`**.
- Pas de clic sur les cartes `locked`, `special`, `unverified`, les paliers,
  les conversations ou les boutons de feedback.
- Une carte n'est comptée comme lancée qu'après vérification de la route
  `/activity/...` ; elle ne sera pas relancée plusieurs fois dans la même
  session AutoPilot.
- Si aucune carte en cours n'est disponible, AutoPilot s'arrête et crée un
  diagnostic ; il n'ouvre **pas** automatiquement les activités déjà terminées.
- `FlowController` reconnaît les résultats via leur URL, même si leur texte
  n'est pas encore rendu.
- L'onglet `Correction` n'est plus considéré à lui seul comme une preuve
  d'une mauvaise réponse.

**Essai réel indispensable :** ce raccord a été testé avec des doubles de
page, pas sur le site connecté. Sauvegarder `profile/`, `data/` et `models/`
avant changement de version, sans les envoyer à qui que ce soit.

Pour démarrer : `run_auto.bat`. Pour diagnostiquer : `run_v2.bat`.
