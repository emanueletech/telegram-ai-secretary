import asyncio
import html
import logging
import re
import time
from collections import deque

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import ai
import credits
import transcribe
from config import (AI_FAILURE_ACK, DEFAULT_AWAY_MESSAGE, FORWARD_ACK,
                    DEFAULT_SYSTEM_PROMPT, FORWARD_COOLDOWN_SECONDS,
                    HANDOFF_PAUSE_SECONDS, KB_PREAMBLE, MAX_INPUT_CHARS,
                    OWNER_USER_ID, PROMO_ALREADY_NOTE, PROMO_BUTTON_TEXT,
                    PROMO_APPEND_TEXT, PROMO_CHANNEL_URL,
                    PROMO_COOLDOWN_DAYS, PROMO_HISTORY_NOTE, PROMO_INSTRUCTIONS,
                    PROMO_MANUAL_TEXT, REPLY_COOLDOWN_SECONDS, SENDER_CONTEXT,
                    UI_LANGUAGE, VOICE_MAX_SECONDS, WHISPER_ENABLED)
from i18n import t
from state import (bump_stat, clear_takeover, in_schedule, is_paused,
                   load_state, lookup_forward, mark_forward, mark_promo,
                   mark_reply, mark_takeover, remember_forward, update_state)

log = logging.getLogger(__name__)

# Recently sent business message_ids. Telegram may echo the bot's own outgoing
# messages back as business_message updates (from_user == owner); without this
# the bot would mistake its own replies for a human takeover and pause itself.
_bot_sent_ids: deque[int] = deque(maxlen=200)


def _remember_bot_msg(mid: int) -> None:
    _bot_sent_ids.append(mid)

MODES = {"off", "away", "ai", "auto"}
TIME_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")

# Explicit "I want to talk to a real person / the owner" requests (IT + EN).
# This is a robust fallback that triggers a forward even in away mode, when
# the AI is not involved to emit its escalation marker.
HUMAN_RE = re.compile(
    r"(parlare\s+con\s+(te|lei|il\s+titolare|il\s+proprietario|il\s+responsabile|"
    r"qualcuno|una\s+persona|un\s+operatore|un\s+umano)|"
    r"(voglio|vorrei|posso)\s+parlare|"
    r"un\s+operatore|una\s+persona\s+(vera|reale)|essere\s+umano|"
    r"(contattare|sentire)\s+(il\s+titolare|il\s+proprietario|il\s+responsabile)|"
    r"(talk|speak|chat)\s+(to|with)\s+(you|(a|the)\s+"
    r"(human|real\s+person|person|manager|operator|owner))|"
    r"real\s+person|human\s+being|human\s+agent)",
    re.IGNORECASE,
)


def _wants_human(text: str) -> bool:
    return bool(text) and HUMAN_RE.search(text) is not None


# Telegram rejects messages longer than 4096 chars with BadRequest("Message is
# too long"). Leave a small margin and split on paragraph/line/space boundaries.
TELEGRAM_MAX_LEN = 4000


def _split_message(text: str, limit: int = TELEGRAM_MAX_LEN) -> list[str]:
    chunks: list[str] = []
    while len(text) > limit:
        # Prefer to break at a newline, then a space, before the hard limit.
        window = text[:limit]
        cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit  # no good boundary: hard cut
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def _is_owner(update: Update) -> bool:
    u = update.effective_user
    return u is not None and u.id == OWNER_USER_ID


# ---- business connection lifecycle ----

async def on_business_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = update.business_connection
    if conn is None:
        return
    rights = getattr(conn, "rights", None)
    can_reply = bool(getattr(rights, "can_reply", False)) if rights else bool(
        getattr(conn, "can_reply", False)
    )
    if conn.is_enabled:
        update_state(
            connection_id=conn.id,
            owner_user_id=conn.user.id,
            can_reply=can_reply,
        )
        log.info("business connection ENABLED id=%s user=%s can_reply=%s",
                 conn.id, conn.user.id, can_reply)
        await context.bot.send_message(
            OWNER_USER_ID,
            t("conn_on", id=conn.id, can_reply=can_reply, mode=load_state()["mode"]),
            parse_mode="HTML",
        )
    else:
        update_state(connection_id=None, can_reply=False)
        log.info("business connection DISABLED id=%s", conn.id)
        try:
            await context.bot.send_message(OWNER_USER_ID, t("conn_off"))
        except Exception:
            pass


# ---- business message handler ----

def _clip(text: str, limit: int = 1500) -> str:
    """Trim quoted text so the forward notice never exceeds Telegram's 4096-char
    message limit (which would make the whole notification fail)."""
    text = text or ""
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


