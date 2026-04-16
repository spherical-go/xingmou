"""LLM-based move selection with vision support."""

import base64
import os

from openai import OpenAI

SYSTEM_PROMPT = """\
You are 星眸 (Xingmou), an AI playing 星逐 (Astrial) — spherical Go on a \
snub dodecahedron with 302 points.

Rules:
- Black plays first. Players alternate turns.
- A group with no liberties is captured and removed.
- Suicide (placing a stone with no liberties that captures nothing) is illegal.
- Superko: no board position may repeat.
- Two consecutive passes end the game.
- Scoring: area-based on the spherical surface. White gets 0.025 komi.

Strategy tips:
- Control territory by surrounding empty regions.
- Keep your groups connected and with multiple liberties.
- Cut opponent groups apart when possible.
- Corners and edges don't exist on a sphere — think about continental regions instead.
- The board has 4 continents and 4 oceans; controlling a continent is strong.

You will receive:
1. A visual rendering of the current board (SVG/PNG image)
2. The game state as JSON (your role, board array, legal moves, score)

You must respond with EXACTLY one of:
- A point index number from the legal_moves list (e.g. `42`)
- The word `pass`

Think step by step about the position, then output your choice on the last line.
"""


def _make_client() -> tuple[OpenAI, str]:
    """Create an OpenAI-compatible client based on available env vars."""
    model = os.environ.get("XINGMOU_MODEL", "openai/gpt-4o")

    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url="https://openrouter.ai/api/v1",
        ), model

    if os.environ.get("OPENAI_API_KEY"):
        # Strip provider prefix for direct OpenAI usage
        if model.startswith("openai/"):
            model = model[len("openai/"):]
        return OpenAI(), model

    raise RuntimeError(
        "Set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable"
    )


def choose_move(
    state: dict,
    board_image: bytes | str,
    image_format: str = "svg",
) -> int | str:
    """Ask the LLM to choose a move.

    Args:
        state: Game state dict from the Astrial API.
        board_image: SVG string or PNG bytes of the board.
        image_format: "svg" or "png".

    Returns:
        Point index (int) or "pass".
    """
    client, model = _make_client()

    legal = state.get("legal_moves", [])
    role = state.get("role", "?")
    score = state.get("score", {})
    move_count = state.get("move_count", 0)

    state_text = (
        f"You are playing as {role}.\n"
        f"Move #{move_count + 1}. It is your turn.\n"
        f"Score — Black: {score.get('black', 0):.3f}, "
        f"White: {score.get('white', 0):.3f}, "
        f"Unclaimed: {score.get('unclaimed', 0):.3f}\n"
        f"Legal moves ({len(legal)} available): {legal}\n\n"
        f"Choose one point index from the legal_moves list, or say 'pass'."
    )

    # Build image content
    if image_format == "png" and isinstance(board_image, bytes):
        b64 = base64.b64encode(board_image).decode()
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        }
    elif image_format == "svg" and isinstance(board_image, str):
        # SVGs can be sent as data URI or as text; use data URI for compatibility
        b64 = base64.b64encode(board_image.encode()).decode()
        image_content = {
            "type": "image_url",
            "image_url": {"url": f"data:image/svg+xml;base64,{b64}"},
        }
    else:
        # Fallback: text-only mode
        image_content = None

    user_parts: list[dict] = []
    if image_content:
        user_parts.append(image_content)
    user_parts.append({"type": "text", "text": state_text})

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_parts},
        ],
        temperature=0.3,
        max_tokens=512,
    )

    return _parse_response(response.choices[0].message.content or "", legal)


def _parse_response(text: str, legal_moves: list[int]) -> int | str:
    """Extract a move from the LLM's response.

    Scans from the last line backward for a valid point index or 'pass'.
    """
    lines = text.strip().split("\n")
    for line in reversed(lines):
        line = line.strip().rstrip(".").strip()
        if line.lower() == "pass":
            return "pass"
        # Try to extract a number
        for token in reversed(line.split()):
            token = token.strip(".,;:()[]`*")
            try:
                n = int(token)
                if n in legal_moves:
                    return n
            except ValueError:
                continue
    # If no valid move found, return the first legal move as fallback
    if legal_moves:
        return legal_moves[0]
    return "pass"
