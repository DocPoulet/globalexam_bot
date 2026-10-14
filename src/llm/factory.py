from .ollama_solver import OllamaSolver
from .llama_cpp_solver import LlamaCppSolver
from .openai_compatible_solver import OpenAICompatibleSolver


def build_llm_solver(config, logger=None):
    config = config or {}
    if not config.get("enabled", True):
        return None

    provider = str(config.get("provider") or "ollama").strip().lower()
    if provider in ("llama_cpp", "llamacpp", "local", "gguf"):
        return LlamaCppSolver(config, logger)
    if provider == "ollama":
        return OllamaSolver(config, logger)
    if provider in ("openai", "openai_compatible", "compatible"):
        return OpenAICompatibleSolver(config, logger)

    raise ValueError(f"Unknown LLM provider: {provider}")