async def _forward_to_owner(context, msg, customer_text: str, customer_reply: str, reason: str) -> None:
    """Notify the owner about an important customer message."""
    user = msg.from_user
    name = user.full_name if user else t("unknown_sender")
    uname = f"@{user.username}" if user and getattr(user, "username", None) else "—"
    notice = t("notice", reason=reason, name=html.escape(name),
               uname=html.escape(uname), chat_id=msg.chat.id,
               voice=t("voice_tag") if msg.voice else "",
               text=html.escape(_clip(customer_text)),
               reply=html.escape(_clip(customer_reply)))
    sent = await context.bot.send_message(OWNER_USER_ID, notice, parse_mode="HTML")
    # Remember which customer this notice belongs to, so a reply to it can be
    # relayed back to the right conversation.
    remember_forward(sent.message_id, msg.chat.id)


async def _send_business(context, conn_id: str, chat_id: int, text: str,
                         reply_markup=None, link_fallback: tuple | None = None) -> bool:
    """Send a (possibly long) message to a customer over the business connection.
    Records the sent message ids so the bot doesn't mistake its own echo for a
    human takeover. An optional inline keyboard is attached to the last chunk;
    if Telegram rejects it (business messages are sent as the owner, and those
    can't always carry inline keyboards), `link_fallback=(label, url)` is
    appended to the text as a plain hyperlink instead — so a promo link never
    silently disappears. Returns True on success."""
    try:
        chunks = _split_message(text)
        for chunk in chunks[:-1]:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=chunk, business_connection_id=conn_id,
            )
            _remember_bot_msg(sent.message_id)
        if not chunks:
            return True
        try:
            sent = await context.bot.send_message(
                chat_id=chat_id, text=chunks[-1], business_connection_id=conn_id,
                reply_markup=reply_markup,
            )
        except Exception as e:
            if reply_markup is None:
                raise
            log.warning("inline button rejected on business chat (%s) — "
                        "falling back to a text link", e)
            if link_fallback:
                label, url = link_fallback
                body = (f"{html.escape(chunks[-1])}\n\n"
                        f'👉 <a href="{html.escape(url, quote=True)}">'
                        f"{html.escape(label)}</a>")
                sent = await context.bot.send_message(
                    chat_id=chat_id, text=body, business_connection_id=conn_id,
                    parse_mode="HTML",
                )
            else:
                sent = await context.bot.send_message(
                    chat_id=chat_id, text=chunks[-1], business_connection_id=conn_id,
                )
        _remember_bot_msg(sent.message_id)
        return True
    except Exception as e:
        log.exception("send_message failed: %s", e)
        return False


def _typing_keepalive(context, conn_id: str, chat_id: int) -> asyncio.Task:
    """Keep the 'typing…' indicator alive while the AI composes. Telegram shows
    the action for ~5s only, so refresh it every 4s until the returned task is
    cancelled. Best effort: any failure (e.g. older API) is ignored."""
    async def loop():
        while True:
            try:
                await context.bot.send_chat_action(
                    chat_id=chat_id, action="typing", business_connection_id=conn_id,
                )
            except Exception:
                pass
            await asyncio.sleep(4)
    return asyncio.create_task(loop())


def _customer_lang(chat_id: int) -> str:
    """Language of the bot's own fixed lines in this chat: the one the AI last
    replied in there, else the UI language. Italian chats get the Italian
    texts, every other language the English ones."""
    lang = ai.last_language(chat_id) or UI_LANGUAGE
    return "it" if lang == "it" else "en"


def _forward_ack(chat_id: int) -> str:
    return FORWARD_ACK[_customer_lang(chat_id)]


def _promo_line(chat_id: int) -> str:
    return PROMO_APPEND_TEXT[_customer_lang(chat_id)]


def _promo_link() -> tuple | None:
    """(label, url) used as a text-link fallback when an inline button is
    rejected on a business chat."""
    return (PROMO_BUTTON_TEXT, PROMO_CHANNEL_URL) if PROMO_CHANNEL_URL else None


def _promo_markup_if_due(state, chat_id: int):
    """Inline button with the channel link, or None if the feature is
    off or this chat already saw it within the cooldown window."""
    if not PROMO_CHANNEL_URL:
        return None
    last = state.get("last_promo_at", {}).get(str(chat_id), 0)
    if time.time() - last < PROMO_COOLDOWN_DAYS * 86400:
        return None
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(PROMO_BUTTON_TEXT, url=PROMO_CHANNEL_URL)
    ]])


