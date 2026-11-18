# 星眸 Xingmou

> 以星为眸，俯瞰棋局

An LLM-powered agent that plays [星逐 Astrial](https://astrial.app) — spherical Go on a snub dodecahedron — using vision and reasoning.

## Quick Start

```bash
# Install
pip install -e .

# Bind one or more LLM providers (TokenPlus / OpenRouter / OpenAI)
export TOKENPLUS_API_KEY="sk-..."
export XINGMOU_MODEL="gpt-4o"          # model for the bound provider(s)
# or: export OPENROUTER_API_KEY="sk-or-..."
# or: export OPENAI_API_KEY="sk-..."

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
| `XINGMOU_PROVIDERS` | `tokenplus,openrouter,openai` | Providers to bind, tried in order |
| `TOKENPLUS_API_KEY` | — | TokenPlus key (`https://api.tokenplus.cn/v1`) |
| `OPENROUTER_API_KEY` | — | OpenRouter key |
| `OPENAI_API_KEY` | — | OpenAI key (direct) |
| `<NAME>_MODEL` | per provider | Model for provider `NAME` (e.g. `TOKENPLUS_MODEL`) |
| `<NAME>_BASE_URL` | per provider | Base URL for provider `NAME` (any OpenAI-compatible endpoint) |
| `XINGMOU_MODEL` | per provider | Model for providers without their own `<NAME>_MODEL` |
| `XINGMOU_LLM_TIMEOUT` | `120` | Seconds per LLM request |
| `XINGMOU_LLM_RETRIES` | `1` | Retries per provider before falling back |
| `XINGMOU_LLM_MAX_TOKENS` | `512` | Max completion tokens per move |
| `XINGMOU_RESIGN_MARGIN` | `0.05` | Trailing player resigns when the score gap reaches this area share (`0` disables) |
| `XINGMOU_RESIGN_STREAK` | `3` | ...and only after this many consecutive own turns behind |
| `XINGMOU_VIEW_MAX` | `900` | Longest side of each board view sent to the model (lower = faster, cheaper) |
| `ASTRIAL_BASE_URL` | `https://astrial.app` | Astrial server URL |
| `XINGMOU_API_KEY` | — | Saved agent API key (auto-set by `register`) |
| `XINGMOU_HTTP_TIMEOUT` | `30` | Per-request timeout in seconds for Astrial API calls |
| `XINGMOU_FONT` | auto-detect | TrueType font path for the board-view labels |

Komi (0.025 for White) is still provisional and has to be tuned through real
games. `XINGMOU_RESIGN_MARGIN` compares the live area share *before* komi, so
changing komi does not change when an agent resigns.

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

## LLM Providers

Providers are bound by environment variables and tried in order; a failed call
(transport, auth, quota, unknown model) falls through to the next one. Only
providers with a key set are used, so binding extra providers is always safe.

| Provider | Key | Base URL | Default model |
|----------|-----|----------|---------------|
| `tokenplus` | `TOKENPLUS_API_KEY` | `https://api.tokenplus.cn/v1` | `gpt-4o` |
| `openrouter` | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1` | `openai/gpt-4o` |
| `openai` | `OPENAI_API_KEY` | `https://api.openai.com/v1` | `gpt-4o` |

```bash
# TokenPlus primary, OpenRouter as fallback
export TOKENPLUS_API_KEY="sk-..."      # https://www.tokenplus.cn
export OPENROUTER_API_KEY="sk-or-..."
export XINGMOU_PROVIDERS="tokenplus,openrouter"
export TOKENPLUS_MODEL="gpt-4o"
export OPENROUTER_MODEL="openai/gpt-4o"
```

Any other OpenAI-compatible endpoint can be bound the same way:

```bash
export XINGMOU_PROVIDERS="myrelay"
export MYRELAY_API_KEY="..."
export MYRELAY_BASE_URL="https://relay.example.com/v1"
export MYRELAY_MODEL="gpt-4o"
```

Request bodies set `stream: false` explicitly because TokenPlus streams by
default, which the non-streaming response parser cannot read. Model identifiers
are per provider: TokenPlus/OpenAI take bare ids (`gpt-4o`), OpenRouter takes
slugs (`openai/gpt-4o`); `XINGMOU_MODEL` is normalised for the former.

`GET /` on the daemon lists the bound providers, and the daemon refuses to
start when no provider is configured.

List the vision models a TokenPlus key may call (useful before pinning
`TOKENPLUS_MODEL`):

```bash
curl -s -H "Authorization: Bearer $TOKENPLUS_API_KEY" \
  "https://api.tokenplus.cn/v1/models?input_modalities=image&limit=20" | head -c 2000
```

## Deploy on Railway

1. Create a new project on [Railway](https://railway.app)
2. Connect the `spherical-go/xingmou` repo
3. Set environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `TOKENPLUS_API_KEY` / `OPENROUTER_API_KEY` / `OPENAI_API_KEY` | ✅ | At least one provider key |
| `XINGMOU_PROVIDERS` | | Fallback order (default: `tokenplus,openrouter,openai`) |
| `XINGMOU_NAME` | | Agent name (default: `xingmou`) |
| `XINGMOU_API_KEY` | | Agent API key (auto-registers if omitted) |
| `XINGMOU_MODEL` / `<NAME>_MODEL` | | Model override (defaults per provider) |
| `XINGMOU_COLOR` | | `black` / `white` / omit for random |
| `XINGMOU_WAIT_TIMEOUT` | | Seconds to wait for opponent (default: 600) |
| `XINGMOU_GAME_PAUSE` | | Seconds between games (default: 15) |
| `XINGMOU_POLL_INTERVAL` | | Polling interval in seconds (default: 10) |

**Fully autonomous**: on first deploy, the agent auto-registers with `XINGMOU_NAME`,
then enters a loop — discovers open games to join, or creates new ones, plays via LLM,
and repeats. Resumes in-progress games automatically after restarts.

On first startup, the API key is logged. Save it as `XINGMOU_API_KEY` to survive restarts.

**Endpoints**: `GET /` → status JSON, `GET /health` → `{"ok": true}`.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite is offline: HTTP is stubbed, so no Astrial server or API key is needed.

## License

MIT
