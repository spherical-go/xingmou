"""The trailing player resigns after N consecutive turns behind by the margin."""

import pytest

import xingmou.player as player


class FakeClient:
    base_url = "https://example.test"

    def __init__(self, states: list[dict] | dict):
        self._states = states if isinstance(states, list) else [states]
        self._calls = 0
        self.resigned = 0
        self.plays: list[int] = []
        self.fetched_views = False

    def state(self, game_id: str) -> dict:
        state = self._states[min(self._calls, len(self._states) - 1)]
        self._calls += 1
        return state

    def resign(self, game_id: str) -> dict:
        self.resigned += 1
        return {"winner": "black"}

    def play(self, game_id: str, point: int) -> dict:
        self.plays.append(point)
        return {"ok": True}

    def board_png(self, game_id: str, view: str | None = None) -> bytes:
        self.fetched_views = True
        raise AssertionError("must not fetch board views when resigning")


def _state(role: str, gap: float, move_count: int = 10) -> dict:
    """State where `role` is trailing by `gap` (negative = leading)."""
    other = "white" if role == "black" else "black"
    mine = 0.5 - gap / 2
    theirs = 0.5 + gap / 2
    return {
        "role": role,
        "your_turn": True,
        "move_count": move_count,
        "score": {role: mine, other: theirs, "unclaimed": 0.0},
        "legal_moves": [1, 2, 3],
    }


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Keep non-resigning turns from fetching images or calling a model."""
    monkeypatch.setattr(player, "_fetch_views", lambda client, game_id: [b"png"])
    monkeypatch.setattr(player, "choose_move", lambda state, images: 42)


def test_margin_default_env_and_disable(monkeypatch):
    monkeypatch.delenv("XINGMOU_RESIGN_MARGIN", raising=False)
    assert player._resign_margin() == player.DEFAULT_RESIGN_MARGIN == 0.05

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.07")
    assert player._resign_margin() == 0.07

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0")
    assert player._resign_margin() == 0.0

    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "not-a-number")
    assert player._resign_margin() == player.DEFAULT_RESIGN_MARGIN


def test_streak_default_env_and_clamp(monkeypatch):
    monkeypatch.delenv("XINGMOU_RESIGN_STREAK", raising=False)
    assert player._resign_streak() == player.DEFAULT_RESIGN_STREAK == 3

    monkeypatch.setenv("XINGMOU_RESIGN_STREAK", "5")
    assert player._resign_streak() == 5

    monkeypatch.setenv("XINGMOU_RESIGN_STREAK", "0")  # never below one turn
    assert player._resign_streak() == 1

    monkeypatch.setenv("XINGMOU_RESIGN_STREAK", "bogus")
    assert player._resign_streak() == player.DEFAULT_RESIGN_STREAK


def test_score_gap_is_signed_for_both_roles():
    trailing_white = {"role": "white", "score": {"black": 0.55, "white": 0.44}}
    assert player._score_gap(trailing_white) == pytest.approx(0.11)

    leading_black = {"role": "black", "score": {"black": 0.55, "white": 0.44}}
    assert player._score_gap(leading_black) == pytest.approx(-0.11)


def test_waits_for_three_consecutive_turns_behind(monkeypatch):
    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.05")
    monkeypatch.delenv("XINGMOU_RESIGN_STREAK", raising=False)
    client = FakeClient([_state("white", 0.11, i) for i in (10, 12, 14)])

    player.play_game(client, "g", poll_interval=0)

    assert client.resigned == 1
    assert client.plays == [42, 42]  # two moves before resigning on the third turn
    assert client.fetched_views is False


def test_a_single_turn_within_margin_resets_the_streak(monkeypatch):
    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.05")
    monkeypatch.delenv("XINGMOU_RESIGN_STREAK", raising=False)
    states = [
        _state("white", 0.11, 10),   # behind: 1
        _state("white", -0.11, 12),  # leading again: reset
        _state("white", 0.11, 14),   # behind: 1
        _state("white", 0.11, 16),   # behind: 2
        _state("white", 0.11, 18),   # behind: 3 -> resign
    ]
    client = FakeClient(states)

    player.play_game(client, "g", poll_interval=0)

    assert client.resigned == 1
    assert client.plays == [42, 42, 42, 42]


def test_streak_of_one_resigns_without_touching_the_llm(monkeypatch):
    monkeypatch.setenv("XINGMOU_RESIGN_MARGIN", "0.05")
    monkeypatch.setenv("XINGMOU_RESIGN_STREAK", "1")
    client = FakeClient(_state("white", 0.11, 320))

    player.play_game(client, "g", poll_interval=0)

    assert client.resigned == 1
    assert client.plays == []
    assert client.fetched_views is False
