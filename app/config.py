import os
from pathlib import Path

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_USER_ID = int(os.environ["OWNER_USER_ID"])

CLAUDE_BACKEND = os.environ.get("CLAUDE_BACKEND", "agent_sdk").strip().lower()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
CLAUDE_CODE_OAUTH_TOKEN = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN", "").strip()

# In agent_sdk mode the API key must NOT exist in the process env:
# the SDK would silently prefer it, ending up billing pay-per-use.
# "auto" = agent_sdk billed to the API key while it works (e.g. promotional
# credits), then the OAuth subscription: ai.py passes the key explicitly.
if CLAUDE_BACKEND in ("agent_sdk", "auto"):
    os.environ.pop("ANTHROPIC_API_KEY", None)
    if CLAUDE_BACKEND == "agent_sdk":
        ANTHROPIC_API_KEY = ""

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "400"))

# Model for the agent_sdk backend (Claude Max via OAuth). Accepts Claude Code
# aliases ("sonnet", "opus", "haiku") or a full model id. Empty = CLI default.
# Note: CLAUDE_MODEL above applies to the "api" backend only.
AGENT_SDK_MODEL = os.environ.get("AGENT_SDK_MODEL", "sonnet").strip()

# Optional "💳 Crediti API" panel button ("auto" backend): credits granted (USD);
# the bot subtracts what its own replies cost (see credits.py).
API_CREDITS_TOTAL = float(os.environ.get("API_CREDITS_TOTAL", "0") or 0)
API_CREDITS_EXPIRES = os.environ.get("API_CREDITS_EXPIRES", "").strip()  # YYYY-MM-DD, optional

DATA_DIR = Path("/app/data")
STATE_FILE = DATA_DIR / "state.json"
LOG_DIR = DATA_DIR / "logs"
HEALTH_FILE = DATA_DIR / "health.txt"


