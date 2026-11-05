# Full setup guide — Telegram Business Bot

Step-by-step guide to recreate from scratch a Telegram bot that replies to your DMs on your behalf (auto-reply or AI via Claude), running in a Docker container on a NAS or Linux server.

Index:
1. [Architecture](#architecture)
2. [Prerequisites](#prerequisites)
3. [Bot creation on BotFather](#1-bot-on-botfather)
4. [Claude OAuth token (for Claude Max/Pro subscribers)](#2-claude-oauth-token)
5. [Project configuration](#3-project-configuration)
6. [Build & deploy](#4-build--deploy)
7. [Connecting to your Telegram profile](#5-connecting-to-your-telegram-profile)
8. [Operator commands](#6-operator-commands)
9. [Troubleshooting](#troubleshooting)
10. [Gotchas — real errors encountered](#gotchas)

---

## Architecture

```
app/
  bot.py        entrypoint + handler wiring + heartbeat
  config.py     env vars + constants
  state.py      JSON persistence in data/state.json + schedule helper
  ai.py         AI backend: agent_sdk (Claude Max via OAuth) or api (anthropic SDK)
  handlers.py   BusinessConnectionHandler, business_message, owner commands
```

Persistent state in `data/state.json` (mode, prompt, schedule, stats). Heartbeat at `data/health.txt` for Docker HEALTHCHECK.

**Telegram updates used**: `business_connection`, `business_message`, `edited_business_message`, `deleted_business_messages`. Under the hood this is the system Telegram used to call "Business" (renamed to "Chat Automation" in May 2026 and made available without a Premium subscription).

---

## Prerequisites

- A Telegram account (Premium no longer required as of May 2026)
- A NAS or server with Docker + Docker Compose
- A local Mac/PC for the OAuth token generation (needs a browser)
- **One of**:
  - A Claude Pro/Max subscription (backend `agent_sdk`, no extra cost)
  - An Anthropic API key with credit loaded (backend `api`, pay-per-use)

---

## 1. Bot on BotFather

1. Open `@BotFather` on Telegram and run `/newbot`
2. Display name: anything you like (e.g. `Your Name · Assistant`)
3. Username: must end in `bot`, e.g. `@yourname_assistant_bot`
4. Copy the **API token** (format `123456:ABC…`) — this is `BOT_TOKEN`
5. From BotFather: `/mybots` → select the bot → **Bot Settings**
6. Enable **Chat Access Mode** (toggle ON)
   > *Allows the bot to access entire chats and read or send messages on behalf of the user who enabled it in Settings.*
   > 
   > In older versions this toggle was called "Business Mode". Leave all the other toggles OFF.

Find your **Telegram user ID** by messaging `@userinfobot` (`/start` → it replies with your numeric id). This is `OWNER_USER_ID`.

---

## 2. Claude OAuth token

**Only required for the `agent_sdk` backend** (Claude Max/Pro). If you're using an API key, skip to step 3.

On your **local Mac/PC** (NOT on the NAS — a browser is needed for the OAuth login):

```sh
npm install -g @anthropic-ai/claude-code
claude setup-token
```

The browser opens → log in with your Claude.ai (Pro/Max) account → a token like `sk-ant-oat01-…` (~108 characters) is printed.

Copy the token. It is valid for 1 year. This is `CLAUDE_CODE_OAUTH_TOKEN`.

> ⚠️ Treat it like a password. If it leaks, regenerate one with the same command — the old one is invalidated.

---

## 3. Project configuration

Clone/copy the `app/`, `Dockerfile`, `docker-compose.yaml` structure from the repository.

Create `.env` from `.env.example`:

```sh
cp .env.example .env
```

Fill in the fields:

```
BOT_TOKEN=<from BotFather>
OWNER_USER_ID=<from @userinfobot>

CLAUDE_BACKEND=agent_sdk          # or "api"

# agent_sdk mode (Claude Max)
CLAUDE_CODE_OAUTH_TOKEN=<from claude setup-token>
ANTHROPIC_API_KEY=                # MUST be empty in agent_sdk mode

# api mode (alternative)
# CLAUDE_BACKEND=api
# ANTHROPIC_API_KEY=sk-ant-...
# CLAUDE_CODE_OAUTH_TOKEN=

CLAUDE_MODEL=claude-haiku-4-5-20251001
CLAUDE_MAX_TOKENS=400
TZ=Europe/Rome
```

> ⚠️ **Never set both at once**. If `ANTHROPIC_API_KEY` is populated while in `agent_sdk` mode, the SDK silently prefers the API key over the OAuth token, ending up billing pay-per-use instead of using your Max subscription. The code in `config.py` strips `ANTHROPIC_API_KEY` from the process environment when backend = agent_sdk, but it's a footgun to avoid.

---

## 4. Build & deploy

The project is agnostic to the target: it runs identically on a NAS (UGREEN, Synology, QNAP) or on a VPS / Linux server. Only deploy paths and Docker installation procedure differ.

Throughout this guide `<DEPLOY_DIR>` is the directory where the project lives on the target:
- UGREEN NAS: typically `/volume1/docker/telegram-ai-secretary`
- Synology NAS: typically `/volume1/docker/telegram-ai-secretary`
- Debian/Ubuntu VPS: typically `/opt/telegram-ai-secretary` or `~/telegram-ai-secretary`

### 4a. VPS/server only: install Docker

If the target is a fresh Linux VPS / server without Docker, install it:

```sh
ssh <user>@<host>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and log back in to apply the group
exit
```

On commercial NAS appliances Docker is preinstalled by the vendor.

### 4b. Clone the project onto the target

Two options:

**Option A — via Git** (recommended if you have a repo):
```sh
ssh <user>@<host>
git clone https://github.com/<owner>/telegram-ai-secretary.git <DEPLOY_DIR>
cd <DEPLOY_DIR>
```

**Option B — via scp from local**:
```sh
# from your Mac/PC
scp -r /path/local/telegram-ai-secretary <user>@<host>:<DEPLOY_DIR>
```

**Later updates with Option B** (the target has no git, the clone lives on your Mac):
`scripts/deploy.sh` does the whole round — updates the local clone, copies `app/`,
`Dockerfile` and `docker-compose.yaml`, rebuilds and shows the logs. It checks that
`<DEPLOY_DIR>/app` exists on the target before copying anything, and lists the
candidates if it doesn't.

```sh
NAS=user@host DIR=/opt/telegram-ai-secretary ~/telegram-ai-secretary/scripts/deploy.sh
# plus a private overlay (extensions, personal.env — see README):
NAS=user@host DIR=/opt/telegram-ai-secretary OVERLAY=~/my-private-config \
  ~/telegram-ai-secretary/scripts/deploy.sh
```

### 4c. Create `.env` on the target

`.env` is NOT versioned (see `.gitignore`). Create it directly on the target:

```sh
cd <DEPLOY_DIR>
cp .env.example .env
nano .env       # fill all fields (see step 3)
```

### 4d. data/ folder permissions

The container runs as a non-root user (uid 1000). The `data/` folder must be writable by that user:

```sh
mkdir -p data
sudo chown -R 1000:1000 data
```

> On a VPS where your main user already has uid 1000 and is in the `docker` group, `sudo` is not needed. On a NAS where you SSH as a different user, it is.

### 4e. Build & start

```sh
docker compose up -d --build
docker compose logs -f telegram-ai-secretary
```

On systems where Docker requires sudo:
```sh
sudo docker compose up -d --build
sudo docker compose logs -f telegram-ai-secretary
```

You should see:
```
Starting polling…
Scheduler started
Application started
```

Without exceptions.

### 4f. Verify Claude authentication (agent_sdk backend only)

```sh
docker compose exec telegram-ai-secretary bash -lc 'claude --print "ping"'
```

It must return a natural-language response (e.g. "Pong!"). If you get `401 Invalid bearer token` → the token is invalid/expired, regenerate it with `claude setup-token`.

---

## 5. Connecting to your Telegram profile

On the Telegram app (phone):

1. **Settings → Chat Automation** (in older versions this may still be called "Telegram Business → Chatbots")
2. Add the bot by its username (`@yourname_assistant_bot`)
3. Grant the **Reply to messages** permission (essential — without it the bot cannot reply)
4. Pick the chat scope: starting with **New chats only** is recommended, to avoid automatically replying to all your existing contacts

As soon as the connection is active, the bot DMs you:
```
✅ Bot connected to your business account.
connection_id: <...>
can_reply: True
```

If you don't get the message, check the logs: the `BusinessConnectionHandler` must have logged `business connection ENABLED`.

---

## 6. Operator commands

All commands go via **direct DM to the bot** (only `OWNER_USER_ID` is authorized).

| Command | Effect |
|---|---|
| `/status` | Current state, connection, mode, stats |
| `/mode off\|away\|ai\|auto` | `off`=ignore, `away`=fixed reply only, `ai`=always AI, `auto`=AI during scheduled hours + away outside |
| `/away <text>` | Change the offline auto-reply |
| `/prompt <text>` | Change the AI system prompt |
| `/schedule HH:MM-HH:MM \| off` | Hours when `auto` mode uses AI |
| `/forward on\|off` | Forward important messages to you (default `on`) |
| `/reset_history` | Wipe in-memory conversation history |
| `/defaults` | Restore default away message and prompt |

When forwarding is on, the bot DMs you any message it can't answer (prices,
appointments, complaints, anything it's unsure about) or when the customer
explicitly asks to talk to you — see the "Message forwarding" section of the
README for details.

Example of an effective custom prompt:
```
/prompt You are John's personal assistant on Telegram. Reply briefly in the same language as the incoming message, max 2 sentences. Do not invent appointments or commitments — for concrete requests (pricing, jobs, meetings), say you'll forward the message to John as soon as he's available. Never declare you're an AI unless explicitly asked.
```

---

## Troubleshooting

### The bot receives messages but always replies with the away message

The AI is silently failing and falling back. Check logs:
```sh
sudo docker compose logs telegram-ai-secretary | grep -i "AI fail\|agent_sdk\|error"
```

Common causes:
- Invalid or expired OAuth token
- `claude-agent-sdk` version too old (see Gotchas)
- Container running as root (see Gotchas)
- Permissions on `data/state.json` (see Gotchas)

### `/status` shows `can_reply: False`

Go to Telegram → Settings → Chat Automation → select the bot → enable **Reply to messages**.

### `/status` shows `connection_id: None`

The bot is no longer linked. Re-add it under Settings → Chat Automation, or check whether you accidentally disabled **Chat Access Mode** in BotFather.

### Slow AI replies (>5s on the first message)

Normal — the Python SDK spawns `claude` as a Node subprocess, which takes 2-3s to initialize the first time. From the second message on it's fast. If you want lower latency at the cost of pay-per-use, switch to `CLAUDE_BACKEND=api`.

### "ANTHROPIC_API_KEY shadows OAuth token"

You have both populated in `.env`. Clear `ANTHROPIC_API_KEY` and restart.

---

## Gotchas

List of real errors encountered during the first deploy, in the order they appeared.

### 1. BotFather: the toggle is called "Chat Access Mode", no longer "Business Mode"

In May 2026 Telegram renamed the toggle and removed the Premium requirement for users connecting bots to their profile. The underlying API is unchanged (`business_connection`, `business_message`).

### 2. Telegram Business → Chat Automation

In the app the user menu was renamed from "Telegram Business → Chatbots" to "Chat Automation" and is now available without Premium.

### 3. Python SDK requires Node.js + claude-code CLI inside the container

Unlike the TypeScript SDK which bundles a native binary, the Python `claude-agent-sdk` spawns `claude` as a subprocess. The `Dockerfile` must install:
```dockerfile
RUN apt-get install -y nodejs npm \
    && npm install -g @anthropic-ai/claude-code
```

### 4. `claude-code` CLI refuses `--dangerously-skip-permissions` when running as root

Error: `--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons`.

**Env vars `IS_SANDBOX=1` / `CLAUDE_CODE_DOCKER_RUN=1` do NOT work** (ignored). Solution: non-root user in the Dockerfile.

```dockerfile
RUN useradd -m -u 1000 -s /bin/bash bot \
    && mkdir -p /app/data /home/bot/.claude \
    && chown -R bot:bot /app /home/bot
USER bot
ENV HOME=/home/bot
```

UID 1000 because it typically matches the main user on UGREEN/Synology NAS appliances, simplifying mounted-volume permissions.

### 5. data/ permissions after switching to non-root

If `data/state.json` was created before the switch (when the container ran as root), the new uid 1000 user cannot read it. Error: `PermissionError: [Errno 13] Permission denied: '/app/data/state.json'`.

One-time fix on the host:
```sh
sudo chown -R 1000:1000 <DEPLOY_DIR>/data
```

### 6. claude-agent-sdk 0.1.x does not handle new message types

Version 0.1.6 raises `MessageParseError: Unknown message type: rate_limit_event` because the Anthropic backend started emitting new event types not anticipated by old SDK releases. Pin at least 0.2.83:

```
claude-agent-sdk==0.2.83
```

### 7. ANTHROPIC_API_KEY silently shadows the OAuth token

If both are set, the SDK prefers the API key without warning, ending up billing pay-per-use. The code in `config.py` strips `ANTHROPIC_API_KEY` from the process environment when `CLAUDE_BACKEND=agent_sdk`.

### 8. SDK swallows subprocess stderr

When the `claude` subprocess fails, the Python SDK raises a generic `Command failed with exit code 1 / Error output: Check stderr output for details` but the actual stderr does not propagate automatically. To debug, run the CLI manually in the container:
```sh
docker compose exec telegram-ai-secretary bash -lc 'claude --print "ping"'
```

### 9. Only OWNER_USER_ID should be allowed to use commands

Enforced in every handler via `_is_owner(update)`. If you need to allow a second user (e.g. a partner), add a check like `update.effective_user.id in ALLOWED_USERS`.

### 10. Anti-loop cooldown

If you accidentally connect two AI bots to each other or reply to another bot, infinite loops are possible. `handlers.py` enforces `REPLY_COOLDOWN_SECONDS = 8` minimum between two replies to the same chat. Raise it if needed.

### 11. Messages sent by the owner themselves

The bot also receives messages YOU send from your own DMs. Filtered with:
```python
if msg.from_user.id == state["owner_user_id"]:
    return
```

### 12. Terminal-friendly debugging when web Docker UI mangles input

Some NAS web Docker terminals mangle long pastes (line wrapping turns into real newlines, breaking commands). When that happens, SSH directly into the host and `docker exec` from there — much cleaner.

### 13. Crash loop on `/app/data` with permissions that look fine (UGREEN UGOS)

Symptom: the container restart-loops, the startup check reports `/app/data non è
scrivibile`, and yet `ls -lan data` shows owner `1000` and mode `777`. Writing to
the folder over SSH works; writing to it from a container as uid 1000 does not,
while uid 0 does (root has `CAP_DAC_OVERRIDE` and skips the check entirely).

Cause: **UGOS applies its own ACL** to folders it manages, stored in an extended
attribute and shown by the `+` in `drwxrwxrwx+`. It takes precedence over the
POSIX bits, so `chmod`/`chown` cannot fix it. Confirm with:

```sh
getfattr -d -m - data | grep ugacl      # system.ugacl_self=0s... → this is it
```

A folder created over SSH with `mkdir` on the same volume has no such attribute
and works. So the fix is to rebuild the folder, copying the contents **without**
the extended attributes — plain `cp -r`, never `cp -a`, which would carry the
ACL straight over:

```sh
cd <DEPLOY_DIR>
sudo /usr/bin/docker compose down
sudo mkdir data_nuova && sudo cp -r data/. data_nuova/
sudo chown -R 1000:1000 data_nuova
sudo mv data data_vecchia_ugacl && sudo mv data_nuova data
sudo /usr/bin/docker compose up -d
```

Check it took with the same probe the bot runs at startup:

```sh
sudo /usr/bin/docker run --rm -u 1000:1000 \
  -v <DEPLOY_DIR>/data:/d \
  telegram-ai-secretary:latest sh -c "touch /d/.probe && rm /d/.probe && echo OK"
```

Prevention: create and move `data/` **over SSH**, not through the UGOS file
manager — that is what stamps the ACL on it.

---

## Backup & maintenance

### State backup

The state file is `data/state.json`. Suggested daily cron:

```sh
# /etc/cron.daily/backup-telegram-bot   (or personal crontab)
#!/bin/sh
SRC=<DEPLOY_DIR>/data/state.json
DEST=<BACKUP_DIR>
mkdir -p "$DEST"
cp "$SRC" "$DEST/state-$(date +%F).json"
find "$DEST" -name 'state-*.json' -mtime +30 -delete
```

On UGREEN/Synology NAS, put `<BACKUP_DIR>` on a different volume from the project (e.g. `/volume2/backup/...`) to survive a single-disk failure. On a VPS, consider periodic upload to external storage (S3, Backblaze B2, rsync to another machine).

### OAuth token rotation

The token lasts 1 year. To rotate:
```sh
claude setup-token   # on your local Mac/PC
```
Update `CLAUDE_CODE_OAUTH_TOKEN` in `.env` on the target, then:
```sh
sudo docker compose restart telegram-ai-secretary
```

### Dependency upgrades

Every 3-6 months it's worth bumping:
- `python-telegram-bot` (may introduce new business handlers/features)
- `claude-agent-sdk` (new backend message types, fixes)

Edit `app/requirements.txt`, then:
```sh
sudo docker compose build --no-cache
sudo docker compose up -d
```

### Autostart on a VPS (systemd)

On NAS appliances, autostart is handled by the vendor's Docker UI (`restart: unless-stopped` in `docker-compose.yaml` is enough). On a Linux VPS, if you want a dedicated systemd unit for finer control:

```ini
# /etc/systemd/system/telegram-ai-secretary.service
[Unit]
Description=Telegram Business Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=<DEPLOY_DIR>
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-ai-secretary
```

Otherwise, `restart: unless-stopped` in compose is already sufficient in most cases.

### Reverse proxy / public exposure

**Not needed.** The bot only makes **outbound** connections to `api.telegram.org` (long polling) and `api.anthropic.com`. No ports to open, no reverse proxy, no SSL certificate. Behind NAT/firewall is fine.

If in the future you wanted to switch to webhooks instead of polling (more efficient but requires a domain + HTTPS), then port 443 exposure with a reverse proxy would be needed.

### Healthcheck

Defined in the Dockerfile and `docker-compose.yaml`. The `heartbeat` job writes `data/health.txt` every 60s. If the file is not updated for 5 minutes, Docker marks the container as `unhealthy`.

```sh
sudo docker inspect --format='{{.State.Health.Status}}' telegram-ai-secretary
```

---

## Notes on limits

- **Max-subscription quota in agent_sdk mode**: the subscription has a 5-hour-window rate limit. Under heavy load this can exhaust, causing replies to fail and fall back to the away message until the next window.
- **Billing change June 15, 2026** (announced by Anthropic): Agent SDK usage on subscription plans will draw from a dedicated monthly credit, separate from interactive Max usage.
- **Anthropic ToS**: OAuth-based use of the subscription is permitted for personal use. Reselling/redistributing access to third parties is not.
- **Telegram rate limit**: the bot cannot send more than ~30 messages/second to the same chat. Irrelevant for normal conversational use.

---

## License

[PolyForm Noncommercial 1.0.0](./LICENSE) — free for any noncommercial purpose (personal, educational, research, hobby). Commercial use is not permitted.