async def _ack_and_handoff(context, state, msg, chat_id: int,
                           customer_text: str, reason: str) -> None:
    """Reply with a short ack and hand the conversation off to the owner. Used
    for content the bot can't process itself (attachments, over-long voice
    notes) — the owner sees the original directly in their business chat."""
    fwd_on = state.get("forward_enabled", True)
    ack = _forward_ack(chat_id) if fwd_on else state["away_message"]
    markup = _promo_markup_if_due(state, chat_id)
    if await _send_business(context, state["connection_id"], chat_id, ack,
                            reply_markup=markup, link_fallback=_promo_link()):
        mark_reply(chat_id)
        if markup is not None:
            mark_promo(chat_id)
            bump_stat("promoted")
            ai.note_attachment(chat_id, PROMO_HISTORY_NOTE.format(
                button=PROMO_BUTTON_TEXT))
    if not fwd_on:
        bump_stat("away_replies")
        return
    last_fwd = state["last_forward_at"].get(str(chat_id), 0)
    if time.time() - last_fwd >= FORWARD_COOLDOWN_SECONDS:
        try:
            await _forward_to_owner(context, msg, customer_text, ack, reason)
            mark_forward(chat_id)
            bump_stat("forwarded")
        except Exception as e:
            log.exception("forward to owner failed: %s", e)


async def on_business_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.business_message
    if msg is None:
        return
    kind = ("voice" if msg.voice else "text" if msg.text else "photo"
            if msg.photo else "document" if msg.document else "other")
    log.info("business_message in chat=%s kind=%s", msg.chat.id, kind)
    # Supported: text, voice notes, photos, documents. Ignore stickers, etc.
    if not msg.text and not msg.voice and not msg.photo and not msg.document:
        return

    state = load_state()
    mode = state["mode"]
    if mode == "off":
        bump_stat("skipped")
        return

    # Messages sent by the business account owner themselves are never replied
    # to. If it's the owner typing manually (not the bot's own echoed reply),
    # treat it as a human stepping in and pause the bot on this chat.
    if msg.from_user and state.get("owner_user_id") and msg.from_user.id == state["owner_user_id"]:
        if msg.message_id in _bot_sent_ids:
            _bot_sent_ids.remove(msg.message_id)
        else:
            mark_takeover(msg.chat.id)
            log.info("owner typed in chat=%s — bot paused (human takeover)", msg.chat.id)
        return

    if not state.get("connection_id"):
        log.warning("business message without saved connection_id — ignoring")
        return
    if not state.get("can_reply"):
        log.warning("bot lacks can_reply right — no reply")
        bump_stat("skipped")
        return

    chat_id = msg.chat.id

    # A human is currently handling this conversation — stay out of the way.
    if is_paused(state, chat_id):
        log.info("chat=%s paused (human takeover) — bot silent", chat_id)
        bump_stat("paused")
        return

    last = state["last_reply_at"].get(str(chat_id), 0)
    if time.time() - last < REPLY_COOLDOWN_SECONDS:
        bump_stat("skipped")
        return

    # Photos / documents can't be read by the bot, but instead of ignoring them
    # we acknowledge the customer and hand the attachment off to the owner (who
    # sees the media directly in their own business chat).
    if not msg.text and not msg.voice:
        media = t("media_photo") if msg.photo else t("media_document")
        await _ack_and_handoff(context, state, msg, chat_id, media,
                               t("reason_attachment"))
        return

    # Resolve the incoming text. Voice notes are transcribed locally with
    # faster-whisper (done only after the gates above, to avoid wasting CPU
    # on messages we wouldn't reply to anyway).
    if msg.text:
        incoming_text = msg.text
    else:  # msg.voice
        if not WHISPER_ENABLED:
            log.info("voice message received but WHISPER_ENABLED=0 — skipping")
            bump_stat("skipped")
            return
        duration = msg.voice.duration or 0
        if VOICE_MAX_SECONDS and duration > VOICE_MAX_SECONDS:
            # Transcribing very long audio would hog the CPU for minutes on a
            # small host — ack the customer and hand the note off instead.
            log.info("voice too long (%ds > %ds) — handing off", duration, VOICE_MAX_SECONDS)
            await _ack_and_handoff(
                context, state, msg, chat_id,
                t("voice_long_text", secs=duration), t("reason_voice_long"))
            return
        try:
            tg_file = await context.bot.get_file(msg.voice.file_id)
            audio = bytes(await tg_file.download_as_bytearray())
            incoming_text = (await transcribe.transcribe(audio)).strip()
        except Exception as e:
            log.exception("voice transcription failed: %s", e)
            bump_stat("skipped")
            return
        if not incoming_text:
            log.info("empty transcription — skipping")
            bump_stat("skipped")
            return
        log.info("voice transcribed (%ds): %s", msg.voice.duration, incoming_text[:120])

    # Bound token cost when someone pastes a wall of text.
    if len(incoming_text) > MAX_INPUT_CHARS:
        log.info("incoming text truncated %d -> %d chars", len(incoming_text), MAX_INPUT_CHARS)
        incoming_text = incoming_text[:MAX_INPUT_CHARS]

    # decide whether to use AI or away
    use_ai = mode == "ai" or (mode == "auto" and in_schedule(state))

    # Channel promo: allowed at most once per PROMO_COOLDOWN_DAYS per chat.
    last_promo = state.get("last_promo_at", {}).get(str(chat_id), 0)
    promo_allowed = bool(PROMO_CHANNEL_URL) and (
        time.time() - last_promo >= PROMO_COOLDOWN_DAYS * 86400)

    forward = False
    if use_ai:
        # Append the owner's knowledge base (if any) so the AI answers from it.
        system_prompt = state["system_prompt"]
        kb = state.get("knowledge", "").strip()
        if kb:
            system_prompt = system_prompt + KB_PREAMBLE + kb
        # Tell the AI who it's talking to (Telegram profile), so it never asks
        # for the name and can spot joke answers (an obviously fake name).
        sender = msg.from_user
        if sender:
            uname = f" (@{sender.username})" if getattr(sender, "username", None) else ""
            system_prompt += SENDER_CONTEXT.format(name=f"{sender.full_name}{uname}")
        if PROMO_CHANNEL_URL:
            system_prompt += PROMO_INSTRUCTIONS if promo_allowed else PROMO_ALREADY_NOTE
        typing = _typing_keepalive(context, state["connection_id"], chat_id)
        try:
            # 3rd value is the [[CHANNEL]] marker: stripped from the text by
            # ai.py and ignored here — the invite line is the bot's job now.
            reply, forward, _ = await ai.generate_reply(chat_id, incoming_text, system_prompt)
            if ai.take_switch_notice():
                await context.bot.send_message(OWNER_USER_ID, t("api_switched"))
        except Exception as e:
            # AI failure: never fall back to away_message (which is the explicit
            # "I'm offline" text). Use a short generic ack so the bot still replies.
            log.exception("AI fail, sending short ack: %s", e)
            reply = AI_FAILURE_ACK[_customer_lang(chat_id)]
            use_ai = False
            promo_allowed = False  # don't bolt a channel pitch onto an error ack
        finally:
            typing.cancel()
    else:
        reply = state["away_message"]

    # An explicit request to talk to a human always escalates, even in away
    # mode where the AI isn't involved to emit its marker. Use incoming_text so
    # it also works for voice notes (msg.text is None once transcribed).
    wants_human = _wants_human(incoming_text)
    should_forward = state.get("forward_enabled", True) and (forward or wants_human)

    # When forwarding without the AI, give the customer a reassuring ack
    # instead of the generic "I'm offline" away message.
    if should_forward and not use_ai:
        reply = _forward_ack(chat_id)

    # Growth mode: attach the channel button to the first reply in every
    # chat (AI or away), then not again until the per-chat cooldown expires.
    markup = None
    if promo_allowed:
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(PROMO_BUTTON_TEXT, url=PROMO_CHANNEL_URL)
        ]])
        # The invite line is written here and only here. Leaving it to the AI
        # meant it either skipped it (button with nothing explaining it) or
        # wrote one without emitting the marker this used to check, so both
        # lines went out and said the same thing twice.
        reply = f"{reply.rstrip()}\n\n{_promo_line(chat_id)}"

    if await _send_business(context, state["connection_id"], chat_id, reply,
                            reply_markup=markup, link_fallback=_promo_link()):
        mark_reply(chat_id)
        bump_stat("ai_replies" if use_ai else "away_replies")
        if markup is not None:
            mark_promo(chat_id)
            bump_stat("promoted")
            ai.note_attachment(chat_id, PROMO_HISTORY_NOTE.format(
                button=PROMO_BUTTON_TEXT))

    # Forward to the owner. Explicit human requests bypass the anti-spam
    # cooldown; AI-detected escalations respect it.
    if should_forward:
        last_fwd = state["last_forward_at"].get(str(chat_id), 0)
        if wants_human or time.time() - last_fwd >= FORWARD_COOLDOWN_SECONDS:
            reason = t("reason_human") if wants_human else t("reason_ai")
            try:
                await _forward_to_owner(context, msg, incoming_text, reply, reason)
                mark_forward(chat_id)
                bump_stat("forwarded")
            except Exception as e:
                log.exception("forward to owner failed: %s", e)


