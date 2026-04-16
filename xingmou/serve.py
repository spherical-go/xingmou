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

def _find_active_game(client: AstrialClient, agent_name: str) -> dict | None:
    """Return the first active game (playing first, then waiting), or None."""
    try:
        games = client.my_games()
    except Exception:
        return None
    active = [g for g in games if g.get("status") in ("playing", "waiting")]
    if not active:
        return None
    # Prefer playing over waiting
    active.sort(key=lambda g: 0 if g.get("status") == "playing" else 1)
    return active[0]


def _wait_for_game_start(client: AstrialClient, game_id: str, timeout: float,
                         poll: float = 10.0) -> bool:
    """Block until game has started (both players joined and ready).
    Returns True if game is ready to play, False on timeout.
    Returns False early if a higher-priority (playing) game appears."""
    wait_start = time.time()
    check_count = 0
    while True:
        try:
            state = client.state(game_id)
        except Exception as e:
            log.warning("state poll error for %s: %s", game_id, e)
            time.sleep(poll)
            continue
        started = state.get("started")
        your_turn = state.get("your_turn")
        move_count = state.get("move_count", 0)
        log.info("waiting %s: started=%s your_turn=%s moves=%s",
                 game_id[:8], started, your_turn, move_count)
        if "game_over" in state:
            return True
        if started:
            return True
        # Fallback for older servers without started field
        if move_count > 0 or your_turn:
            return True
        if time.time() - wait_start > timeout:
            log.warning("timeout waiting for %s after %.0fs", game_id[:8], timeout)
            return False
        # Every 3 polls, check if a playing game needs attention
        check_count += 1
        if check_count % 3 == 0:
            try:
                games = client.my_games()
                if any(g.get("status") == "playing" and g["game_id"] != game_id
                       for g in games):
                    log.info("playing game detected, leaving wait for %s", game_id[:8])
                    return False
            except Exception:
                pass
        time.sleep(poll)


def _play_loop(client: AstrialClient, agent_name: str, prefer_color: str | None,
               use_png: bool, poll_interval: float):
    """Continuously find or create games and play them (one at a time)."""
    _update(state="ready")

    while True:
        try:
            game_id = None

            # 0. Resume an existing active game (re-join to restore Redis state)
            existing = _find_active_game(client, agent_name)
            if existing:
                game_id = existing["game_id"]
                bu = existing.get("black_user")
                wu = existing.get("white_user")
                role = "black" if bu == agent_name else "white" if wu == agent_name else None
                if not role:
                    log.warning("Cannot determine role in game %s, skipping", game_id)
                    time.sleep(30)
                    continue

                log.info("Resuming game %s as %s (status=%s)", game_id, role, existing.get("status"))
                try:
                    client.join_game(game_id, role)
                except Exception as e:
                    log.warning("Failed to re-join game %s: %s", game_id, e)
            else:
                # 1. Try to join an existing game
                found = _find_joinable_game(client, agent_name)
                if found:
                    game_id, role = found
                    log.info("Found joinable game %s — joining as %s", game_id, role)
                    try:
                        client.join_game(game_id, role)
                    except Exception as e:
                        log.warning("Failed to join %s: %s", game_id, e)
                        game_id = None

                # 2. No joinable game — create one
                if not game_id:
                    color = prefer_color or random.choice(["black", "white"])
                    result = client.create_game()
                    game_id = result["game_id"]
                    log.info("Created game %s", game_id)
                    client.join_game(game_id, color)

            _update(state="waiting", current_game=game_id)

            # 3. Wait for opponent / game to be ready
            timeout = float(os.environ.get("XINGMOU_WAIT_TIMEOUT", "600"))
            if not _wait_for_game_start(client, game_id, timeout, poll=poll_interval):
                log.warning("Timeout waiting for opponent in %s", game_id)
                _update(state="idle", current_game=None)
                time.sleep(20)
                continue

            # 4. Play the game
            _update(state="playing")
            play_game(client, game_id, poll_interval=poll_interval, use_png=use_png)

            # 5. Update stats
            _update(state="idle", current_game=None)
            _sync_profile(client)

            pause = float(os.environ.get("XINGMOU_GAME_PAUSE", "15"))
            time.sleep(pause)

        except KeyboardInterrupt:
            log.info("Shutting down")
            _update(state="stopped")
            break
        except Exception as e:
            log.error("Error in game loop: %s", e)
            _update(state="error", error=str(e))
            time.sleep(30)


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
    use_png: bool = True,
    poll_interval: float = 10.0,
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

    log.info("Entering auto-play loop (resumes active games automatically)")
    _play_loop(client, agent_name, color, use_png, poll_interval)
