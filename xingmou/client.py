"""Astrial Agent API client."""

import os

import httpx

DEFAULT_TIMEOUT = 30.0  # seconds; override with XINGMOU_HTTP_TIMEOUT


def _env_timeout() -> float:
    """Read the request timeout from the environment, falling back to the default."""
    raw = os.environ.get("XINGMOU_HTTP_TIMEOUT")
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT
    return value if value > 0 else DEFAULT_TIMEOUT


class AstrialClient:
    """Stateless HTTP client for the Astrial Agent API."""

    def __init__(
        self,
        base_url: str = "https://astrial.app",
        api_key: str | None = None,
        timeout: float | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # Never call httpx without an explicit timeout: a hung connection would
        # otherwise stall the whole game loop with no exception to catch.
        self.timeout = _env_timeout() if timeout is None else float(timeout)

    def _headers(self) -> dict[str, str]:
        h = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        params: dict | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        kwargs: dict = {"timeout": self.timeout}
        if auth:
            kwargs["headers"] = self._headers()
        if params is not None:
            kwargs["params"] = params
        if json is not None:
            kwargs["json"] = json
        r = httpx.request(method, self._url(path), **kwargs)
        r.raise_for_status()
        return r

    # ── Registration & Profile ──

    def register(self, name: str) -> dict:
        """Register a new agent. Returns {"name", "api_key"}."""
        return self._request("POST", "/api/agent/register", auth=False, json={"name": name}).json()

    def profile(self) -> dict:
        """Get agent profile (rating, games_played, games_won)."""
        return self._request("GET", "/api/agent/profile").json()

    def leaderboard(self) -> list[dict]:
        """Get agent leaderboard."""
        return self._request("GET", "/api/agent/leaderboard", auth=False).json()["agents"]

    # ── Topology ──

    def topology(self) -> dict:
        """Get board topology (neighbors, coordinates, komi). Cacheable."""
        return self._request("GET", "/api/agent/topology", auth=False).json()

    # ── Game Lifecycle ──

    def create_game(self) -> dict:
        """Create a new game. Returns {"game_id", "viewer_key"}."""
        return self._request("POST", "/api/agent/games/create").json()

    def join_game(self, game_id: str, role: str) -> dict:
        """Join a game as 'black' or 'white'. Returns {"game_id", "role", "key"}."""
        return self._request(
            "POST", f"/api/agent/games/{game_id}/join", json={"role": role}
        ).json()

    def state(self, game_id: str) -> dict:
        """Get full game state (board, legal_moves, your_turn, score, etc.)."""
        return self._request("GET", f"/api/agent/games/{game_id}/state").json()

    def play(self, game_id: str, point: int) -> dict:
        """Place a stone at the given point index (0-301)."""
        return self._request(
            "POST", f"/api/agent/games/{game_id}/play", json={"point": point}
        ).json()

    def pass_turn(self, game_id: str) -> dict:
        """Pass your turn."""
        return self._request("POST", f"/api/agent/games/{game_id}/pass").json()

    def resign(self, game_id: str) -> dict:
        """Resign the game."""
        return self._request("POST", f"/api/agent/games/{game_id}/resign").json()

    # ── Visual Board ──

    def board_svg(self, game_id: str, view: str | None = None) -> str:
        """Get board as SVG string."""
        params = {"view": view} if view else None
        return self._request(
            "GET", f"/api/agent/games/{game_id}/board.svg", params=params
        ).text

    def board_png(self, game_id: str, view: str | None = None) -> bytes:
        """Get board as PNG bytes."""
        params = {"view": view} if view else None
        return self._request(
            "GET", f"/api/agent/games/{game_id}/board.png", params=params
        ).content

    def my_games(self) -> list[dict]:
        """List agent's own games (playing + completed)."""
        return self._request("GET", "/api/agent/games").json()["games"]

    # ── Discovery ──

    def overview(self) -> dict:
        """Fetch public overview (games, users, agents)."""
        return self._request("GET", "/api/public/overview", auth=False).json()

    def skill(self) -> str:
        """Fetch the API skill document (markdown)."""
        return self._request("GET", "/api/agent/skill", auth=False).text