# ---- owner control panel (inline menu, language from UI_LANGUAGE) ----

# Free-text settings the owner can change from the menu: pressing a button parks
# the field here, and the next DM the owner sends becomes its new value.
# In-memory on purpose — a restart simply cancels a half-finished edit.
_pending_input: dict[int, str] = {}


def _mode_label(mode: str) -> str:
    return t(f"mode_{mode}") if mode in MODES else mode


def _hours(s: dict) -> str:
    sched = s.get("schedule")
    return f"{sched['start']}–{sched['end']}" if sched else t("always_on")


def _menu_text(s: dict) -> str:
    kb = s.get("knowledge", "")
    paused = [c for c in s.get("human_takeover_at", {}) if is_paused(s, int(c))]
    mode = s.get("mode", "auto")
    lines = [
        t("menu_title"),
        t("menu_mode", label=html.escape(_mode_label(mode)),
          descr=t(f"descr_{mode}") if mode in MODES else ""),
        t("menu_hours", hours=_hours(s)),
        t("menu_fwd", state=t("on") if s.get("forward_enabled", True) else t("off")),
        t("menu_kb", state=t("kb_set", n=len(kb)) if kb else t("kb_empty")),
    ]
    if not s.get("connection_id"):
        lines.append("\n" + t("menu_no_conn"))
    elif not s.get("can_reply"):
        lines.append("\n" + t("menu_no_reply"))
    if paused:
        lines.append("\n" + t("menu_paused", n=len(paused)))
    lines.append("\n" + t("menu_choose"))
    return "\n".join(lines)


