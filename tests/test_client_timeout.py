"""Every HTTP call must carry an explicit timeout.

httpx's default is "wait forever", which used to stall the daemon's game loop
with no exception to catch.
"""

import httpx

from xingmou.client import DEFAULT_TIMEOUT, AstrialClient


def _json_response(url: str, payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", url))


def _install_fake_transport(monkeypatch) -> list[dict]:
    calls: list[dict] = []

    def handler(method: str, url, **kwargs) -> httpx.Response:
        calls.append({"method": method, "url": str(url), "kwargs": kwargs})
        path = str(url)
        if path.endswith("/register"):
            return _json_response(url, {"api_key": "k"})
        if path.endswith("/profile"):
            return _json_response(url, {"name": "x", "rating": 1500, "games_played": 0, "games_won": 0})
        if path.endswith("/leaderboard"):
            return _json_response(url, {"agents": []})
        if path.endswith("/topology"):
            return _json_response(url, {})
        if path.endswith("/create"):
            return _json_response(url, {"game_id": "g"})
        if path.endswith("/join"):
            return _json_response(url, {"game_id": "g", "role": "black", "key": "k"})
        if path.endswith("/state"):
            return _json_response(url, {"started": False})
        if path.endswith("/board.png"):
            return httpx.Response(200, content=b"\x89PNG\r\n", request=httpx.Request(method, url))
        if path.endswith("/board.svg"):
            return httpx.Response(200, text="<svg/>", request=httpx.Request(method, url))
        if path.endswith("/skill"):
            return httpx.Response(200, text="# skill", request=httpx.Request(method, url))
        if path.endswith("/games") and method == "GET":
            return _json_response(url, {"games": []})
        if path.endswith("/overview"):
            return _json_response(url, {"games": []})
        return _json_response(url, {"ok": True})

    monkeypatch.setattr(httpx, "request", handler)
    return calls


def test_every_api_call_passes_a_timeout(monkeypatch):
    calls = _install_fake_transport(monkeypatch)
    c = AstrialClient(base_url="https://example.test", api_key="k")

    c.register("n")
    c.profile()
    c.leaderboard()
    c.topology()
    c.create_game()
    c.join_game("g", "black")
    c.state("g")
    c.play("g", 1)
    c.pass_turn("g")
    c.resign("g")
    c.my_games()
    c.overview()
    c.board_png("g")
    c.board_svg("g", view="dark-north")
    c.skill()

    assert len(calls) == 15
    assert [call["kwargs"].get("timeout") for call in calls] == [DEFAULT_TIMEOUT] * 15


def test_timeout_comes_from_env(monkeypatch):
    monkeypatch.setenv("XINGMOU_HTTP_TIMEOUT", "7.5")
    assert AstrialClient().timeout == 7.5


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("XINGMOU_HTTP_TIMEOUT", "not-a-number")
    assert AstrialClient().timeout == DEFAULT_TIMEOUT


def test_explicit_timeout_wins_over_env(monkeypatch):
    monkeypatch.setenv("XINGMOU_HTTP_TIMEOUT", "7.5")
    assert AstrialClient(timeout=3).timeout == 3.0
