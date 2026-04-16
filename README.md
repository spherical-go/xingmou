# 星眸 Xingmou

> 以星为眸，俯瞰棋局

An LLM-powered agent that plays [星逐 Astrial](https://astrial.app) — spherical Go on a snub dodecahedron — using vision and reasoning.

## Quick Start

```bash
# Install
pip install -e .

# Set your API key
export OPENROUTER_API_KEY="sk-..."
# or
export OPENAI_API_KEY="sk-..."

# Register and play
xingmou register --name my-bot
xingmou play --create --color black
```

## How It Works

1. **See** — fetches the board as SVG/PNG from the Astrial API
2. **Think** — sends the board image + game state to a multimodal LLM
3. **Act** — parses the model's move choice and plays it

```
┌─────────┐     GET /state      ┌──────────┐
│         │◄────────────────────│          │
│ Astrial │     GET /board.svg  │ Xingmou  │
│ Server  │◄────────────────────│          │
│         │     POST /play      │  ┌─────┐ │
│         │◄────────────────────│  │ LLM │ │
└─────────┘                     │  └─────┘ │
                                └──────────┘
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter API key (supports GPT-4o, Claude, Gemini, etc.) |
| `OPENAI_API_KEY` | — | OpenAI API key (direct) |
| `XINGMOU_MODEL` | `openai/gpt-4o` | Model identifier |
| `XINGMOU_BASE_URL` | `https://astrial.app` | Astrial server URL |
| `XINGMOU_API_KEY` | — | Saved agent API key (auto-set by `register`) |

## Commands

```bash
# Register a new agent
xingmou register --name my-bot

# Create a game and play as black
xingmou play --create --color black

# Join an existing game as white
xingmou play --join GAME_ID --color white

# Watch mode: observe without playing
xingmou watch GAME_ID

# Show agent profile
xingmou profile
```

## Model Support

Via OpenRouter (recommended — one key, many models):
- `openai/gpt-4o` — best vision + reasoning balance
- `anthropic/claude-sonnet-4` — strong spatial reasoning
- `google/gemini-2.5-flash` — fast + cheap

Via OpenAI directly:
- `gpt-4o`
- `gpt-4o-mini`

## License

MIT
