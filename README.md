# telegram-ai-secretary

A Telegram bot that connects to your personal account (via **Settings → Chat Automation**) and replies to your DMs on your behalf: either with an AI assistant powered by Claude (via Claude Max subscription or pay-per-use API key) or with a fixed away message.

**Voice messages** are supported too: they are transcribed locally on-device with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CPU, no external API, no per-use cost) and then handled like any text message. Tune it via the `WHISPER_*` variables in `.env` (set `WHISPER_ENABLED=0` to ignore voice notes).

> 📘 **Full setup guide**: see [`SETUP.md`](./SETUP.md) — covers BotFather, Claude OAuth token generation, NAS or VPS deployment, troubleshooting, and all the gotchas encountered during the first deploy.

## Features

- 🤖 **AI auto-reply** powered by Claude — via your **Claude Max** subscription (OAuth, no extra cost) or a pay-per-use **API key**.
- 🕹️ **Four modes** — `off` (ignore), `away` (fixed message), `ai` (always AI), `auto` (AI during scheduled hours, away outside).
- ⏰ **Schedule** — define the hours when `auto` mode uses the AI (windows crossing midnight supported).
- 🎙️ **Voice notes** — transcribed locally with faster-whisper and answered like text. Forced-language option for better accuracy.
- 📎 **Photos & documents** — the bot can't read them, but instead of ignoring them it acknowledges the customer and hands the attachment off to you.
- ⌨️ **Typing indicator** — shows “typing…” to the customer while the AI composes its reply, so the wait feels natural.
- 📨 **Human handoff** — escalates to you when the AI can't answer or the customer explicitly asks for a person (works in `away` mode too).
- ↩️ **Two-way handoff** — reply to a forwarded notice in the bot's DM and your message reaches the customer through the business connection.
- ⏸️ **Auto-pause on takeover** — the moment you step into a chat (reply or type directly), the bot stays silent there so it never talks over you.
- 🧠 **Per-conversation memory** — short rolling history per chat for coherent multi-turn replies; system-prompt caching to cut cost/latency.
- 🗣️ **Social smarts** — the AI knows the sender's Telegram name/username (never asks who they are), reads jokes/sarcasm/fake answers instead of taking them literally, and matches the register of the conversation.
- 📚 **Knowledge base / FAQ** — set business facts (hours, address, price list, FAQ) with `/kb`; they're injected into the AI's context so answers stay accurate instead of invented.
- 📢 **Channel promo** (optional) — the bot attaches an inline button with your channel's tracking invite link (`PROMO_CHANNEL_URL`) to its first reply in every chat, under a one-line invite in the customer's language; repeated at most once per chat every `PROMO_COOLDOWN_DAYS`.
- 🛡️ **Anti-spam** — per-chat reply cooldown and per-chat forward cooldown to avoid loops and notification floods.
- 📊 **Stats & health** — running counters (`/status`) and a heartbeat file for Docker `HEALTHCHECK`.
- 🐳 **Self-hosted** — single Docker container, JSON state on a mounted volume, no external database.

## Quick setup

1. `@BotFather` → `/newbot` → copy the `BOT_TOKEN`
2. `/mybots` → select bot → **Bot Settings** → **Chat Access Mode** → **ON**
   *(previously named "Business Mode")*
3. Find your user id with `@userinfobot`
4. (Optional) Generate a Claude OAuth token on your local machine:
   ```sh
   npm install -g @anthropic-ai/claude-code
   claude setup-token
   ```
5. Configure:
   ```sh
   cp .env.example .env
   # fill BOT_TOKEN, OWNER_USER_ID, CLAUDE_CODE_OAUTH_TOKEN (or ANTHROPIC_API_KEY)
   ```
6. Deploy:
   ```sh
   mkdir -p data && sudo chown -R 1000:1000 data
   docker compose up -d --build
   ```
7. On the Telegram app → **Settings → Chat Automation** → add the bot, grant **Reply to messages** permission.

## Owner control panel (DM the bot directly)

Send `/menu` (or `/start`) and the bot replies with an **inline control panel in
Italian** — every setting is a button, no commands to memorise:

