"""Game loop: poll state → think → act."""

import io
import time
import sys

from PIL import Image

from .client import AstrialClient
from .brain import choose_move

CONTINENTS = ["dark-north", "fertile-south", "east-wilds", "west-gorge"]
OCEANS = ["nether-sea", "whalewave-sea", "clearglow-sea", "drifting-mist-sea"]


def _tile_2x2(images: list[bytes]) -> bytes:
    """Combine 4 PNG images into a 2×2 grid."""
    pils = [Image.open(io.BytesIO(b)) for b in images]
    w, h = pils[0].size
    grid = Image.new("RGB", (w * 2, h * 2))
    for i, img in enumerate(pils):
        grid.paste(img, ((i % 2) * w, (i // 2) * h))
    buf = io.BytesIO()
    grid.save(buf, format="PNG")
    return buf.getvalue()


def _fetch_views(client: AstrialClient, game_id: str) -> list[bytes]:
    """Fetch default + continent grid + ocean grid = 3 PNGs."""
    default = client.board_png(game_id)
    continent_imgs = [client.board_png(game_id, view=v) for v in CONTINENTS]
    ocean_imgs = [client.board_png(game_id, view=v) for v in OCEANS]
    return [default, _tile_2x2(continent_imgs), _tile_2x2(ocean_imgs)]


def play_game(
    client: AstrialClient,
    game_id: str,
    poll_interval: float = 2.0,
    **_kwargs,
):
    """Main game loop. Polls state and plays moves until game over."""
    print(f"🎮 Game {game_id}")
    print(f"   Watching at: {client.base_url}/kifu/{game_id}")
    print()

    while True:
        state = client.state(game_id)

        # Game over?
        if "game_over" in state:
            go = state["game_over"]
            print(f"\n🏁 Game over! Winner: {go['winner']}")
            fs = go.get("final_score", {})
            print(f"   Final score — Black: {fs.get('black', 0):.3f}, White: {fs.get('white', 0):.3f}")
            break

        # Not our turn — wait
        if not state.get("your_turn", False):
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(poll_interval)
            continue

        role = state["role"]
        move_n = state["move_count"] + 1
        legal = state.get("legal_moves", [])
        score = state.get("score", {})

        print(f"\n⚫ Move #{move_n} ({role})")
        print(f"   Score: B {score.get('black', 0):.3f} / W {score.get('white', 0):.3f}")
        print(f"   Legal moves: {len(legal)}")

        # Get board images (default + continent grid + ocean grid)
        print("   📷 Fetching views...", end="", flush=True)
        board_images = _fetch_views(client, game_id)
        print(f" {len(board_images)} images")

        # Ask LLM
        print("   🧠 Thinking...", end="", flush=True)
        move = choose_move(state, board_images)
        print(f" → {move}")

        # Execute
        if move == "pass":
            client.pass_turn(game_id)
            print("   ⏭ Passed")
        else:
            result = client.play(game_id, move)
            pt_score = result.get("score", {})
            print(f"   ✅ Played point {move}")
            if pt_score:
                print(f"      Score: B {pt_score.get('black', 0):.3f} / W {pt_score.get('white', 0):.3f}")
