"""Game loop: poll state → think → act."""

import io
import time
import sys

from PIL import Image, ImageDraw, ImageFont

from .client import AstrialClient
from .brain import choose_move

CONTINENTS = [
    ("dark-north", "Dark North"),
    ("fertile-south", "Fertile South"),
    ("east-wilds", "East Wilds"),
    ("west-gorge", "West Gorge"),
]
OCEANS = [
    ("nether-sea", "Nether Sea"),
    ("whalewave-sea", "Whalewave Sea"),
    ("clearglow-sea", "Clearglow Sea"),
    ("drifting-mist-sea", "Drifting Mist Sea"),
]

LABEL_H = 32  # height of the label bar above each tile


def _tile_2x2(images: list[bytes], labels: list[str]) -> bytes:
    """Combine 4 PNG images into a labeled 2×2 grid."""
    pils = [Image.open(io.BytesIO(b)) for b in images]
    w, h = pils[0].size
    cell_h = LABEL_H + h
    grid = Image.new("RGB", (w * 2, cell_h * 2), (0, 0, 0))
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    except (OSError, IOError):
        font = ImageFont.load_default()
    for i, (img, label) in enumerate(zip(pils, labels)):
        x = (i % 2) * w
        y = (i // 2) * cell_h
        # Draw label
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((x + (w - tw) // 2), y + 4), label, fill=(255, 255, 255), font=font)
        # Paste image below label
        grid.paste(img, (x, y + LABEL_H))
    buf = io.BytesIO()
    grid.save(buf, format="PNG")
    return buf.getvalue()


def _fetch_views(client: AstrialClient, game_id: str) -> list[bytes]:
    """Fetch default + labeled continent grid + labeled ocean grid = 3 PNGs."""
    default = client.board_png(game_id)
    c_imgs = [client.board_png(game_id, view=slug) for slug, _ in CONTINENTS]
    o_imgs = [client.board_png(game_id, view=slug) for slug, _ in OCEANS]
    c_labels = [name for _, name in CONTINENTS]
    o_labels = [name for _, name in OCEANS]
    return [default, _tile_2x2(c_imgs, c_labels), _tile_2x2(o_imgs, o_labels)]


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
