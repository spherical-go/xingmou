"""Game loop: poll state → think → act."""

import time
import sys

from .client import AstrialClient
from .brain import choose_move


def play_game(
    client: AstrialClient,
    game_id: str,
    poll_interval: float = 2.0,
    use_png: bool = False,
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

        # Get board image
        if use_png:
            board_image = client.board_png(game_id)
            fmt = "png"
        else:
            board_image = client.board_svg(game_id)
            fmt = "svg"

        # Ask LLM
        print("   🧠 Thinking...", end="", flush=True)
        move = choose_move(state, board_image, image_format=fmt)
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
