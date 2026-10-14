import json
import urllib.error
import urllib.request

from .base import LLMSolver


class OllamaSolver(LLMSolver):
    """Backend local Ollama (/api/chat)."""

    def __init__(self, config, logger=None):
        super().__init__(config, logger)
        self.base_url = str(config.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
        self.model = str(config.get("model") or "qwen2.5:7b")
        self.timeout = float(config.get("timeout_seconds", 35))

    def solve(self, packet):
        if not self.supports(packet):
            return None

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": self.build_messages(packet),
            "options": {
                "temperature": float(self.config.get("temperature", 0.0)),
            },
        }

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama unavailable: {exc}") from exc

        content = ((data.get("message") or {}).get("content"))
        if content is None:
            raise RuntimeError("Ollama response has no message.content")

        answer = self.validate_answer(packet, content)
        answer.update({
            "provider": "ollama",
            "model": self.model,
        })
        return answer