| Button | Effect |
|---|---|
| 🤖 AI · ⏰ Automatico · 💤 Assenza · 🔴 Spento | Switch mode; the active one is ticked |
| 📊 Statistiche | Counters, paused chats, connection health |
| 📨 Inoltro: ON/OFF | Toggle forwarding of important messages |
| ✍️ Messaggio assenza · 🧠 Personalità AI | Edit the text: press, then just type the new value |
| 📚 Info attività | View / edit / clear the knowledge base |
| 🕐 Orari AI | Set the `auto`-mode window, or make the AI always-on |
| ▶️ Riattiva ovunque · 🗑 Cancella memoria | Lift every pause; wipe conversation memory (with confirmation) |
| 📢 Invia invito al canale · ♻️ Ripristina default | Send the channel invite to a chat; restore defaults (with confirmation) |

Replying to a “📨 Messaggio da inoltrare” notice still relays your text straight
to that customer.

<details>
<summary>Slash commands (still available as shortcuts)</summary>


| Command | Effect |
|---|---|
| `/status` | Current state, connection, mode, stats |
| `/mode off\|away\|ai\|auto` | `off`=ignore, `away`=fixed reply only, `ai`=always AI, `auto`=AI during scheduled hours + away outside |
| `/away <text>` | Change the offline auto-reply |
| `/prompt <text>` | Change the AI system prompt |
| `/kb <text> \| clear` | Set/clear the knowledge base the AI answers from (`/faq` is an alias) |
| `/schedule HH:MM-HH:MM \| off` | Hours when `auto` mode uses AI |
| `/forward on\|off` | Forward important messages to you (default `on`) |
| `/pause <chat_id>` | Manually silence the bot on one chat (same timer as a takeover) |
| `/promo <chat_id>` | Send the channel invite (text + button) to a chat — also works as a reply to a forwarded notice |
| `/resume [chat_id]` | Un-pause the bot after a takeover or `/pause` (all chats, or one) |
| `/reset_history [chat_id]` | Wipe conversation memory (all chats, or one) |
| `/defaults` | Restore default away message and prompt |

</details>

## Message forwarding / human handoff

When `forward` is on (default), the bot escalates a conversation to you (a DM
to `OWNER_USER_ID`) in two cases:

- **The AI can't handle it** — for prices, quotes, appointments, complaints or
  anything it's unsure about, the AI emits an internal `[[FORWARD]]` marker
  (stripped before the customer sees the reply) and reassures the customer that
  their message is being passed on.
- **The customer explicitly asks for you** — phrases like "voglio parlare con
  il titolare" or "talk to a human" are detected with a keyword matcher, so the
  handoff works even in `away` mode when the AI isn't involved.

The forward DM includes the sender's name/username, the `chat_id`, the original
message and the reply the bot gave. Explicit requests always notify you;
AI-detected escalations are rate-limited per chat (`FORWARD_COOLDOWN_SECONDS`,
default 5 min) to avoid spamming you.

### Two-way handoff & auto-pause

The handoff is bidirectional: **reply** to a "📨 Messaggio da inoltrare" notice
in the bot's DM and your text is relayed to that customer through the business
connection — no need to switch chats.

Whenever a human steps into a conversation — by replying to a notice, **or** by
typing directly in the business chat — the bot goes silent on that chat for
`HANDOFF_PAUSE_SECONDS` (default 30 min) so it never talks over you. Each new
message you send refreshes the timer; `/resume` (optionally with a `chat_id`)
lifts the pause immediately. The bot recognises its own outgoing messages, so
its automated replies don't count as a takeover.

## Configuration (`.env`)

All settings live in `.env` (see [`.env.example`](./.env.example) for the full annotated list). The most relevant:

