"""CLI entry point for Xingmou."""

import os
import sys
import json
import time
from pathlib import Path

import click

from .client import AstrialClient
from .player import play_game
from .serve import run as serve_run

CONFIG_PATH = Path.home() / ".config" / "xingmou" / "config.json"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _get_client() -> AstrialClient:
    cfg = _load_config()
    base_url = os.environ.get("ASTRIAL_BASE_URL", cfg.get("base_url", "https://astrial.app"))
    api_key = os.environ.get("XINGMOU_API_KEY", cfg.get("api_key"))
    if not api_key:
        click.echo("❌ No API key. Run `xingmou register --name <name>` first.", err=True)
        sys.exit(1)
    return AstrialClient(base_url=base_url, api_key=api_key)


def _wait_for_start(
    client: AstrialClient,
    game_id: str,
    timeout: float = 600.0,
    poll: float = 2.0,
) -> bool:
    """Poll until the opponent has joined and the game has started.

    Returns True once moves can be played, False if `timeout` elapses first.
    """
    deadline = time.time() + timeout
    while True:
        state = client.state(game_id)
        if "game_over" in state:
            return True
        started = state.get("started")
        # Older servers have no `started` field; a move on the board is then
        # the only reliable evidence that the game is really under way.
        if started is None:
            started = state.get("move_count", 0) > 0
        if started:
            return True
        if time.time() >= deadline:
            return False
        click.echo(".", nl=False)
        time.sleep(poll)


@click.group()
def main():
    """星眸 Xingmou — LLM agent for Astrial (spherical Go)."""
    pass


@main.command()
@click.option("--name", required=True, help="Agent name (2-32 chars, alphanumeric/dash/underscore)")
@click.option("--base-url", default="https://astrial.app", help="Astrial server URL")
def register(name: str, base_url: str):
    """Register a new agent and save the API key."""
    client = AstrialClient(base_url=base_url)
    try:
        result = client.register(name)
    except Exception as e:
        click.echo(f"❌ Registration failed: {e}", err=True)
        sys.exit(1)

    api_key = result["api_key"]
    cfg = _load_config()
    cfg["api_key"] = api_key
    cfg["name"] = name
    cfg["base_url"] = base_url
    _save_config(cfg)

    click.echo(f"✅ Registered as {name}")
    click.echo(f"   API key saved to {CONFIG_PATH}")
    click.echo(f"   Key: {api_key[:8]}...{api_key[-4:]}")


@main.command()
def profile():
    """Show agent profile (rating, record)."""
    client = _get_client()
    p = client.profile()
    click.echo(f"🏷  {p['name']}")
    click.echo(f"   Rating: {p['rating']}")
    click.echo(f"   Games: {p['games_played']} played, {p['games_won']} won")


@main.command()
@click.option("--create", is_flag=True, help="Create a new game")
@click.option("--join", "game_id", default=None, help="Join an existing game by ID")
@click.option("--color", type=click.Choice(["black", "white"]), required=True, help="Play as black or white")
@click.option("--png", is_flag=True, help="Use PNG instead of SVG for board images")
@click.option("--poll", default=10.0, help="Polling interval in seconds")
def play(create: bool, game_id: str | None, color: str, png: bool, poll: float):
    """Play a game of Astrial."""
    if not create and not game_id:
        click.echo("❌ Specify --create or --join GAME_ID", err=True)
        sys.exit(1)

    client = _get_client()

    if create:
        result = client.create_game()
        game_id = result["game_id"]
        click.echo(f"🆕 Created game {game_id}")
        click.echo(f"   Viewer: {client.base_url}/play?game={game_id}")

    # Join
    join_result = client.join_game(game_id, color)
    click.echo(f"🪑 Joined as {join_result['role']}")

    # Wait for opponent if we created
    if create:
        timeout = float(os.environ.get("XINGMOU_WAIT_TIMEOUT", "600"))
        click.echo("⏳ Waiting for opponent...", nl=False)
        if not _wait_for_start(client, game_id, timeout=timeout):
            click.echo()
            click.echo(
                f"❌ No opponent joined within {timeout:.0f}s. "
                f"Game {game_id} is still open at {client.base_url}/play?game={game_id}",
                err=True,
            )
            sys.exit(1)
        click.echo(" ready!")

    play_game(client, game_id, poll_interval=poll, use_png=png)


@main.command()
@click.argument("game_id")
def watch(game_id: str):
    """Watch a game (print state updates)."""
    client = _get_client()
    import time
    last_move = -1
    while True:
        state = client.state(game_id)
        mc = state.get("move_count", 0)
        if mc != last_move:
            score = state.get("score", {})
            click.echo(
                f"Move {mc}: {state.get('current_player', '?')} to play | "
                f"B {score.get('black', 0):.3f} / W {score.get('white', 0):.3f}"
            )
            last_move = mc
        if "game_over" in state:
            go = state["game_over"]
            click.echo(f"🏁 Game over! Winner: {go['winner']}")
            break
        time.sleep(2)


@main.command()
@click.option("--color", type=click.Choice(["black", "white"]), default=None, help="Preferred color (random if omitted)")
@click.option("--png", is_flag=True, help="Use PNG instead of SVG")
@click.option("--poll", default=10.0, help="Polling interval in seconds")
def serve(color: str | None, png: bool, poll: float):
    """Run as a daemon: auto-play loop + health server.

    Designed for Railway/container deployment. All config via env vars:

    \b
    XINGMOU_API_KEY       Agent API key (required)
    ASTRIAL_BASE_URL      Astrial server (default: https://astrial.app)
    XINGMOU_MODEL         LLM model (default: openai/gpt-4o)
    XINGMOU_COLOR         Preferred color (default: random)
    OPENROUTER_API_KEY    OpenRouter key
    OPENAI_API_KEY        OpenAI key (alternative)
    PORT                  Health server port (default: 8080)
    """
    serve_run(color=color, use_png=png, poll_interval=poll)


@main.command()
def leaderboard():
    """Show agent leaderboard."""
    cfg = _load_config()
    base_url = os.environ.get("ASTRIAL_BASE_URL", cfg.get("base_url", "https://astrial.app"))
    client = AstrialClient(base_url=base_url)
    agents = client.leaderboard()
    if not agents:
        click.echo("No agents registered yet.")
        return
    click.echo(f"{'#':<4} {'Name':<20} {'Rating':<8} {'W/L'}")
    click.echo("-" * 44)
    for i, a in enumerate(agents, 1):
        gw = a["games_won"]
        gl = a["games_played"] - gw
        click.echo(f"{i:<4} {a['name']:<20} {a['rating']:<8} {gw}/{gl}")
