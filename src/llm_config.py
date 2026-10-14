import json
from pathlib import Path


DEFAULT_CONFIG = {
    "enabled": True,
    "provider": "llama_cpp",
    "model_path": "models/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
    "temperature": 0.0,
    "min_confidence": 0.35,
    "n_ctx": 4096,
    "n_threads": 0,
    "n_gpu_layers": 0,
    "max_tokens": 128,
    "verbose": False,
    "timeout_seconds": 35,
    "api_key_env": "OPENAI_API_KEY",
}


def load_llm_config(base_dir, logger=None):
    base_dir = Path(base_dir)
    path = base_dir / "config.json"
    config = dict(DEFAULT_CONFIG)

    if not path.exists():
        if logger:
            logger.info("LLM config absent : valeurs par défaut llama.cpp local utilisées.")
        return config

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        if logger:
            logger.info("LLM config invalide, défauts utilisés : %s", exc)
        return config

    llm = raw.get("llm", raw)
    if isinstance(llm, dict):
        config.update(llm)

    model_path = config.get("model_path")
    if model_path:
        model_path = Path(str(model_path))
        if not model_path.is_absolute():
            model_path = base_dir / model_path
        config["model_path"] = str(model_path)

    # Si le chemin configuré n'existe pas, utilise automatiquement le
    # premier GGUF trouvé dans models/. Cela simplifie le remplacement
    # du modèle sans modifier config.json.
    if str(config.get("provider", "")).lower() in (
        "llama_cpp", "llamacpp", "local", "gguf"
    ):
        configured = Path(str(config.get("model_path") or ""))
        if not configured.exists():
            models_dir = base_dir / "models"
            if models_dir.exists():
                ggufs = sorted(models_dir.glob("*.gguf"))
                if ggufs:
                    # Pour les GGUF shardés, privilégie 00001-of-xxxxx.
                    first_shards = [
                        p for p in ggufs
                        if "-00001-of-" in p.name.lower()
                    ]
                    config["model_path"] = str(
                        (first_shards or ggufs)[0]
                    )

    return config