| Variable | Default | Purpose |
|---|---|---|
| `BOT_TOKEN` | — | Bot token from `@BotFather` (required) |
| `OWNER_USER_ID` | — | Your Telegram user id — receives commands & forwards (required) |
| `CLAUDE_BACKEND` | `agent_sdk` | `agent_sdk` (Claude Max via OAuth) or `api` (anthropic SDK) |
| `CLAUDE_CODE_OAUTH_TOKEN` | — | OAuth token for `agent_sdk` mode (`claude setup-token`) |
| `ANTHROPIC_API_KEY` | — | API key for `api` mode (leave empty in `agent_sdk` mode) |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Model used by the `api` backend |
| `AGENT_SDK_MODEL` | `sonnet` | Model used by the `agent_sdk` backend (`sonnet`\|`opus`\|`haiku` or full id) |
| `PROMO_CHANNEL_URL` | _(empty)_ | Channel invite link attached as a button to the first reply in each chat (empty = off) |
| `PROMO_BUTTON_TEXT` | `📢 Canale Telegram` | Label of the promo button |
| `PROMO_CHANNEL_DESCRIPTION` | _(empty)_ | What the channel is about, so the AI can answer questions on it |
| `PROMO_APPEND_TEXT` / `PROMO_APPEND_TEXT_EN` | _(generic)_ | Invite line under the reply, for Italian chats / any other language |
| `PROMO_MANUAL_TEXT` | _(generic)_ | Text sent with the button by `/promo` |
| `PROMO_COOLDOWN_DAYS` | `30` | Minimum days between two promos to the same chat |
| `CLAUDE_MAX_TOKENS` | `400` | Max tokens per reply |
| `HANDOFF_PAUSE_SECONDS` | `1800` | How long the bot stays paused after a human takeover |
| `WHISPER_ENABLED` | `1` | Set `0` to ignore voice notes |
| `WHISPER_MODEL` | `base` | `tiny`\|`base`\|`small`\|`medium`\|`large-v3` |
| `VOICE_MAX_SECONDS` | `300` | Voice notes longer than this are handed off to you instead of transcribed (`0` = no limit) |
| `WHISPER_LANGUAGE` | _(auto)_ | Force a language (e.g. `it`) for better accuracy on short clips |
| `TZ` | `Europe/Rome` | Timezone (affects `/schedule`) |

A few behaviours are tuned by constants in `config.py`: `REPLY_COOLDOWN_SECONDS` (8s, anti-loop per chat), `FORWARD_COOLDOWN_SECONDS` (300s, forward anti-spam), `HISTORY_MAX_TURNS` (12, rolling memory per chat), `MAX_INPUT_CHARS` (3000, incoming text is truncated beyond this before reaching the AI).

## Architecture

```
app/
  bot.py         entrypoint + handler wiring + heartbeat
  config.py      env vars + tunable constants
  state.py       JSON persistence in data/state.json (mode, schedule, takeover &
                 forward maps, stats) + schedule/pause helpers
  ai.py          AI backend: agent_sdk (Claude Max via OAuth) or api (anthropic SDK)
  transcribe.py  local voice transcription with faster-whisper
  handlers.py    business connection/message handlers, owner commands, DM relay
  extensions/    optional per-deployment modules (see below)
```

Persistent state in `data/state.json` (mode, prompt, schedule, per-chat cooldowns, human-takeover timestamps, forwarded-notice → chat map, stats). The `stats` counter tracks `ai_replies`, `away_replies`, `skipped`, `forwarded`, `relayed` and `paused`. Heartbeat at `data/health.txt` for the Docker `HEALTHCHECK`.

**Telegram updates used**: `business_connection`, `business_message`, `edited_business_message`, `deleted_business_messages`. Under the hood this is what Telegram called "Business" (renamed "Chat Automation" in May 2026 and made available without a Premium subscription).

## Extensions & private overlay

Need a feature that only makes sense for your own deployment (a custom
`/start <payload>` flow, an extra command…)? Don't fork: drop a module into
`app/extensions/`. At startup `bot.py` imports every `app/extensions/*.py`
whose name doesn't start with `_` and calls its `register(app)`, **before** the
built-in handlers — so an extension can claim e.g. `/start mypayload` ahead of
the owner's `/start`. A failing extension is logged and skipped, never fatal.
See [`app/extensions/_example.py`](./app/extensions/_example.py).

To keep those modules — and your personal settings — out of this repo, keep
them in a private folder (or private repo) laid out like the deploy directory
and point `scripts/deploy.sh` at it with `OVERLAY=`:

```
my-private-config/
  app/extensions/my_feature.py        # copied into the image
  personal.env                        # non-secret personal settings
  docker-compose.override.yml         # e.g. adds personal.env to env_file
```

`docker compose` merges `docker-compose.override.yml` automatically, so a
two-line override is enough to load `personal.env` after `.env`:

```yaml
services:
  telegram-ai-secretary:
    env_file: [.env, personal.env]
```

Secrets (`BOT_TOKEN`, OAuth token, API keys) stay in `.env` on the target only.

## License

[PolyForm Noncommercial 1.0.0](./LICENSE) — free for any noncommercial purpose (personal, educational, research, hobby). Commercial use is not permitted.
