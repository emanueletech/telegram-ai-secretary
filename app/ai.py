import json
import logging
import re
import time
from collections import defaultdict, deque

import credits
from config import (AGENT_SDK_MODEL, ANTHROPIC_API_KEY, CLAUDE_BACKEND,
                    CLAUDE_CODE_OAUTH_TOKEN, CLAUDE_MAX_TOKENS, CLAUDE_MODEL,
                    CONVERSATION_INSTRUCTIONS, DATA_DIR, FORWARD_INSTRUCTIONS,
                    FORWARD_MARKER, HISTORY_MAX_TURNS, HISTORY_TTL_DAYS,
                    LANG_MARKER_RE, LANGUAGE_INSTRUCTIONS, PROMO_MARKER)

log = logging.getLogger(__name__)

_MAXLEN = HISTORY_MAX_TURNS * 2
_HISTORY_FILE = DATA_DIR / "history.json"


def _new_deque() -> deque:
    return deque(maxlen=_MAXLEN)


# chat_id -> deque[{"role": "user"|"assistant", "content": str}]
_history: dict[int, deque] = defaultdict(_new_deque)
# chat_id -> last-activity unix ts (for TTL pruning)
_history_updated: dict[int, float] = {}
# chat_id -> ISO code of the language the AI last replied in ([[LANG:xx]]), so
# the bot's own fixed lines (channel invite, acks) match the conversation.
_language: dict[int, str] = {}
_LANG_RE = re.compile(LANG_MARKER_RE)

_anthropic_client = None  # lazy


# ─────────────────────────── persistence ───────────────────────────

def _prune_expired() -> None:
    cutoff = time.time() - HISTORY_TTL_DAYS * 86400
    stale = [cid for cid, ts in _history_updated.items() if ts < cutoff]
    for cid in stale:
        _history.pop(cid, None)
        _history_updated.pop(cid, None)
        _language.pop(cid, None)


def _save_history() -> None:
    """Atomically persist all live conversations to data/history.json."""
    _prune_expired()
    data = {
        str(cid): {"updated": _history_updated.get(cid, 0), "turns": list(dq),
                   "lang": _language.get(cid, "")}
        for cid, dq in _history.items() if dq
    }
    try:
        tmp = _HISTORY_FILE.with_suffix(".tmp")
        with tmp.open("w") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(_HISTORY_FILE)
    except OSError as e:
        log.warning("could not persist history: %s", e)


def _load_history() -> None:
    """Load persisted conversations at startup, dropping expired ones."""
    if not _HISTORY_FILE.exists():
        return
    try:
        with _HISTORY_FILE.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        log.warning("history file unreadable — starting with empty memory")
        return
    cutoff = time.time() - HISTORY_TTL_DAYS * 86400
    loaded = 0
    for cid_s, entry in data.items():
        updated = entry.get("updated", 0)
        if updated < cutoff:
            continue
        try:
            cid = int(cid_s)
        except (TypeError, ValueError):
            continue
        dq = _new_deque()
        dq.extend(entry.get("turns", []))
        if dq:
            _history[cid] = dq
            _history_updated[cid] = updated
            if entry.get("lang"):
                _language[cid] = entry["lang"]
            loaded += 1
    log.info("loaded persisted history for %d conversation(s)", loaded)


def _touch(chat_id: int) -> None:
    _history_updated[chat_id] = time.time()


def reset_history(chat_id: int | None = None) -> None:
    if chat_id is None:
        _history.clear()
        _history_updated.clear()
        _language.clear()
    else:
        _history.pop(chat_id, None)
        _history_updated.pop(chat_id, None)
        _language.pop(chat_id, None)
    _save_history()


def last_language(chat_id: int) -> str:
    """ISO code of the language the AI last replied in for this chat, "" when
    unknown (no AI reply yet, or the model left the tag out)."""
    return _language.get(chat_id, "")


_load_history()


def note_attachment(chat_id: int, note: str) -> None:
    """Record, on the last assistant turn, something the bot attached that the
    model didn't write itself (the channel invite button). Without this the AI
    has no idea the button went out, so a follow-up like "what's this?" gets a
    confabulated answer instead of the truth."""
    hist = _history.get(chat_id)          # .get: don't create an empty entry
    if not hist or hist[-1].get("role") != "assistant":
        return
    last = hist[-1]
    if note in last.get("content", ""):
        return
    last["content"] = last["content"].rstrip() + "\n" + note
    _save_history()


def _extract_markers(text: str, chat_id: int | None = None) -> tuple[str, bool, bool]:
    """Detect & strip the internal markers from an AI reply.

    Returns the customer-facing text (markers removed), whether the
    conversation should be forwarded to the owner, and whether the
    channel should be proposed (inline button attached by the handler).
    The [[LANG:xx]] tag is recorded per chat and always stripped.
    """
    m = _LANG_RE.search(text)
    if m:
        if chat_id is not None:
            _language[chat_id] = m.group(1).lower()
        text = _LANG_RE.sub("", text).strip()
    forward = FORWARD_MARKER in text
    promo = PROMO_MARKER in text
    if forward or promo:
        text = text.replace(FORWARD_MARKER, "").replace(PROMO_MARKER, "").strip()
    return text, forward, promo


# ─────────────────────────── backend: api (anthropic SDK) ───────────────────────────

def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY missing (backend=api)")
        _anthropic_client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


