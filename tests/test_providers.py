"""Provider binding: multiple OpenAI-compatible endpoints, ordered fallback."""

import pytest

from xingmou.providers import Provider, resolve_providers


def test_tokenplus_defaults():
    providers = resolve_providers({"TOKENPLUS_API_KEY": "tp"})

    assert [p.name for p in providers] == ["tokenplus"]
    assert providers[0].base_url == "https://api.tokenplus.cn/v1"
    assert providers[0].model == "gpt-4o"


def test_multiple_providers_are_bound_in_default_order():
    providers = resolve_providers(
        {"TOKENPLUS_API_KEY": "tp", "OPENROUTER_API_KEY": "or"}
    )

    assert [p.name for p in providers] == ["tokenplus", "openrouter"]
    assert providers[1].base_url == "https://openrouter.ai/api/v1"
    assert providers[1].model == "openai/gpt-4o"


def test_explicit_order_is_respected():
    providers = resolve_providers(
        {
            "XINGMOU_PROVIDERS": "openai, tokenplus",
            "OPENAI_API_KEY": "o",
            "TOKENPLUS_API_KEY": "t",
        }
    )

    assert [p.name for p in providers] == ["openai", "tokenplus"]


def test_providers_without_a_key_are_skipped():
    providers = resolve_providers(
        {"XINGMOU_PROVIDERS": "tokenplus,openrouter", "OPENROUTER_API_KEY": "or"}
    )

    assert [p.name for p in providers] == ["openrouter"]


def test_per_provider_model_beats_global_model():
    providers = resolve_providers(
        {
            "TOKENPLUS_API_KEY": "t",
            "TOKENPLUS_MODEL": "gpt-4o-mini",
            "XINGMOU_MODEL": "claude-sonnet-4",
        }
    )

    assert providers[0].model == "gpt-4o-mini"


def test_global_model_is_normalised_for_bare_id_providers():
    # OpenRouter wants "openai/gpt-4o"; tokenplus wants "gpt-4o".
    providers = resolve_providers(
        {
            "XINGMOU_PROVIDERS": "openrouter,openai",
            "OPENROUTER_API_KEY": "or",
            "OPENAI_API_KEY": "o",
            "XINGMOU_MODEL": "openai/gpt-4o",
        }
    )

    assert providers[0].model == "openai/gpt-4o"
    assert providers[1].model == "gpt-4o"


def test_custom_provider_from_env():
    providers = resolve_providers(
        {
            "XINGMOU_PROVIDERS": "myrelay",
            "MYRELAY_API_KEY": "k",
            "MYRELAY_BASE_URL": "https://relay.test/v1/",
            "MYRELAY_MODEL": "vision-model",
        }
    )

    assert providers == [
        Provider("myrelay", "https://relay.test/v1", "k", "vision-model")
    ]


def test_custom_provider_requires_base_url_and_model():
    with pytest.raises(ValueError, match="myrelay"):
        resolve_providers({"XINGMOU_PROVIDERS": "myrelay", "MYRELAY_API_KEY": "k"})


def test_no_provider_configured_raises_a_helpful_error():
    with pytest.raises(RuntimeError) as exc:
        resolve_providers({})

    assert "TOKENPLUS_API_KEY" in str(exc.value)
    assert "XINGMOU_PROVIDERS" in str(exc.value)


def test_duplicate_names_collapse():
    providers = resolve_providers(
        {"XINGMOU_PROVIDERS": "tokenplus,tokenplus", "TOKENPLUS_API_KEY": "t"}
    )

    assert len(providers) == 1