def _check_data_dir_writable() -> None:
    """The host's data/ is bind-mounted over /app/data, so the Dockerfile's
    `chown bot:bot` does NOT apply at runtime — only the owner on the NAS
    counts. Docker creates a missing bind-mount source as root, so after a
    first `sudo compose up`, or after moving the project to a new path, data/
    can end up root-owned while the container runs as uid 1000. Every write
    then fails and the bot restart-loops on a bare PermissionError that says
    nothing about the cause. Check once, and say exactly how to fix it."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = DATA_DIR / ".write-probe"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise SystemExit(
            "\n" + "=" * 72 + "\n"
            f"{DATA_DIR} is not writable by the container user (uid 1000).\n"
            f"Detail: {e}\n\n"
            "Two possible causes — check the permissions on the host:\n\n"
            "1) The folder belongs to root. Docker creates it that way when it\n"
            "   is missing (first start with sudo, or a freshly moved project):\n"
            "       sudo chown -R 1000:1000 data\n\n"
            "2) The permissions LOOK right (owner 1000, mode 777) but writes are\n"
            "   still denied: a NAS ACL, which wins over POSIX permissions. You\n"
            "   spot it by the '+' in 'drwxrwxrwx+' and with:\n"
            "       getfattr -d -m - data | grep -i acl\n"
            "   chmod and chown don't touch it: recreate the folder copying the\n"
            "   files with 'cp -r' (NEVER 'cp -a', which carries the ACL over).\n"
            "   Full procedure in SETUP.md, section 13.\n\n"
            "Then: sudo docker compose up -d\n"
            + "=" * 72 + "\n"
        )


_check_data_dir_writable()

# Secondary dirs: data/ is writable by now, so these normally succeed. If one
# of them is individually root-owned (an old run before the chown), don't take
# the bot down for it — file logging degrades to stdout, which is what
# `docker logs` reads anyway.
for _subdir in (LOG_DIR, DATA_DIR / "whisper-models"):
    try:
        _subdir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

# ── Local voice transcription (faster-whisper) ──────────────────────────
# Runs on CPU inside the container, no external API / no per-use cost.
WHISPER_ENABLED = os.environ.get("WHISPER_ENABLED", "1").strip().lower() in (
    "1", "true", "yes", "on")
# Model size: tiny | base | small | medium | large-v3 (bigger = better & slower)
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "base").strip()
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu").strip()
# int8 is the fast / low-RAM choice for CPU; use float16 only on GPU
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8").strip()
# "" = auto-detect language; set e.g. "it" to force Italian for better accuracy
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "").strip()
# Voice notes longer than this many seconds are not transcribed (CPU cost on
# small hosts); the customer gets an ack and the note is handed off to the
# owner, who hears it directly in the business chat. 0 = no limit.
VOICE_MAX_SECONDS = int(os.environ.get("VOICE_MAX_SECONDS", "300"))
# Persisted on the mounted data volume so the model isn't re-downloaded on rebuild
WHISPER_CACHE_DIR = DATA_DIR / "whisper-models"

# Language of the owner's control panel and notices: "en" (default) or "it".
# Also the language of the bot's fixed lines to a customer until the AI has
# replied to them once (after that, those follow the customer's language).
UI_LANGUAGE = os.environ.get("UI_LANGUAGE", "en").strip().lower() or "en"

_DEFAULT_AWAY = {
    "en": "Hi! I'm not available right now. I'll get back to you as soon as I can.",
    "it": "Ciao! Al momento non sono disponibile, ti rispondo appena posso.",
}
DEFAULT_AWAY_MESSAGE = _DEFAULT_AWAY.get(UI_LANGUAGE, _DEFAULT_AWAY["en"])
DEFAULT_SYSTEM_PROMPT = (
    "You are the personal assistant of the owner of this Telegram account. "
    "Reply on their behalf in a friendly, concise tone, in the same language "
    "as the incoming message. Do not invent appointments or commitments: for "
    "concrete requests (pricing, jobs, meetings) say you'll forward the "
    "message as soon as the owner is available. Never declare you are an AI "
    "unless explicitly asked. Customize this prompt with /prompt from the owner."
)

# Minimum seconds between two replies to the same chat (anti-loop / anti-spam)
REPLY_COOLDOWN_SECONDS = 8

# Incoming texts longer than this are truncated before reaching the AI, to
# bound token cost when someone pastes a wall of text.
MAX_INPUT_CHARS = 3000

# Max history per conversation (turns kept in memory)
HISTORY_MAX_TURNS = 12

# Conversation history is persisted to data/history.json so it survives a
# restart/redeploy. Chats with no activity for this many days are pruned so the
# file (and memory) don't grow forever.
HISTORY_TTL_DAYS = int(os.environ.get("HISTORY_TTL_DAYS", "7"))

# ── message forwarding / human handoff ─────────────────────────────────
# Sentinel the AI can emit (anywhere in its reply) to signal that the
# conversation should be escalated to the owner. It is stripped out before
# the reply is sent to the customer.
FORWARD_MARKER = "[[FORWARD]]"

# Instructions appended to the system prompt so the forwarding behaviour
# works regardless of the custom prompt set with /prompt.
FORWARD_INSTRUCTIONS = (
    "\n\nIMPORTANT — escalation to the owner: if you cannot answer a request, "
    "if it needs the owner's personal decision (prices, quotes, appointments, "
    "payments, complaints, anything you are unsure about), or if the person "
    "explicitly asks to talk to the owner / a human, then add the exact token "
    f"{FORWARD_MARKER} at the very end of your reply. In that case reassure the "
    "person that you are forwarding their message to the owner who will get "
    "back to them. Never show or mention this token to the person; it is an "
    "internal signal."
)

# Minimum seconds between two forwards for the same chat (anti-spam for the
# owner). Explicit "I want to talk to a human" requests bypass this.
FORWARD_COOLDOWN_SECONDS = 300

# Appended to every prompt (like FORWARD_INSTRUCTIONS, regardless of the
# custom /prompt) so the assistant reads intent and register instead of
# taking every message literally.
CONVERSATION_INSTRUCTIONS = (
    "\n\nIMPORTANT — social intelligence: read the intent behind each message, "
    "not just the literal words. Recognize jokes, sarcasm, swearing, teasing "
    "and obviously fake or vulgar answers (e.g. a joke name): never process "
    "them earnestly as real information — reply with brief, good-natured wit "
    "and steer back to the point, without being preachy or offended. Match "
    "the person's register: playful with friends who banter, professional "
    "with genuine customers. Sound like a real human texting: short messages, "
    "varied wording, no formulaic openings, emojis only occasionally and "
    "never the same one twice in a row. Never ask for information you "
    "already have from the context or from earlier in the conversation.\n\n"
    "IMPORTANT — insults and crude language (common banter between friends): "
    "don't take offence, don't lecture, but don't play along with the word "
    "either. Never repeat the insult back, and never label it — calling a "
    "slur \"a compliment\" or \"a joke\" dignifies it and reads badly to "
    "anyone else who sees the chat. Acknowledge lightly and go straight to "
    "the point instead (\"Ahah ciao, tutto bene?\"). If the abuse is "
    "insistent or genuinely hostile rather than friendly teasing, drop the "
    "banter, stay polite and brief, and hand the conversation to the owner.\n\n"
    "IMPORTANT — never invent facts about the owner: not what they are doing "
    "right now, not what they own, not their opinions, habits or plans. State "
    "only facts that appear in the knowledge base or in this conversation. If "
    "asked something about the owner that you don't know (e.g. \"what is he "
    "up to?\"), keep it light and vague — you don't know exactly, they're "
    "busy — and offer to pass the message along. A wrong made-up detail is "
    "far worse than admitting you don't know.\n\n"
    "IMPORTANT — never invent the conversation itself. Do not claim you said "
    "something earlier, or that the person said or already knew something, "
    "unless it is actually written above. If they refer to something you "
    "cannot see, say plainly that you're not sure what they mean and ask — "
    "never bluff, and never contradict them about what was said."
)

# Appended LAST to every prompt, after the owner's /prompt, the knowledge base
# and the internal notes — several of those are written in Italian, and without
# a binding rule the model drifted into Italian with foreign customers.
LANG_MARKER_RE = r"\[\[LANG:([A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?)\]\]"
LANGUAGE_INSTRUCTIONS = (
    "\n\nIMPORTANT — language (overrides any other instruction about language, "
    "including the owner's prompt above): always reply in the language of the "
    "person's LATEST message. If they write in English, answer in English; if "
    "they switch language, switch with them. The language of these "
    "instructions, of the knowledge base, of the owner's prompt, of internal "
    "notes or of your own earlier replies is irrelevant. Only for messages "
    "with no clear language (just \"ok\", an emoji, a name) keep the language "
    "the conversation was already in.\n"
    "Start every reply with the tag [[LANG:xx]], where xx is the ISO 639-1 "
    "code of the language you are replying in (e.g. [[LANG:en]], [[LANG:it]]). "
    "It is an internal signal stripped before sending: never mention it."
)

# Appended to the system prompt with the sender's Telegram profile, so the
# AI knows who it's talking to and never asks for a name it already has.
SENDER_CONTEXT = (
    "\n\n--- SENDER CONTEXT ---\n"
    "You are talking with: {name}. Telegram already provides this name, so "
    "never ask who they are. If they claim a different, clearly implausible "
    "name, it is a joke: answer with wit, do not treat it as real information."
)

# ── channel promotion ──────────────────────────────────────────────────
# When set, the bot attaches an inline button with this (tracking) invite link
# to its first reply in each chat, under a short invite line. Empty = off.
PROMO_CHANNEL_URL = os.environ.get("PROMO_CHANNEL_URL", "").strip()
PROMO_BUTTON_TEXT = os.environ.get("PROMO_BUTTON_TEXT", "📢 Our channel").strip()
# What the channel is about, told to the AI so it can answer questions about
# the invite (e.g. "tech and Amazon deals"). Optional.
PROMO_CHANNEL_DESCRIPTION = os.environ.get("PROMO_CHANNEL_DESCRIPTION", "").strip()
# Minimum days between two promotions to the same chat (anti-spam).
PROMO_COOLDOWN_DAYS = int(os.environ.get("PROMO_COOLDOWN_DAYS", "30"))

PROMO_MARKER = "[[CHANNEL]]"
PROMO_INSTRUCTIONS = (
    "\n\n--- OWNER'S TELEGRAM CHANNEL ---\n"
    "The owner runs a Telegram channel"
    + (f" about {PROMO_CHANNEL_DESCRIPTION}" if PROMO_CHANNEL_DESCRIPTION else "")
    + ". Below this "
    "reply of yours the bot AUTOMATICALLY appends a short invite line and a "
    "button linking to the channel. So do NOT mention the channel, do not "
    "invite them to it and do not write its link: it is already handled, and "
    "saying it yourself makes the same invitation appear twice in a row. "
    "Just answer the person normally."
)
PROMO_ALREADY_NOTE = (
    "\n\n(You already suggested the owner's channel to this person "
    "recently — do not bring it up again unless they ask about it.)"
)


def _customer_texts(name: str, en: str, it: str) -> dict[str, str]:
    """A fixed line the bot sends to customers, in English (env NAME) and
    Italian (env NAME_IT). Which one goes out follows the customer's language:
    Italian chats get "it", every other language gets "en"."""
    return {
        "en": os.environ.get(name, en).strip(),
        "it": os.environ.get(f"{name}_IT", it).strip(),
    }


# Invite line the bot appends under the reply that carries the button — a
# button with nothing explaining it just confuses people.
PROMO_APPEND_TEXT = _customer_texts(
    "PROMO_APPEND_TEXT",
    "P.S. feel free to check out our Telegram channel too 👇",
    "P.S. se ti va, dai un'occhiata anche al nostro canale Telegram 👇",
)
# Written into the conversation history after the button is attached, so the
# AI knows it went out and can answer truthfully if asked about it.
# In English on purpose: it sits inside the conversation history, and an
# Italian note there pulled replies to foreign customers into Italian.
PROMO_HISTORY_NOTE = (
    "[System note: the bot automatically attached to this message an invite "
    "line and a «{button}» button opening the owner's Telegram channel. The "
    "person sees them; you did not write them.]"
)
# Text sent with the button when the owner uses /promo manually.
PROMO_MANUAL_TEXT = _customer_texts(
    "PROMO_MANUAL_TEXT",
    "📢 Here's the link to our Telegram channel, join from here 👇",
    "📢 Ti lascio il link al nostro canale Telegram, entra da qui 👇",
)

# ── human handoff / takeover ───────────────────────────────────────────
# After the owner steps into a conversation — either by typing directly in the
# business chat, or by replying to a forwarded notice in the bot DM — the bot
# stays silent in that chat for this many seconds so it doesn't talk over the
# human. Every new owner message refreshes the timer; /resume clears it early.
HANDOFF_PAUSE_SECONDS = int(os.environ.get("HANDOFF_PAUSE_SECONDS", "1800"))

# Fallback reply sent to the customer when a forward is triggered but the AI
# did not produce a reassuring message (e.g. away mode + explicit request).
FORWARD_ACK = _customer_texts(
    "FORWARD_ACK",
    "Got it, I'm passing your message on right away. You'll hear back soon. 🙏",
    "Perfetto, inoltro subito il tuo messaggio. Ti risponderà a breve. 🙏",
)
# Sent when the AI backend fails, so the customer still gets an answer.
AI_FAILURE_ACK = _customer_texts("AI_FAILURE_ACK", "One moment…", "Un attimo…")

# ── knowledge base / FAQ ───────────────────────────────────────────────
# Text the owner sets with /kb (business hours, address, price list, FAQ…).
# It is appended to the system prompt so the AI answers from these facts.
# Stays empty until set; appended only when non-empty.
KB_PREAMBLE = (
    "\n\n--- KNOWLEDGE BASE (verified facts about the business) ---\n"
    "Use the facts below to answer accurately. Quote them when relevant and "
    "never contradict or invent details beyond them. If a question is not "
    "covered here and needs the owner's input, escalate as instructed above.\n\n"
)
