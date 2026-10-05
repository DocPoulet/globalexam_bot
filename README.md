# GlobalExam Bot — v0.1

Première version du projet d'automatisation web avec Python et Playwright.

## Objectifs de la v0.1

Cette version permet de :

- lancer Chromium automatiquement ;
- ouvrir GlobalExam ;
- se connecter manuellement ;
- conserver la session dans `data/session.json` ;
- analyser grossièrement la page ouverte ;
- détecter :
  - les titres ;
  - les boutons ;
  - les champs `input` ;
  - les boutons radio ;
  - les cases à cocher ;
- enregistrer les événements dans `logs/bot.log`.

La v0.1 ne répond pas encore aux exercices automatiquement.

---

## Installation Windows

### Méthode simple

Double-cliquer sur :

```text
install.bat
```

Le script crée automatiquement un environnement virtuel Python et installe Playwright + Chromium.

### Installation manuelle

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

---

## Lancement

Double-cliquer sur :

```text
run.bat
```

Ou :

```bash
venv\Scripts\activate
python src/main.py
```

---

## Première utilisation

1. Le navigateur Chromium s'ouvre.
2. Connecte-toi à ton compte GlobalExam si nécessaire.
3. Va sur une page contenant un exercice.
4. Reviens dans la console.
5. Appuie sur Entrée.
6. Le programme affiche les éléments principaux détectés sur la page.

À la fermeture, la session est sauvegardée dans :

```text
data/session.json
```

La fois suivante, la connexion peut donc être restaurée automatiquement.

---

## Structure

```text
globalexam_bot_v0.1/
├── src/
│   ├── main.py
│   ├── browser.py
│   ├── page_analyzer.py
│   └── logger.py
├── data/
├── logs/
├── requirements.txt
├── install.bat
├── run.bat
├── .gitignore
└── README.md
```

---

## Roadmap immédiate

### v0.2
Détection plus précise des exercices :
- question ;
- réponses ;
- boutons de validation ;
- bouton suivant ;
- type de question.

### v0.3
Machine à états et navigation automatique.

### v0.4
Moteur de réponses configurable et historique des exercices.

---

## Remarque

Les sélecteurs spécifiques à GlobalExam devront être ajoutés après observation du DOM réel de plusieurs types d'exercices.