def _btn(key: str, data: str, **kw) -> InlineKeyboardButton:
    return InlineKeyboardButton(t(key, **kw), callback_data=data)


def _menu_markup(s: dict) -> InlineKeyboardMarkup:
    mode = s.get("mode", "auto")

    def mode_btn(key: str) -> InlineKeyboardButton:
        label = _mode_label(key)
        return InlineKeyboardButton(
            f"✅ {label}" if mode == key else label, callback_data=f"m:mode:{key}")

    fwd_on = s.get("forward_enabled", True)
    rows = [
        [mode_btn("ai"), mode_btn("auto")],
        [mode_btn("away"), mode_btn("off")],
        [_btn("btn_stats", "m:stats"),
         _btn("btn_fwd", "m:fwd", state="ON" if fwd_on else "OFF")],
        [_btn("btn_away", "m:set:away"), _btn("btn_prompt", "m:set:prompt")],
        [_btn("btn_kb", "m:kb"), _btn("btn_sched", "m:sched")],
        [_btn("btn_resume_all", "m:resume"), _btn("btn_reset", "m:reset")],
    ]
    if credits.enabled():
        rows.append([_btn("btn_credits", "m:credits")])
    if PROMO_CHANNEL_URL:
        rows.append([_btn("btn_promo", "m:promo"), _btn("btn_defaults", "m:defaults")])
    else:
        rows.append([_btn("btn_defaults", "m:defaults")])
    return InlineKeyboardMarkup(rows)


def _back_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("btn_back", "m:home")]])


def _cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_btn("btn_cancel", "m:home")]])


async def _show_menu(update: Update, edit: bool = False) -> None:
    s = load_state()
    text, markup = _menu_text(s), _menu_markup(s)
    if edit and update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=markup)
            return
        except Exception:
            pass  # message unchanged or too old — fall through to a new one
    target = update.effective_message
    if target:
        await target.reply_html(text, reply_markup=markup)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    _pending_input.pop(update.effective_user.id, None)
    await _show_menu(update)


# What each free-text edit asks for: i18n key of the prompt per field.
_PROMPTS = {"away": "p_away", "prompt": "p_prompt", "kb": "p_kb",
            "sched": "p_sched", "promo": "p_promo"}


