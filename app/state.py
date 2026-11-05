import json
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

from config import (DEFAULT_AWAY_MESSAGE, DEFAULT_SYSTEM_PROMPT,
                    HANDOFF_PAUSE_SECONDS, STATE_FILE)

_lock = Lock()

DEFAULT_STATE = {
    "connection_id": None,
    "owner_user_id": None,        # business user id (who linked the bot)
    "can_reply": False,           # business_bot_rights.can_reply
    "mode": "auto",               # off | away | ai | auto
    "away_message": DEFAULT_AWAY_MESSAGE,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "knowledge": "",              # optional FAQ/knowledge base set with /kb
    "schedule": None,             # {"start": "09:00", "end": "19:00"} or None = always AI
    "forward_enabled": True,      # forward/escalate important messages to the owner
    "last_reply_at": {},          # chat_id -> unix ts
    "last_forward_at": {},        # chat_id -> unix ts (anti-spam for the owner)
    "last_promo_at": {},          # chat_id -> unix ts (channel promo cooldown)
    "human_takeover_at": {},      # chat_id -> unix ts (bot paused, human handling)
    "pending_forwards": {},       # owner-DM message_id (str) -> customer chat_id
    "stats": {"ai_replies": 0, "away_replies": 0, "skipped": 0,
              "forwarded": 0, "relayed": 0, "paused": 0},
}


def _load() -> dict:
    if not STATE_FILE.exists():
        return dict(DEFAULT_STATE)
    try:
        with STATE_FILE.open() as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return dict(DEFAULT_STATE)
    merged = dict(DEFAULT_STATE)
    merged.update(data)
    return merged


def _save(state: dict) -> None:
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    tmp.replace(STATE_FILE)


def load_state() -> dict:
    with _lock:
        return _load()


def update_state(**changes) -> dict:
    with _lock:
        state = _load()
        state.update(changes)
        _save(state)
        return state


def mark_reply(chat_id: int) -> None:
    with _lock:
        state = _load()
        state["last_reply_at"][str(chat_id)] = int(time.time())
        _save(state)


def mark_promo(chat_id: int) -> None:
    with _lock:
        state = _load()
        state.setdefault("last_promo_at", {})[str(chat_id)] = int(time.time())
        _save(state)


def mark_forward(chat_id: int) -> None:
    with _lock:
        state = _load()
        state["last_forward_at"][str(chat_id)] = int(time.time())
        _save(state)


def bump_stat(key: str) -> None:
    with _lock:
        state = _load()
        state["stats"][key] = state["stats"].get(key, 0) + 1
        _save(state)


# ---- human handoff / takeover ----

def mark_takeover(chat_id: int) -> None:
    """Record that a human just acted in this chat; pauses the bot there."""
    with _lock:
        state = _load()
        state.setdefault("human_takeover_at", {})[str(chat_id)] = int(time.time())
        _save(state)


def clear_takeover(chat_id: int | None = None) -> int:
    """Resume the bot on one chat (or all). Returns how many were cleared."""
    with _lock:
        state = _load()
        ht = state.setdefault("human_takeover_at", {})
        if chat_id is None:
            n = len(ht)
            state["human_takeover_at"] = {}
        else:
            n = 1 if ht.pop(str(chat_id), None) is not None else 0
        _save(state)
        return n


def is_paused(state: dict, chat_id: int) -> bool:
    ts = state.get("human_takeover_at", {}).get(str(chat_id), 0)
    return time.time() - ts < HANDOFF_PAUSE_SECONDS


def remember_forward(owner_msg_id: int, chat_id: int, keep: int = 500) -> None:
    """Map a forwarded-notice message_id (in the owner DM) to the customer chat,
    so a reply to that notice can be relayed back. Keeps the newest `keep`."""
    with _lock:
        state = _load()
        pf = state.setdefault("pending_forwards", {})
        pf[str(owner_msg_id)] = chat_id
        if len(pf) > keep:  # dict preserves insertion order — drop the oldest
            for k in list(pf)[: len(pf) - keep]:
                pf.pop(k, None)
        _save(state)


def lookup_forward(owner_msg_id: int) -> int | None:
    return load_state().get("pending_forwards", {}).get(str(owner_msg_id))


def in_schedule(state: dict, now: datetime | None = None) -> bool:
    sched = state.get("schedule")
    if not sched:
        return True
    now = now or datetime.now()
    cur = now.strftime("%H:%M")
    start, end = sched["start"], sched["end"]
    # window that crosses midnight (e.g. 22:00-07:00)
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end
