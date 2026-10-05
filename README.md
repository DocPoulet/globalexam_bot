# GlobalExam Bot — v0.6

V0.6 consolide la détection avant de reprendre l'automatisation des exercices.

## Changements

- URL : `https://general.global-exam.com/`
- profil Chromium persistant ;
- détection de connexion sur la page et dans les iframes ;
- analyse de la page principale et de tous les iframes accessibles ;
- extraction des boutons, inputs, labels, rôles ARIA et `data-testid` ;
- meilleure détection des questions et réponses ;
- diagnostics JSON + HTML + captures ;
- sauvegarde du HTML de chaque iframe ;
- commande `frames` pour afficher les URLs des frames détectés.

## Installation

```text
install.bat
```

Puis :

```text
run.bat
```

## Premier lancement

Connecte-toi manuellement. Le profil Chromium est conservé dans `profile/`.
Lors des lancements suivants, la session est réutilisée si GlobalExam ne l'a pas expirée.

## Test conseillé

1. Ouvre un vrai exercice.
2. Tape `frames`.
3. Tape `a`.
4. Vérifie le résumé affiché.

En cas de mauvaise détection, les fichiers les plus utiles sont :

```text
diagnostics/last_page.json
diagnostics/last_page.html
diagnostics/last_page.png
diagnostics/frame_*_*.html
```

## Suite prévue

La V0.6 sert à identifier correctement la structure réelle des exercices.
La version suivante pourra remettre la machine à états au-dessus de ce détecteur
et gérer proprement les différents composants interactifs.
