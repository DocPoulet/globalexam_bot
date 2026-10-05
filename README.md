# GlobalExam Bot — v0.5

Cette version corrige plusieurs défauts des versions précédentes.

## Correction principale

L'URL utilisée est désormais :

```text
https://general.global-exam.com/
```

Lorsqu'aucune session n'est active, GlobalExam peut rediriger vers :

```text
https://auth.global-exam.com/login
```

## Nouveau système de session

Les anciennes versions utilisaient `storage_state`.

La v0.5 utilise maintenant un **profil Chromium persistant complet** grâce à :

```python
launch_persistent_context(...)
```

Cela conserve plus fidèlement :

- cookies ;
- localStorage ;
- IndexedDB ;
- autres données du profil navigateur.

### Première utilisation

1. Lancer `run.bat`.
2. Se connecter manuellement.
3. Aller jusqu'à GlobalExam.
4. Appuyer sur Entrée dans le terminal.

### Utilisations suivantes

Le même profil Chromium est réutilisé automatiquement.

Si GlobalExam conserve la session côté serveur, le compte devrait rester connecté.

### Réinitialisation

Pour effacer le profil :

```text
reset_profile.bat
```

## Nouveau détecteur

La v0.5 n'utilise plus seulement quelques sélecteurs HTML supposés.

Elle inspecte jusqu'à 2000 éléments visibles et récupère notamment :

- tag HTML ;
- texte ;
- `id` ;
- classes ;
- rôle ARIA ;
- type d'input ;
- `name` ;
- placeholder ;
- aria-label ;
- data-testid.

Le bot tente ensuite de déterminer :

- la question probable ;
- les réponses candidates ;
- les boutons visibles ;
- les champs ;
- le type d'exercice.

## Diagnostics

À chaque commande `a` ou `dump`, la v0.5 génère :

```text
diagnostics/last_page.json
diagnostics/last_page.html
```

ainsi qu'une copie horodatée et une capture PNG.

Ces fichiers permettent d'adapter précisément la version suivante à la structure réelle de GlobalExam.

## Commandes

```text
a     analyser la page
dump  sauvegarder les diagnostics
url   afficher l'URL actuelle
r     recharger la page
q     quitter
```

## Ce qu'il faut tester

Le plus important est d'ouvrir un véritable exercice puis d'utiliser :

```text
a
```

Si la détection reste incorrecte, le fichier :

```text
diagnostics/last_page.json
```

contiendra assez d'informations pour construire des sélecteurs spécifiques à l'interface réellement utilisée.
