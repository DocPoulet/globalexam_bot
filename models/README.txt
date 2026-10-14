Place ici les fichiers .gguf.

Configuration par défaut :
Qwen/Qwen2.5-7B-Instruct-GGUF, quantification Q4_K_M.

Ce modèle officiel est shardé en deux fichiers :
- qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf
- qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf

Le bot pointe vers le premier fichier. llama.cpp retrouve automatiquement
le second shard lorsqu'il est dans le même dossier.

Tu peux aussi utiliser un autre modèle GGUF :
- copie-le dans ce dossier ;
- change llm.model_path dans config.json ;
- ou supprime le chemin configuré : le bot tentera le premier .gguf trouvé.

Aucun serveur Ollama n'est nécessaire.