async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle every button of the owner control panel."""
    q = update.callback_query
    if q is None:
        return
    if not _is_owner(update):
        await q.answer()
        return
    data = q.data or ""
    uid = update.effective_user.id
    _pending_input.pop(uid, None)
    s = load_state()

    # ---- navigation ----
    if data == "m:home":
        await q.answer()
        await _show_menu(update, edit=True)
        return

    # ---- mode ----
    if data.startswith("m:mode:"):
        mode = data.split(":")[2]
        if mode in MODES:
            update_state(mode=mode)
            await q.answer(t("ans_mode", label=_mode_label(mode)))
        await _show_menu(update, edit=True)
        return

    # ---- forward toggle ----
    if data == "m:fwd":
        new = not s.get("forward_enabled", True)
        update_state(forward_enabled=new)
        await q.answer(t("ans_fwd_on") if new else t("ans_fwd_off"))
        await _show_menu(update, edit=True)
        return

    # ---- API credits ----
    if data == "m:credits":
        await q.answer()
        await q.edit_message_text(credits.summary(ai.api_key_off()), parse_mode="HTML",
                                  reply_markup=_BACK_MARKUP)
        return

    # ---- stats ----
    if data == "m:stats":
        await q.answer()
        st = s.get("stats", {})
        paused = [c for c in s.get("human_takeover_at", {}) if is_paused(s, int(c))]
        txt = t("stats", ai=st.get("ai_replies", 0), away=st.get("away_replies", 0),
                fwd=st.get("forwarded", 0), rel=st.get("relayed", 0),
                promo=st.get("promoted", 0), paused=st.get("paused", 0),
                skipped=st.get("skipped", 0), paused_now=len(paused),
                conn=t("conn_active") if s.get("connection_id") else t("conn_missing"))
        await q.edit_message_text(txt, parse_mode="HTML", reply_markup=_back_markup())
        return

    # ---- knowledge base: view / edit / clear ----
    if data == "m:kb":
        await q.answer()
        kb = s.get("knowledge", "")
        body = html.escape(kb[:2500]) if kb else t("kb_empty_i")
        rows = [[_btn("btn_edit", "m:set:kb")]]
        if kb:
            rows.append([_btn("btn_clear", "m:kb:clear")])
        rows.append([_btn("btn_back", "m:home")])
        await q.edit_message_text(
            t("kb_view", body=body),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data == "m:kb:clear":
        update_state(knowledge="")
        await q.answer(t("ans_kb_cleared"))
        await _show_menu(update, edit=True)
        return

    # ---- schedule: view / edit / disable ----
    if data == "m:sched":
        await q.answer()
        rows = [[_btn("btn_set_hours", "m:set:sched")]]
        if s.get("schedule"):
            rows.append([_btn("btn_always", "m:sched:off")])
        rows.append([_btn("btn_back", "m:home")])
        await q.edit_message_text(
            t("sched_view", cur=_hours(s)),
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        return

    if data == "m:sched:off":
        update_state(schedule=None)
        await q.answer(t("ans_sched_off"))
        await _show_menu(update, edit=True)
        return

    # ---- free-text edits ----
    if data.startswith("m:set:"):
        field = data.split(":")[2]
        await q.answer()
        _pending_input[uid] = field
        cur = {
            "away": s.get("away_message", ""),
            "prompt": s.get("system_prompt", ""),
            "kb": s.get("knowledge", "") or t("empty_paren"),
            "sched": _hours(s),
            "promo": "",
        }.get(field, "")
        await q.edit_message_text(
            t(_PROMPTS[field], cur=html.escape(str(cur)[:400])),
            parse_mode="HTML", reply_markup=_cancel_markup())
        return

    # ---- resume everywhere ----
    if data == "m:resume":
        n = clear_takeover(None)
        await q.answer(t("ans_resumed", n=n))
        await _show_menu(update, edit=True)
        return

    # ---- destructive actions: ask first ----
    if data == "m:reset":
        await q.answer()
        await q.edit_message_text(
            t("confirm_reset"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                _btn("btn_yes_clear", "m:reset:ok"), _btn("btn_cancel", "m:home"),
            ]]))
        return

    if data == "m:reset:ok":
        ai.reset_history()
        await q.answer(t("ans_reset"))
        await _show_menu(update, edit=True)
        return

    if data == "m:defaults":
        await q.answer()
        await q.edit_message_text(
            t("confirm_defaults"),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                _btn("btn_yes_restore", "m:defaults:ok"), _btn("btn_cancel", "m:home"),
            ]]))
        return

    if data == "m:defaults:ok":
        update_state(away_message=DEFAULT_AWAY_MESSAGE,
                     system_prompt=DEFAULT_SYSTEM_PROMPT)
        ai.reset_history()
        await q.answer(t("ans_defaults"))
        await _show_menu(update, edit=True)
        return

    # ---- promo: ask for the chat id ----
    if data == "m:promo":
        await q.answer()
        _pending_input[uid] = "promo"
        await q.edit_message_text(t("p_promo"), parse_mode="HTML",
                                  reply_markup=_cancel_markup())
        return

    await q.answer()


async def _apply_pending(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         field: str, text: str) -> None:
    """Store the value the owner just typed for the parked setting."""
    msg = update.message
    if field == "away":
        update_state(away_message=text)
        await msg.reply_text(t("ok_away"))
    elif field == "prompt":
        update_state(system_prompt=text)
        ai.reset_history()
        await msg.reply_text(t("ok_prompt"))
    elif field == "kb":
        update_state(knowledge=text)
        await msg.reply_text(t("ok_kb", n=len(text)))
    elif field == "sched":
        m = TIME_RE.match(text.strip())
        if not m:
            _pending_input[update.effective_user.id] = "sched"
            await msg.reply_text(t("bad_hours"), reply_markup=_cancel_markup())
            return
        start, end = f"{m.group(1)}:{m.group(2)}", f"{m.group(3)}:{m.group(4)}"
        update_state(schedule={"start": start, "end": end})
        await msg.reply_text(t("ok_hours", start=start, end=end))
    elif field == "promo":
        try:
            chat_id = int(text.strip())
        except ValueError:
            _pending_input[update.effective_user.id] = "promo"
            await msg.reply_text(t("bad_chat_id"), reply_markup=_cancel_markup())
            return
        await _send_promo(update, context, chat_id)
        return
    await _show_menu(update)


async def _send_promo(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      chat_id: int) -> None:
    """Send the channel invite (text + button) to one customer chat."""
    msg = update.effective_message
    if not PROMO_CHANNEL_URL:
        await msg.reply_text(t("promo_off"))
        return
    conn = load_state().get("connection_id")
    if not conn:
        await msg.reply_text(t("no_conn"))
        return
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(PROMO_BUTTON_TEXT, url=PROMO_CHANNEL_URL)]])
    if await _send_business(context, conn, chat_id, PROMO_MANUAL_TEXT[_customer_lang(chat_id)],
                            reply_markup=markup, link_fallback=_promo_link()):
        mark_promo(chat_id)
        bump_stat("promoted")
        ai.note_attachment(chat_id, PROMO_HISTORY_NOTE.format(
            button=PROMO_BUTTON_TEXT))
        await msg.reply_text(t("promo_sent", chat_id=chat_id))
    else:
        await msg.reply_text(t("send_failed"))


# ---- owner DM: relay a reply back to the customer ----

async def on_owner_dm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Owner DM router: a reply to a forwarded notice reaches the customer; a
    message typed after a menu button fills that setting; anything else gets
    the control panel."""
    if not _is_owner(update):
        return
    msg = update.message
    if msg is None or not msg.text:
        return
    uid = update.effective_user.id

    # 1) Reply to a forwarded notice → relay to the customer.
    reply_to = msg.reply_to_message
    chat_id = lookup_forward(reply_to.message_id) if reply_to else None
    if chat_id is not None:
        _pending_input.pop(uid, None)
        state = load_state()
        conn = state.get("connection_id")
        if not conn:
            await msg.reply_text(t("no_conn"))
            return
        if await _send_business(context, conn, chat_id, msg.text):
            mark_takeover(chat_id)  # the human is handling this chat now
            bump_stat("relayed")
            await msg.reply_text(
                t("relayed"),
                reply_markup=InlineKeyboardMarkup([[_btn("btn_resume_here", "m:resume")]]))
        else:
            await msg.reply_text(t("relay_failed"))
        return

    # 2) A menu button parked a setting → this message is its new value.
    field = _pending_input.pop(uid, None)
    if field:
        await _apply_pending(update, context, field, msg.text.strip())
        return

    # 3) Reply to something unrelated, or a plain message → show the panel.
    if reply_to is not None:
        await msg.reply_text(t("reply_unknown"))
        return
    await _show_menu(update)


