"""Regression tests for the CLI's "wait for opponent" loop.

The old code broke out of the wait on the very first poll because
``move_count >= 0`` and ``your_turn is not None`` are both always true, so
``xingmou play --create`` started playing into an empty seat.
"""

import xingmou.cli as cli
from click.testing import CliRunner


class FakeClient:
    """Minimal stand-in for AstrialClient.state()."""

    def __init__(self, states: list[dict]):
        self.states = list(states)
        self.calls = 0

    def state(self, game_id: str) -> dict:
        self.calls += 1
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]


def _freeze_clock(monkeypatch, step: float = 1.0) -> None:
    clock = {"now": 0.0}

    def now() -> float:
        clock["now"] += step
        return clock["now"]

    monkeypatch.setattr(cli.time, "time", now)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)


def test_waits_until_the_game_has_started(monkeypatch):
    _freeze_clock(monkeypatch)
    client = FakeClient([
        {"started": False, "move_count": 0},
        {"started": False, "move_count": 0},
        {"started": True, "move_count": 0},
    ])

    assert cli._wait_for_start(client, "g", timeout=60, poll=0) is True
    assert client.calls == 3


def test_returns_false_on_timeout(monkeypatch):
    _freeze_clock(monkeypatch)
    client = FakeClient([{"started": False, "move_count": 0}])

    assert cli._wait_for_start(client, "g", timeout=5, poll=0) is False
    assert client.calls >= 2


def test_finished_game_needs_no_waiting(monkeypatch):
    _freeze_clock(monkeypatch)
    client = FakeClient([
        {"started": False, "move_count": 0, "game_over": {"winner": "black"}},
    ])

    assert cli._wait_for_start(client, "g", timeout=60, poll=0) is True
    assert client.calls == 1


def test_old_server_without_started_waits_for_first_move(monkeypatch):
    _freeze_clock(monkeypatch)
    # It is Black's turn before the opponent joins, so `your_turn` must not be
    # treated as "game started" (the daemon had the same trap).
    client = FakeClient([
        {"move_count": 0, "your_turn": True},
        {"move_count": 1, "your_turn": False},
    ])

    assert cli._wait_for_start(client, "g", timeout=60, poll=0) is True
    assert client.calls == 2


class FakePlayClient:
    """Stand-in used by the `play --create` command tests."""

    base_url = "https://example.test"

    def __init__(self, state: dict):
        self._state = state

    def create_game(self) -> dict:
        return {"game_id": "g"}

    def join_game(self, game_id: str, role: str) -> dict:
        return {"role": role}

    def state(self, game_id: str) -> dict:
        return self._state


def test_play_create_does_not_start_before_opponent_joins(monkeypatch):
    _freeze_clock(monkeypatch)
    client = FakePlayClient({"started": False, "move_count": 0})
    monkeypatch.setattr(cli, "_get_client", lambda: client)

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("play_game() must not run before the game starts")

    monkeypatch.setattr(cli, "play_game", _unexpected)

    result = CliRunner().invoke(
        cli.main, ["play", "--create", "--color", "black", "--poll", "0"]
    )

    assert result.exit_code == 1, result.output
    assert "No opponent joined" in result.output


def test_play_create_starts_game_once_started(monkeypatch):
    _freeze_clock(monkeypatch)
    client = FakePlayClient({"started": True, "move_count": 0})
    started: list[tuple] = []
    monkeypatch.setattr(cli, "_get_client", lambda: client)
    monkeypatch.setattr(
        cli, "play_game", lambda c, game_id, **kwargs: started.append((game_id, kwargs))
    )

    result = CliRunner().invoke(
        cli.main, ["play", "--create", "--color", "black", "--poll", "0"]
    )

    assert result.exit_code == 0, result.output
    assert started and started[0][0] == "g"
