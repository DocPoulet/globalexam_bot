import os
from pathlib import Path

from .base import LLMSolver


class LlamaCppSolver(LLMSolver):
    """
    Backend 100 % local : le GGUF est chargé directement dans le process
    Python via llama-cpp-python. Aucun serveur HTTP n'est requis.
    """

    def __init__(self, config, logger=None):
        super().__init__(config, logger)

        self.model_path = Path(str(config.get("model_path") or "")).expanduser()
        self.model_name = self.model_path.name or "local-gguf"

        if not self.model_path.exists():
            raise RuntimeError(
                "Modèle GGUF introuvable : "
                f"{self.model_path}. "
                "Place le modèle dans models/ ou lance "
                "download_qwen25_7b_q4km.bat."
            )

        try:
            from llama_cpp import Llama
        except Exception as exc:
            raise RuntimeError(
                "llama-cpp-python n'est pas installé. "
                "Lance install_local_llm.bat."
            ) from exc

        n_threads = int(config.get("n_threads", 0) or 0)
        if n_threads <= 0:
            n_threads = max(1, (os.cpu_count() or 4) - 1)

        n_ctx = int(config.get("n_ctx", 4096) or 4096)
        n_gpu_layers = int(config.get("n_gpu_layers", 0) or 0)
        verbose = bool(config.get("verbose", False))

        if self.logger:
            self.logger.info(
                "LLM local : chargement GGUF=%s n_ctx=%s "
                "n_threads=%s n_gpu_layers=%s",
                self.model_path,
                n_ctx,
                n_threads,
                n_gpu_layers,
            )

        try:
            self.llm = Llama(
                model_path=str(self.model_path),
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
                verbose=verbose,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Impossible de charger le modèle GGUF {self.model_path}: {exc}"
            ) from exc

        if self.logger:
            self.logger.info(
                "LLM local chargé : %s",
                self.model_name,
            )

    def solve(self, packet):
        if not self.supports(packet):
            return None

        messages = self.build_messages(packet)

        try:
            result = self.llm.create_chat_completion(
                messages=messages,
                temperature=float(self.config.get("temperature", 0.0)),
                max_tokens=int(self.config.get("max_tokens", 128) or 128),
            )
        except Exception as exc:
            raise RuntimeError(f"Inférence llama.cpp échouée : {exc}") from exc

        choices = result.get("choices") or []
        if not choices:
            raise RuntimeError("llama.cpp n'a renvoyé aucun choice")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if content is None:
            raise RuntimeError("llama.cpp n'a renvoyé aucun message.content")

        answer = self.validate_answer(packet, content)
        answer.update({
            "provider": "llama_cpp",
            "model": self.model_name,
        })
        return answer
