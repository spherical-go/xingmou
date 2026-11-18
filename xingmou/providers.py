"""LLM provider binding: several OpenAI-compatible endpoints, ordered fallback.

Every provider speaks the OpenAI Chat Completions wire format, so binding one is
just a base URL, a key and a model id. Multiple providers are resolved from the
environment at call time; ``choose_move`` tries them in order and falls through
on failure.

Environment:

- ``XINGMOU_PROVIDERS`` — comma-separated order, default ``tokenplus,openrouter,openai``.
- ``<NAME>_API_KEY`` — key for provider ``NAME`` (e.g. ``TOKENPLUS_API_KEY``).
- ``<NAME>_BASE_URL`` — optional base URL override.
- ``<NAME>_MODEL`` — optional model override, beats ``XINGMOU_MODEL``.
- ``XINGMOU_MODEL`` — model for every provider that has no ``<NAME>_MODEL``.

Built-ins (name → default base URL / model):

- ``tokenplus``  → ``https://api.tokenplus.cn/v1`` / ``gpt-4o``
- ``openrouter`` → ``https://openrouter.ai/api/v1`` / ``openai/gpt-4o``
- ``openai``     → ``https://api.openai.com/v1`` / ``gpt-4o``

Any other name may be listed in ``XINGMOU_PROVIDERS`` as long as its
``<NAME>_BASE_URL``, ``<NAME>_MODEL`` and ``<NAME>_API_KEY`` are set.
"""

import os
from dataclasses import dataclass
from typing import Mapping

ORDER_ENV = "XINGMOU_PROVIDERS"
GLOBAL_MODEL_ENV = "XINGMOU_MODEL"
DEFAULT_ORDER = ("tokenplus", "openrouter", "openai")


@dataclass(frozen=True)
class ProviderSpec:
    api_key_env: str
    base_url: str
    default_model: str


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str

    def __str__(self) -> str:
        return f"{self.name} ({self.model})"


BUILTIN_PROVIDERS: dict[str, ProviderSpec] = {
    "tokenplus": ProviderSpec("TOKENPLUS_API_KEY", "https://api.tokenplus.cn/v1", "gpt-4o"),
    "openrouter": ProviderSpec("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/gpt-4o"),
    "openai": ProviderSpec("OPENAI_API_KEY", "https://api.openai.com/v1", "gpt-4o"),
}


def _env_prefix(name: str) -> str:
    """TOKENPLUS_API_KEY style prefix for a provider name."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name)
    return cleaned.upper()


def _normalise_model(name: str, model: str) -> str:
    """Drop OpenRouter's ``openai/`` prefix for endpoints that take bare ids."""
    if name in ("openai", "tokenplus") and model.startswith("openai/"):
        return model[len("openai/"):]
    return model


def resolve_providers(env: Mapping[str, str] | None = None) -> list[Provider]:
    """Resolve every configured provider, in the order they should be tried.

    Providers without an API key are skipped, so binding more keys is always
    safe. Raises RuntimeError when no provider is configured and ValueError
    when a custom provider is missing its base URL or model.
    """
    env = os.environ if env is None else env

    raw_order = env.get(ORDER_ENV, "")
    order = [part.strip() for part in raw_order.split(",") if part.strip()]
    if not order:
        order = list(DEFAULT_ORDER)

    providers: list[Provider] = []
    seen: set[str] = set()
    for name in order:
        if name in seen:
            continue
        seen.add(name)

        spec = BUILTIN_PROVIDERS.get(name)
        prefix = _env_prefix(name)
        api_key = (env.get(f"{prefix}_API_KEY") or "").strip()
        if not api_key:
            continue

        base_url = env.get(f"{prefix}_BASE_URL") or (spec.base_url if spec else "")
        model = (
            env.get(f"{prefix}_MODEL")
            or env.get(GLOBAL_MODEL_ENV)
            or (spec.default_model if spec else "")
        )
        if not base_url or not model:
            raise ValueError(
                f"provider '{name}' 缺少配置：需要 {prefix}_API_KEY、"
                f"{prefix}_BASE_URL 和 {prefix}_MODEL"
            )

        providers.append(
            Provider(
                name=name,
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=_normalise_model(name, model),
            )
        )

    if not providers:
        raise RuntimeError(
            "没有可用的 LLM provider：请至少设置 TOKENPLUS_API_KEY、"
            "OPENROUTER_API_KEY 或 OPENAI_API_KEY 之一（可用 "
            f"{ORDER_ENV} 指定顺序）"
        )
    return providers
