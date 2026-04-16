"""Astrial Agent API client."""

import httpx


class AstrialClient:
    """Stateless HTTP client for the Astrial Agent API."""

    def __init__(self, base_url: str = "https://astrial.app", api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    # ── Registration & Profile ──

    def register(self, name: str) -> dict:
        """Register a new agent. Returns {"name", "api_key"}."""
        r = httpx.post(self._url("/api/agent/register"), json={"name": name})
        r.raise_for_status()
        return r.json()

    def profile(self) -> dict:
        """Get agent profile (rating, games_played, games_won)."""
        r = httpx.get(self._url("/api/agent/profile"), headers=self._headers())
        r.raise_for_status()
        return r.json()

    def leaderboard(self) -> list[dict]:
        """Get agent leaderboard."""
        r = httpx.get(self._url("/api/agent/leaderboard"))
        r.raise_for_status()
        return r.json()["agents"]

    # ── Topology ──

    def topology(self) -> dict:
        """Get board topology (neighbors, coordinates, komi). Cacheable."""
        r = httpx.get(self._url("/api/agent/topology"))
        r.raise_for_status()
        return r.json()

    # ── Game Lifecycle ──

    def create_game(self) -> dict:
        """Create a new game. Returns {"game_id", "viewer_key"}."""
        r = httpx.post(self._url("/api/agent/games/create"), headers=self._headers())
        r.raise_for_status()
        return r.json()

    def join_game(self, game_id: str, role: str) -> dict:
        """Join a game as 'black' or 'white'. Returns {"game_id", "role", "key"}."""
        r = httpx.post(
            self._url(f"/api/agent/games/{game_id}/join"),
            headers=self._headers(),
            json={"role": role},
        )
        r.raise_for_status()
        return r.json()

    def state(self, game_id: str) -> dict:
        """Get full game state (board, legal_moves, your_turn, score, etc.)."""
        r = httpx.get(
            self._url(f"/api/agent/games/{game_id}/state"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def play(self, game_id: str, point: int) -> dict:
        """Place a stone at the given point index (0-301)."""
        r = httpx.post(
            self._url(f"/api/agent/games/{game_id}/play"),
            headers=self._headers(),
            json={"point": point},
        )
        r.raise_for_status()
        return r.json()

    def pass_turn(self, game_id: str) -> dict:
        """Pass your turn."""
        r = httpx.post(
            self._url(f"/api/agent/games/{game_id}/pass"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    def resign(self, game_id: str) -> dict:
        """Resign the game."""
        r = httpx.post(
            self._url(f"/api/agent/games/{game_id}/resign"),
            headers=self._headers(),
        )
        r.raise_for_status()
        return r.json()

    # ── Visual Board ──

    def board_svg(self, game_id: str, view: str | None = None) -> str:
        """Get board as SVG string."""
        params = {"view": view} if view else {}
        r = httpx.get(
            self._url(f"/api/agent/games/{game_id}/board.svg"),
            headers=self._headers(),
            params=params,
        )
        r.raise_for_status()
        return r.text

    def board_png(self, game_id: str, view: str | None = None) -> bytes:
        """Get board as PNG bytes."""
        params = {"view": view} if view else {}
        r = httpx.get(
            self._url(f"/api/agent/games/{game_id}/board.png"),
            headers=self._headers(),
            params=params,
        )
        r.raise_for_status()
        return r.content

    # ── Discovery ──

    def overview(self) -> dict:
        """Fetch public overview (games, users, agents)."""
        r = httpx.get(self._url("/api/public/overview"))
        r.raise_for_status()
        return r.json()

    def skill(self) -> str:
        """Fetch the API skill document (markdown)."""
        r = httpx.get(self._url("/api/agent/skill"))
        r.raise_for_status()
        return r.text
