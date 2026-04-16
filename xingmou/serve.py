"""Daemon mode for Railway/container deployment.

Fully autonomous: auto-registers, discovers games, plays continuously.
"""

import json
import logging
import os
import random
import string
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from .client import AstrialClient
from .player import play_game

log = logging.getLogger("xingmou")

# Daemon state (read by health/status endpoint)
_status = {
    "state": "starting",
    "name": None,
    "rating": None,
    "games_played": 0,
    "games_won": 0,
    "current_game": None,
    "error": None,
}
_lock = threading.Lock()


def _update(**kwargs):
    with _lock:
        _status.update(kwargs)


def _get_status() -> dict:
    with _lock:
        return dict(_status)


# ── Health HTTP server ──

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = json.dumps({"ok": True}).encode()
        elif self.path == "/":
            body = json.dumps(_get_status(), indent=2).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def _start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("Health server on :%d", port)


# ── Auto-register ──

def _ensure_registered(client: AstrialClient, name: str) -> AstrialClient:
    """Try to use existing key; if none, register a new agent."""
    # Already have a key — verify it
    if client.api_key:
        try:
            profile = client.profile()
            log.info("Authenticated as %s (rating %d)", profile["name"], profile["rating"])
            return client
        except Exception:
            log.warning("Existing API key invalid, will re-register")

    # Register
    log.info("Registering as %s ...", name)
    try:
        result = client.register(name)
        api_key = result["api_key"]
        log.info("✅ Registered! API key: %s", api_key)
        log.info("   Save this as XINGMOU_API_KEY to avoid re-registration on restart.")
        return AstrialClient(base_url=client.base_url, api_key=api_key)
    except Exception as e:
        log.error("Registration failed: %s", e)
        log.error("If agent '%s' already exists, set XINGMOU_API_KEY env var.", name)
        raise SystemExit(1)


# ── Game discovery ──

def _find_joinable_game(client: AstrialClient, my_name: str) -> tuple[str, str] | None:
    """Find a waiting game with an open seat. Returns (game_id, role) or None."""
    try:
        overview = client.overview()
    except Exception:
        return None

    for g in overview.get("games", []):
        if g.get("status") not in ("waiting", "ready"):
            continue

        bu = g.get("black_user")
        wu = g.get("white_user")

        # Don't join our own games
        if bu == my_name or wu == my_name:
            continue

        # Find an open seat
        if not bu:
            return g["game_id"], "black"
        if not wu:
            return g["game_id"], "white"

    return None


# ── Main loop ──

def _play_loop(client: AstrialClient, agent_name: str, prefer_color: str | None,
               use_png: bool, poll_interval: float):
    """Continuously find or create games and play them."""
    _update(state="ready")

    while True:
        try:
            # 1. Try to join an existing game
            found = _find_joinable_game(client, agent_name)
            if found:
                game_id, role = found
                log.info("Found joinable game %s — joining as %s", game_id, role)
                try:
                    client.join_game(game_id, role)
                except Exception as e:
                    log.warning("Failed to join %s: %s", game_id, e)
                    found = None

            # 2. No joinable game — create one
            if not found:
                color = prefer_color or random.choice(["black", "white"])
                result = client.create_game()
                game_id = result["game_id"]
                log.info("Created game %s", game_id)
                client.join_game(game_id, color)
                role = color

            _update(state="waiting", current_game=game_id)
            log.info("Playing as %s in %s", role, game_id)

            # 3. Wait for opponent
            timeout = float(os.environ.get("XINGMOU_WAIT_TIMEOUT", "600"))
            wait_start = time.time()
            while True:
                try:
                    state = client.state(game_id)
                except Exception:
                    time.sleep(3)
                    continue
                if "game_over" in state:
                    break
                if state.get("your_turn") is not None:
                    # Both players are in — check if opponent has joined
                    board = state.get("board", [])
                    if state.get("move_count", 0) > 0 or state.get("your_turn"):
                        break
                if time.time() - wait_start > timeout:
                    log.warning("Timeout waiting for opponent in %s", game_id)
                    break
                time.sleep(3)

            # 4. Play the game
            _update(state="playing")
            play_game(client, game_id, poll_interval=poll_interval, use_png=use_png)

            # 5. Update stats
            _update(state="idle", current_game=None)
            _sync_profile(client)

            pause = float(os.environ.get("XINGMOU_GAME_PAUSE", "10"))
            time.sleep(pause)

        except KeyboardInterrupt:
            log.info("Shutting down")
            _update(state="stopped")
            break
        except Exception as e:
            log.error("Error in game loop: %s", e)
            _update(state="error", error=str(e))
            time.sleep(15)


def _sync_profile(client: AstrialClient):
    try:
        p = client.profile()
        _update(
            name=p.get("name"),
            rating=p.get("rating"),
            games_played=p.get("games_played", 0),
            games_won=p.get("games_won", 0),
        )
    except Exception:
        pass


def run(
    base_url: str | None = None,
    api_key: str | None = None,
    color: str | None = None,
    use_png: bool = False,
    poll_interval: float = 2.0,
):
    """Start the daemon: health server + auto-play loop."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    base_url = base_url or os.environ.get("ASTRIAL_BASE_URL", "https://astrial.app")
    api_key = api_key or os.environ.get("XINGMOU_API_KEY")
    name = os.environ.get("XINGMOU_NAME", "xingmou")
    color = color or os.environ.get("XINGMOU_COLOR")
    use_png = use_png or os.environ.get("XINGMOU_USE_PNG", "").lower() in ("1", "true")
    poll_interval = float(os.environ.get("XINGMOU_POLL_INTERVAL", str(poll_interval)))

    # Health server (start early so Railway sees it alive)
    port = int(os.environ.get("PORT", "8080"))
    _start_health_server(port)

    # Auto-register or verify key
    client = AstrialClient(base_url=base_url, api_key=api_key)
    client = _ensure_registered(client, name)
    _sync_profile(client)

    agent_name = _get_status().get("name") or name
    log.info("Ready — entering auto-play loop")

    # Play loop (blocks)
    _play_loop(client, agent_name, color, use_png, poll_interval)
