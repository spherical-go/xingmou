"""LLM-based move selection with vision support.

The prompt is sent to the first configured provider that answers; see
``providers.py`` for how several OpenAI-compatible endpoints are bound.
"""

import base64
import logging
import os

from openai import OpenAI

from .providers import Provider, resolve_providers

log = logging.getLogger(__name__)

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

Move priority (highest → lowest):
1. Life-and-death / urgent points (急所) — saving or killing groups
2. Pentagon centers — high-connectivity hubs, strategically dominant
3. Pentagon vertices — strong influence points on the spherical topology
4. Degree-4 points — solid positional moves
5. Degree-3 points — lower priority, weaker influence

Placement principles:
- Spread stones in a staggered, varied pattern — avoid clustering.
- Prevent the opponent from forming large connected territories.
- Prioritize cutting opponent groups apart over passive expansion.

You will receive:
1. Three board images:
   - Default view (overall perspective, last move marked)
   - Four continent views (2×2 grid: Dark North, Fertile South, East Wilds, West Gorge)
   - Four ocean views (2×2 grid: Nether Sea, Whalewave Sea, Clearglow Sea, Drifting Mist Sea)
2. The game state as JSON (your role, board array, legal moves, score)

You must respond with EXACTLY one of:
- A point index number from the legal_moves list (e.g. `42`)
- The word `pass`

Think step by step about the position, then output your choice on the last line.
"""

IMAGE_LABELS = [
    "Default view (last move marked with diamond)",
    "Four continent views (labeled in image)",
    "Four ocean views (labeled in image)",
]

DEFAULT_LLM_TIMEOUT = 120.0
DEFAULT_LLM_RETRIES = 1
DEFAULT_LLM_MAX_TOKENS = 512


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value >= 0 else default


def _max_tokens() -> int:
    return _env_int("XINGMOU_LLM_MAX_TOKENS", DEFAULT_LLM_MAX_TOKENS) or DEFAULT_LLM_MAX_TOKENS


def _state_text(state: dict) -> str:
    legal = state.get("legal_moves", [])
    role = state.get("role", "?")
    score = state.get("score", {})
    move_count = state.get("move_count", 0)
    return (
        f"You are playing as {role}.\n"
        f"Move #{move_count + 1}. It is your turn.\n"
        f"Score — Black: {score.get('black', 0):.3f}, "
        f"White: {score.get('white', 0):.3f}, "
        f"Unclaimed: {score.get('unclaimed', 0):.3f}\n"
        f"Legal moves ({len(legal)} available): {legal}\n\n"
        f"Choose one point index from the legal_moves list, or say 'pass'."
    )


def _user_parts(state: dict, board_images: list[bytes]) -> list[dict]:
    parts: list[dict] = []
    for i, img in enumerate(board_images):
        label = IMAGE_LABELS[i] if i < len(IMAGE_LABELS) else f"View {i}"
        parts.append({"type": "text", "text": label})
        b64 = base64.b64encode(img).decode()
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
    parts.append({"type": "text", "text": _state_text(state)})
    return parts


def _build_messages(state: dict, board_images: list[bytes]) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_parts(state, board_images)},
    ]


def _make_client(provider: Provider) -> OpenAI:
    return OpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
        timeout=_env_float("XINGMOU_LLM_TIMEOUT", DEFAULT_LLM_TIMEOUT),
        max_retries=_env_int("XINGMOU_LLM_RETRIES", DEFAULT_LLM_RETRIES),
    )


def _complete(provider: Provider, messages: list[dict]) -> str:
    """Run one chat completion on `provider` and return the message text."""
    client = _make_client(provider)
    response = client.chat.completions.create(
        model=provider.model,
        messages=messages,
        temperature=0.3,
        max_tokens=_max_tokens(),
        # TokenPlus replies in SSE unless `stream` is explicitly false.
        stream=False,
    )
    return response.choices[0].message.content or ""


def choose_move(
    state: dict,
    board_images: list[bytes],
) -> int | str:
    """Ask the LLM to choose a move, falling back across bound providers.

    Args:
        state: Game state dict from the Astrial API.
        board_images: List of PNG images (default, continent grid, ocean grid).

    Returns:
        Point index (int) or "pass".
    """
    legal = state.get("legal_moves", [])
    messages = _build_messages(state, board_images)
    providers = resolve_providers()

    last_error: Exception | None = None
    for provider in providers:
        try:
            text = _complete(provider, messages)
        except Exception as exc:  # network, auth, quota, model id, ...
            last_error = exc
            log.warning("LLM provider %s failed: %s", provider, exc)
            continue
        log.info("move chosen via %s", provider)
        return _parse_response(text, legal)

    raise RuntimeError(
        "所有 LLM provider 都调用失败（依次尝试了 "
        + ", ".join(str(p) for p in providers)
        + "）"
    ) from last_error


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
