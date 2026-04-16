"""Daemon mode for Railway/container deployment.

Runs a lightweight HTTP server for health checks + a background
auto-play loop that creates games and plays them continuously.
"""

import json
import logging
import os
import random
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

from .client import AstrialClient
from .player import play_game

log = logging.getLogger("xingmou")

# Daemon state (read by health endpoint)
_status = {
    "state": "starting",
    "games_played": 0,
    "games_won": 0,
    "current_game": None,
    "error": None,
}
_lock = threading.Lock()


def _update_status(**kwargs):
    with _lock:
        _status.update(kwargs)


def _get_status() -> dict:
    with _lock:
        return dict(_status)


# ── Health HTTP server ──

class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        elif self.path == "/":
            status = _get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress access logs


def _start_health_server(port: int):
    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info(f"Health server on :{port}")


# ── Auto-play loop ──

def _play_loop(client: AstrialClient, color: str, use_png: bool, interval: float):
    """Continuously create games and play them."""
    _update_status(state="ready")

    while True:
        try:
            # Create a game
            result = client.create_game()
            game_id = result["game_id"]
            log.info(f"Created game {game_id}")
            _update_status(state="waiting", current_game=game_id)

            # Join
            client.join_game(game_id, color)
            log.info(f"Joined as {color}")

            # Wait for opponent
            log.info("Waiting for opponent...")
            wait_start = time.time()
            timeout = float(os.environ.get("XINGMOU_WAIT_TIMEOUT", "600"))
            while True:
                state = client.state(game_id)
                if "game_over" in state:
                    break
                # Check if game has started (both players joined)
                if state.get("move_count", 0) > 0 or state.get("your_turn") is not None:
                    break
                if time.time() - wait_start > timeout:
                    log.warning(f"Timeout waiting for opponent, cancelling game {game_id}")
                    break
                time.sleep(3)

            # Play
            _update_status(state="playing")
            log.info(f"Playing game {game_id}")
            play_game(client, game_id, poll_interval=interval, use_png=use_png)

            # Update stats
            _update_status(state="idle", current_game=None)
            try:
                profile = client.profile()
                _update_status(
                    games_played=profile.get("games_played", 0),
                    games_won=profile.get("games_won", 0),
                )
            except Exception:
                pass

            # Brief pause before next game
            pause = float(os.environ.get("XINGMOU_GAME_PAUSE", "5"))
            time.sleep(pause)

        except KeyboardInterrupt:
            log.info("Shutting down")
            _update_status(state="stopped")
            break
        except Exception as e:
            log.error(f"Error in game loop: {e}")
            _update_status(state="error", error=str(e))
            time.sleep(10)


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

    base_url = base_url or os.environ.get("XINGMOU_BASE_URL", "https://astrial.app")
    api_key = api_key or os.environ.get("XINGMOU_API_KEY")
    color = color or os.environ.get("XINGMOU_COLOR", random.choice(["black", "white"]))
    use_png = use_png or os.environ.get("XINGMOU_USE_PNG", "").lower() in ("1", "true")
    poll_interval = float(os.environ.get("XINGMOU_POLL_INTERVAL", str(poll_interval)))

    if not api_key:
        log.error("XINGMOU_API_KEY is required")
        raise SystemExit(1)

    client = AstrialClient(base_url=base_url, api_key=api_key)

    # Verify key
    try:
        profile = client.profile()
        log.info(f"Agent: {profile['name']} (rating {profile['rating']})")
        _update_status(
            games_played=profile.get("games_played", 0),
            games_won=profile.get("games_won", 0),
        )
    except Exception as e:
        log.error(f"Failed to verify API key: {e}")
        raise SystemExit(1)

    # Health server
    port = int(os.environ.get("PORT", "8080"))
    _start_health_server(port)

    # Play loop (blocks)
    _play_loop(client, color, use_png, poll_interval)