async def _reply_api(chat_id: int, user_text: str, system_prompt: str) -> tuple[str, bool, bool]:
    client = _get_anthropic()
    hist = _history[chat_id]
    hist.append({"role": "user", "content": user_text})

    # cache_control on the system prompt: cache hit from the second message onward
    system_blocks = [{
        "type": "text",
        "text": system_prompt + CONVERSATION_INSTRUCTIONS + FORWARD_INSTRUCTIONS
                + LANGUAGE_INSTRUCTIONS,
        "cache_control": {"type": "ephemeral"},
    }]

    try:
        resp = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=CLAUDE_MAX_TOKENS,
            system=system_blocks,
            messages=list(hist),
        )
    except Exception:
        hist.pop()
        raise

    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    reply, forward, promo = _extract_markers("".join(parts).strip() or "…", chat_id)
    hist.append({"role": "assistant", "content": reply})
    _touch(chat_id)
    _save_history()
    return reply, forward, promo


# ─────────────────────────── backend: agent_sdk (Claude Max via OAuth) ───────────────────────────

# "auto" backend: once the API key is rejected (credits used up or expired, key
# revoked) this file makes every later reply use the subscription, restarts
# included. Delete it to go back to the key.
_API_KEY_OFF_FILE = DATA_DIR / "api_key_off"
_switch_notice = False


class _ApiKeyRejected(RuntimeError):
    pass


def _use_api_key() -> bool:
    return CLAUDE_BACKEND == "auto" and bool(ANTHROPIC_API_KEY) and not _API_KEY_OFF_FILE.exists()


def api_key_off() -> bool:
    return _API_KEY_OFF_FILE.exists()


def take_switch_notice() -> bool:
    """True once, right after the switch to the subscription, so the owner hears about it."""
    global _switch_notice
    notice, _switch_notice = _switch_notice, False
    return notice


def _build_prompt_with_history(hist, user_text: str) -> str:
    # The SDK accepts a string prompt for one-shot query(); serialize history
    # in a simple format.
    lines = []
    for turn in hist:
        role = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{role}: {turn['content']}")
    lines.append(f"User: {user_text}")
    lines.append("Assistant:")
    return "\n\n".join(lines)


async def _reply_agent_sdk(chat_id: int, user_text: str, system_prompt: str) -> tuple[str, bool, bool]:
    use_key = _use_api_key()
    if not use_key and not CLAUDE_CODE_OAUTH_TOKEN:
        raise RuntimeError(
            "CLAUDE_CODE_OAUTH_TOKEN missing. Generate it on your local Mac/PC "
            "with 'claude setup-token' and copy the value into .env"
        )
    from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions,
                                  ResultMessage, TextBlock, query)

    hist = _history[chat_id]
    prompt = _build_prompt_with_history(hist, user_text)

    options = ClaudeAgentOptions(
        system_prompt=system_prompt + CONVERSATION_INSTRUCTIONS + FORWARD_INSTRUCTIONS
                + LANGUAGE_INSTRUCTIONS,
        allowed_tools=[],
        max_turns=1,
        model=AGENT_SDK_MODEL or None,  # None = Claude Code CLI default
        # the CLI prefers the key over the OAuth token when both are set
        env={"ANTHROPIC_API_KEY": ANTHROPIC_API_KEY} if use_key else {},
    )

    pieces: list[str] = []
    err_text = ""
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                if use_key and msg.error in ("authentication_failed", "billing_error"):
                    raise _ApiKeyRejected(msg.error)
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        pieces.append(block.text)
            elif isinstance(msg, ResultMessage) and use_key:
                credits.record(msg.total_cost_usd)
    except _ApiKeyRejected:
        raise
    except Exception as e:
        # Try to surface the subprocess stderr if available on the exception
        err_text = getattr(e, "stderr", "") or str(e)
        log.error("agent_sdk subprocess error: %s", err_text)
        # in case the CLI leaves msg.error unset, the error text is the only clue
        if use_key and re.search(r"credit balance|invalid api key", "".join(pieces) + err_text, re.I):
            raise _ApiKeyRejected(err_text) from e
        raise

    reply, forward, promo = _extract_markers("".join(pieces).strip() or "…", chat_id)
    hist.append({"role": "user", "content": user_text})
    hist.append({"role": "assistant", "content": reply})
    _touch(chat_id)
    _save_history()
    return reply, forward, promo


# ─────────────────────────── dispatcher ───────────────────────────

async def generate_reply(chat_id: int, user_text: str, system_prompt: str) -> tuple[str, bool, bool]:
    """Return (reply_text, should_forward_to_owner, propose_channel)."""
    global _switch_notice
    try:
        if CLAUDE_BACKEND in ("agent_sdk", "auto"):
            try:
                return await _reply_agent_sdk(chat_id, user_text, system_prompt)
            except _ApiKeyRejected as e:
                log.warning("API key rejected (%s): switching to the subscription for good", e)
                _API_KEY_OFF_FILE.write_text(time.strftime("%Y-%m-%d %H:%M:%S\n"))
                _switch_notice = True
                return await _reply_agent_sdk(chat_id, user_text, system_prompt)
        if CLAUDE_BACKEND == "api":
            return await _reply_api(chat_id, user_text, system_prompt)
        raise RuntimeError(f"Unknown CLAUDE_BACKEND: {CLAUDE_BACKEND!r}")
    except Exception as e:
        log.exception("backend %s failed: %s", CLAUDE_BACKEND, e)
        raise
