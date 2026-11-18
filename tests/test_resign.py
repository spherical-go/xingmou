"""The trailing player resigns once the opponent leads by XINGMOU_RESIGN_MARGIN."""

import pytest

import xingmou.player as player


class FakeClient:
    base_url = "https://example.test"

    def __init__(self, state: dict):
        self._state = state
        self.resigned = False
        self.fetched_views = False

    def state(self, game_id: str) -> dict:
        return self._state

    def resign(self, game_id: str) -> dict:
        self.resigned = True
        return {"winner": "black"}

    def board_png(self, game_id: str, view: str | None = None) -> bytes:
        self.fetched_views = True
        raise AssertionError("must not fetch board views when resigning")


def test_margin_default_env_and_disable(monkeypatch):
    monkeypatch.delenv("XINGMOU_RESIGN_MARGIN", raising=False)
    assert player._resign_margin() == player.DEFAULT_RESIGN_MARGIN == 0.05

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.05")
    assert player._resign_margin() == 0.05

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0")
    assert player._resign_margin() == 0.0

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "not-a-number")
    assert player._resign_margin() == player.DEFAULT_RESIGN_MARGIN


def test_score_gap_is_signed_for_both_roles():
    trailing_white = {"role": "white", "score": {"black": 0.55, "white": 0.44}}
    assert player._score_gap(trailing_white) == pytest.approx(0.11)

    leading_black = {"role": "black", "score": {"black": 0.55, "white": 0.44}}
    assert player._score_gap(leading_black) == pytest.approx(-0.11)


def test_trailing_player_resigns_without_calling_the_llm(monkeypatch):
    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.05")
    client = FakeClient({
        "role": "white",
        "your_turn": True,
        "move_count": 320,
        "score": {"black": 0.55, "white": 0.44, "unclaimed": 0.01},
        "legal_moves": [1, 2],
    })

    player.play_game(client, "g", poll_interval=0)

    assert client.resigned
    assert not client.fetched_views