# ---- owner commands (DM directly to the bot) ----

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    _pending_input.pop(update.effective_user.id, None)
    await update.message.reply_html(t("welcome"))
    await _show_menu(update)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    s = load_state()
    sched = s["schedule"]
    sched_str = f"{sched['start']}-{sched['end']}" if sched else "off (always AI in 'auto')"

    def preview(text: str) -> str:
        # escape: away/prompt are free text and could break the HTML parse mode
        return html.escape(text[:80] + ("…" if len(text) > 80 else ""))

    paused = [cid for cid in s.get("human_takeover_at", {}) if is_paused(s, int(cid))]
    txt = (
        f"<b>Status</b>\n"
        f"connection_id: <code>{s['connection_id']}</code>\n"
        f"can_reply: {s['can_reply']}\n"
        f"mode: <b>{s['mode']}</b>\n"
        f"schedule: {sched_str}\n"
        f"forward: <b>{'on' if s.get('forward_enabled', True) else 'off'}</b>\n"
        f"paused chats: {', '.join(paused) if paused else 'none'}\n"
        f"away: {preview(s['away_message'])}\n"
        f"prompt: {preview(s['system_prompt'])}\n"
        f"kb: {'set (' + str(len(s.get('knowledge', ''))) + ' chars)' if s.get('knowledge') else 'empty'}\n"
        f"stats: {s['stats']}"
    )
    await update.message.reply_html(txt)


async def cmd_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    if not context.args:
        await update.message.reply_text(f"Usage: /mode {'|'.join(sorted(MODES))}")
        return
    m = context.args[0].lower()
    if m not in MODES:
        await update.message.reply_text(f"Invalid mode. Use one of: {sorted(MODES)}")
        return
    update_state(mode=m)
    await update.message.reply_text(t("ok_mode", label=_mode_label(m)))


