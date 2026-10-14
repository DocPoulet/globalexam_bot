import json
import os
import urllib.error
import urllib.request

from .base import LLMSolver


class OpenAICompatibleSolver(LLMSolver):
    """Backend générique /v1/chat/completions compatible OpenAI."""

    def __init__(self, config, logger=None):
        super().__init__(config, logger)
        self.base_url = str(config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        self.model = str(config.get("model") or "")
        self.timeout = float(config.get("timeout_seconds", 35))
        self.api_key_env = str(config.get("api_key_env") or "OPENAI_API_KEY")

    def _request(self, packet, with_response_format=True):
        if not self.model:
            raise RuntimeError("LLM model is empty in config.json")

        api_key = os.getenv(self.api_key_env, "").strip()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": self.model,
            "temperature": float(self.config.get("temperature", 0.0)),
            "messages": self.build_messages(packet),
        }
        if with_response_format:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def solve(self, packet):
        if not self.supports(packet):
            return None

        try:
            data = self._request(packet, with_response_format=True)
        except urllib.error.HTTPError as exc:
            # Certains serveurs compatibles n'implémentent pas response_format.
            if exc.code not in (400, 404, 422):
                raise RuntimeError(f"LLM HTTP error {exc.code}") from exc
            try:
                data = self._request(packet, with_response_format=False)
            except Exception as retry_exc:
                raise RuntimeError(f"LLM request failed: {retry_exc}") from retry_exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM unavailable: {exc}") from exc

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("LLM response has no choices")
        content = ((choices[0].get("message") or {}).get("content"))
        if content is None:
            raise RuntimeError("LLM response has no message.content")

        answer = self.validate_answer(packet, content)
        answer.update({
            "provider": "openai_compatible",
            "model": self.model,
        })
        return answer
