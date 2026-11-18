"""choose_move must fall through bound providers and never silently give up."""

import pytest

import xingmou.brain as brain
from xingmou.providers import Provider

TOKENPLUS = Provider("tokenplus", "https://api.tokenplus.cn/v1", "k1", "gpt-4o")
OPENROUTER = Provider("openrouter", "https://openrouter.ai/api/v1", "k2", "openai/gpt-4o")

STATE = {
    "role": "black",
    "move_count": 0,
    "score": {"black": 0, "white": 0, "unclaimed": 1},
    "legal_moves": [42, 43],
}


def test_falls_back_to_the_next_provider(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(brain, "resolve_providers", lambda: [TOKENPLUS, OPENROUTER])

    def fake_complete(provider, messages):
        calls.append(provider.name)
        if provider.name == "tokenplus":
            raise RuntimeError("quota exhausted")
        return "thinking...\n42"

    monkeypatch.setattr(brain, "_complete", fake_complete)

    assert brain.choose_move(STATE, [b"png"]) == 42
    assert calls == ["tokenplus", "openrouter"]


def test_raises_when_every_provider_fails(monkeypatch):
    monkeypatch.setattr(brain, "resolve_providers", lambda: [TOKENPLUS, OPENROUTER])

    def always_fail(provider, messages):
        raise RuntimeError(f"{provider.name} down")

    monkeypatch.setattr(brain, "_complete", always_fail)

    with pytest.raises(RuntimeError) as exc:
        brain.choose_move(STATE, [b"png"])

    assert "tokenplus" in str(exc.value)
    assert "openrouter" in str(exc.value)


def test_stream_is_disabled_and_timeout_is_passed(monkeypatch):
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            message = type("Message", (), {"content": "7"})
            choice = type("Choice", (), {"message": message})
            return type("Response", (), {"choices": [choice]})

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})

    monkeypatch.setattr(brain, "OpenAI", FakeClient)
    monkeypatch.setenv("XINGMOU_LLM_TIMEOUT", "9")
    monkeypatch.setenv("XINGMOU_LLM_RETRIES", "0")
    monkeypatch.setenv("XINGMOU_LLM_MAX_TOKENS", "1024")

    assert brain._complete(TOKENPLUS, [{"role": "user", "content": "x"}]) == "7"
    assert captured["client"] == {
        "api_key": "k1",
        "base_url": "https://api.tokenplus.cn/v1",
        "timeout": 9.0,
        "max_retries": 0,
    }
    # TokenPlus streams by default, which would break the non-streaming parse.
    assert captured["request"]["stream"] is False
    assert captured["request"]["model"] == "gpt-4o"
    assert captured["request"]["max_tokens"] == 1024


def test_parse_response_still_accepts_pass_and_numbers():
    assert brain._parse_response("reasoning...\npass", [1, 2]) == "pass"
    assert brain._parse_response("choice: 43.", [42, 43]) == 43