async def cmd_away(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(f"Usage: /away <message>\nCurrent:\n{load_state()['away_message']}")
        return
    update_state(away_message=text)
    await update.message.reply_text(t("ok_away"))


async def cmd_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(f"Usage: /prompt <text>\nCurrent:\n{load_state()['system_prompt']}")
        return
    update_state(system_prompt=text)
    # Previous history was generated with the old prompt — wipe it
    ai.reset_history()
    await update.message.reply_text(t("ok_prompt"))


async def cmd_kb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Knowledge base / FAQ the AI answers from. /kb shows it, /kb <text> sets
    it, /kb clear removes it."""
    if not _is_owner(update):
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        cur = load_state().get("knowledge", "")
        body = cur if cur else "(empty)"
        full = (
            "Knowledge base (facts the AI answers from — hours, address, prices, "
            "FAQ):\n\n"
            f"{body}\n\n"
            "Set it with: /kb <text>   ·   clear it with: /kb clear"
        )
        # A long KB would exceed Telegram's 4096-char limit in one message.
        for chunk in _split_message(full):
            await update.message.reply_text(chunk)
        return
    if text.lower() == "clear":
        update_state(knowledge="")
        await update.message.reply_text(t("ok_kb_cleared"))
        return
    update_state(knowledge=text)
    await update.message.reply_text(t("ok_kb", n=len(text)))


async def cmd_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    if not context.args:
        s = load_state()["schedule"]
        cur = f"{s['start']}-{s['end']}" if s else "off"
        await update.message.reply_text(f"Usage: /schedule HH:MM-HH:MM | off\nCurrent: {cur}")
        return
    arg = context.args[0]
    if arg.lower() == "off":
        update_state(schedule=None)
        await update.message.reply_text("✅ schedule = off (in 'auto' mode AI always replies)")
        return
    m = TIME_RE.match(arg)
    if not m:
        await update.message.reply_text("Format: HH:MM-HH:MM (e.g. 09:00-19:00)")
        return
    start = f"{m.group(1)}:{m.group(2)}"
    end = f"{m.group(3)}:{m.group(4)}"
    update_state(schedule={"start": start, "end": end})
    await update.message.reply_text(f"✅ schedule = {start}-{end} (in 'auto': AI inside, away outside)")


async def cmd_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    if not context.args:
        cur = "on" if load_state().get("forward_enabled", True) else "off"
        await update.message.reply_text(
            f"Usage: /forward on|off\nCurrent: {cur}\n\n"
            "When on, I forward you any message I can't answer or when the "
            "customer asks to talk to you."
        )
        return
    arg = context.args[0].lower()
    if arg not in {"on", "off"}:
        await update.message.reply_text("Usage: /forward on|off")
        return
    update_state(forward_enabled=(arg == "on"))
    await update.message.reply_text(t("ok_fwd", state=t("on") if arg == "on" else t("off")))


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually silence the bot on one chat (same mechanism as a human
    takeover); /resume lifts it early."""
    if not _is_owner(update):
        return
    if not context.args:
        await update.message.reply_text(t("pause_usage"))
        return
    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Usage: /pause <chat_id>")
        return
    mark_takeover(chat_id)
    await update.message.reply_text(
        f"⏸️ bot paused on chat {chat_id} for {HANDOFF_PAUSE_SECONDS // 60} min "
        f"(/resume {chat_id} to lift it early)"
    )


async def cmd_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually send the channel invite (text + button) to a customer
    chat: /promo <chat_id>, or reply to a forwarded notice with /promo.
    Bypasses the automatic per-chat cooldown."""
    if not _is_owner(update):
        return
    if not PROMO_CHANNEL_URL:
        await update.message.reply_text(t("promo_off"))
        return
    chat_id = None
    if context.args:
        try:
            chat_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /promo <chat_id>")
            return
    elif update.message.reply_to_message:
        chat_id = lookup_forward(update.message.reply_to_message.message_id)
    if chat_id is None:
        await update.message.reply_text(t("promo_usage"))
        return
    state = load_state()
    conn = state.get("connection_id")
    if not conn:
        await update.message.reply_text(t("no_conn"))
        return
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(PROMO_BUTTON_TEXT, url=PROMO_CHANNEL_URL)
    ]])
    if await _send_business(context, conn, chat_id, PROMO_MANUAL_TEXT[_customer_lang(chat_id)],
                            reply_markup=markup, link_fallback=_promo_link()):
        mark_promo(chat_id)
        bump_stat("promoted")
        ai.note_attachment(chat_id, PROMO_HISTORY_NOTE.format(
            button=PROMO_BUTTON_TEXT))
        await update.message.reply_text(t("promo_sent", chat_id=chat_id))
    else:
        await update.message.reply_text(t("send_failed"))


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    chat_id = None
    if context.args:
        try:
            chat_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /resume [chat_id]")
            return
    n = clear_takeover(chat_id)
    target = f"chat {chat_id}" if chat_id is not None else "all chats"
    await update.message.reply_text(f"✅ bot resumed on {target} ({n} cleared)")


async def cmd_reset_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    chat_id = None
    if context.args:
        try:
            chat_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Usage: /reset_history [chat_id]")
            return
    ai.reset_history(chat_id)
    target = f"chat {chat_id}" if chat_id is not None else "all chats"
    await update.message.reply_text(f"✅ conversation history cleared for {target}")


async def cmd_defaults(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update):
        return
    update_state(away_message=DEFAULT_AWAY_MESSAGE, system_prompt=DEFAULT_SYSTEM_PROMPT)
    ai.reset_history()
    await update.message.reply_text(t("ok_defaults"))
