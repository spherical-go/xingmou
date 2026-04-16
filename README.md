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

1. **See** — fetches 9 board views (default + 4 continents + 4 oceans) as PNG, tiles them into 3 images
2. **Think** — sends the board images + game state to a multimodal LLM
3. **Act** — parses the model's move choice and plays it

```
┌─────────┐     GET /state         ┌──────────┐
│         │◄───────────────────────│          │
│ Astrial │     GET /board.png ×9  │ Xingmou  │
│ Server  │◄───────────────────────│          │
│         │     POST /play         │  ┌─────┐ │
│         │◄───────────────────────│  │ LLM │ │
└─────────┘                        │  └─────┘ │
                                   └──────────┘
```

The agent sends 3 PNG images per move:
- **Default view** — overall perspective with last move marked
- **Continent grid** — 2×2 tile of Dark North, Fertile South, East Wilds, West Gorge
- **Ocean grid** — 2×2 tile of Nether Sea, Whalewave Sea, Clearglow Sea, Drifting Mist Sea

This gives the LLM full spherical coverage of the board.

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter API key (supports GPT-4o, Claude, Gemini, etc.) |
| `OPENAI_API_KEY` | — | OpenAI API key (direct) |
| `XINGMOU_MODEL` | `openai/gpt-4o` | Model identifier |
| `ASTRIAL_BASE_URL` | `https://astrial.app` | Astrial server URL |
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

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect the `spherical-go/xingmou` repo
3. Set environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API key |
| `XINGMOU_NAME` | | Agent name (default: `xingmou`) |
| `XINGMOU_API_KEY` | | Agent API key (auto-registers if omitted) |
| `XINGMOU_MODEL` | | Model (default: `openai/gpt-4o`) |
| `XINGMOU_COLOR` | | `black` / `white` / omit for random |
| `XINGMOU_WAIT_TIMEOUT` | | Seconds to wait for opponent (default: 600) |
| `XINGMOU_GAME_PAUSE` | | Seconds between games (default: 15) |
| `XINGMOU_POLL_INTERVAL` | | Polling interval in seconds (default: 10) |

**Fully autonomous**: on first deploy, the agent auto-registers with `XINGMOU_NAME`,
then enters a loop — discovers open games to join, or creates new ones, plays via LLM,
and repeats. Resumes in-progress games automatically after restarts.

On first startup, the API key is logged. Save it as `XINGMOU_API_KEY` to survive restarts.

**Endpoints**: `GET /` → status JSON, `GET /health` → `{"ok": true}`.

## License

MIT
