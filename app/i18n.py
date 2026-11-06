"""Owner-facing texts (control panel, notices, confirmations) in every
supported UI language. Pick one with UI_LANGUAGE in .env (default English).

Customer-facing fixed lines (forward ack, channel invite…) follow the
customer's language instead and live in config.py.

To add a language: copy the "en" block, translate the values (keep every
{placeholder} as is) and add its code to SUPPORTED. A missing key falls back
to English, so a partial translation still works.
"""
from config import UI_LANGUAGE

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ── business connection ──
        "conn_on": ("✅ Bot connected to your account.\n"
                    "connection_id: <code>{id}</code>\n"
                    "can_reply: <b>{can_reply}</b>\n"
                    "Current mode: <b>{mode}</b>"),
        "conn_off": "⚠️ Bot disconnected from your account.",
        "no_conn": "⚠️ No active business connection.",

        # ── forward notice ──
        "notice_name": "📨 Message to forward",
        "notice": ("<b>{notice_name}</b> — {reason}\n"
                   "From: <b>{name}</b> ({uname})\n"
                   "chat_id: <code>{chat_id}</code>\n\n"
                   "💬 <i>Customer:</i>{voice}\n{text}\n\n"
                   "🤖 <i>Bot's reply:</i>\n{reply}\n\n"
                   "↩️ <i>Reply to this message to write to the customer.</i>"),
        "unknown_sender": "Unknown",
        "voice_tag": " 🎙️ (transcribed voice note)",
        "reason_attachment": "attachment from the customer",
        "reason_voice_long": "voice note too long",
        "reason_human": "the customer asked for you",
        "reason_ai": "the bot can't answer",
        "media_photo": "[a photo]",
        "media_document": "[a document]",
        "voice_long_text": "[{secs}s voice note — too long to transcribe]",

        # ── modes ──
        "mode_off": "🔴 Off",
        "mode_away": "💤 Away",
        "mode_ai": "🤖 AI",
        "mode_auto": "⏰ Automatic",
        "descr_off": "the bot ignores every message",
        "descr_away": "replies only with the away message",
        "descr_ai": "always replies with the AI",
        "descr_auto": "AI during the set hours, away message outside",

        # ── panel ──
        "menu_title": "🤖 <b>Secretary — control panel</b>\n",
        "menu_mode": "Mode: <b>{label}</b> ({descr})",
        "menu_hours": "AI hours: <b>{hours}</b>",
        "menu_fwd": "Message forwarding: <b>{state}</b>",
        "menu_kb": "Business info: <b>{state}</b>",
        "menu_no_conn": "⚠️ <b>No active business connection.</b>",
        "menu_no_reply": "⚠️ <b>Missing permission to reply.</b>",
        "menu_paused": "⏸️ Paused in {n} chats",
        "menu_choose": "Pick an option 👇",
        "always_on": "always on",
        "on": "on",
        "off": "off",
        "kb_set": "set ({n} characters)",
        "kb_empty": "empty",

        # ── API credits (CLAUDE_BACKEND=auto) ──
        "btn_credits": "💳 API credits",
        "credits": ("💳 <b>API credits</b>\n\n"
                    "Spent by this bot: <b>{spent} $</b>\n"
                    "Left: at most <b>{left} $</b> of {total}"),
        "credits_expire": "Expire in <b>{days}</b> days",
        "credits_expired": "<b>Expired</b>",
        "credits_low": "⚠️ Almost used up: then the bot switches to the subscription by itself.",
        "credits_note": ("<i>Counts only this bot's replies: if other apps use the same "
                         "credits, fewer are left. The exact balance is in the Console.</i>"),
        "credits_off": "💳 <b>API credits used up</b>: replies now run on your Claude subscription.",
        "api_switched": ("💳 API key rejected (credits used up or key revoked): "
                         "AI replies now run on your Claude subscription."),

        # ── buttons ──
        "btn_stats": "📊 Stats",
        "btn_fwd": "📨 Forwarding: {state}",
        "btn_away": "✍️ Away message",
        "btn_prompt": "🧠 AI personality",
        "btn_kb": "📚 Business info",
        "btn_sched": "🕐 AI hours",
        "btn_resume_all": "▶️ Resume everywhere",
        "btn_reset": "🗑 Clear memory",
        "btn_promo": "📢 Send channel invite",
        "btn_defaults": "♻️ Restore defaults",
        "btn_back": "⬅️ Back to menu",
        "btn_cancel": "❌ Cancel",
        "btn_edit": "✏️ Edit",
        "btn_clear": "🗑 Clear",
        "btn_set_hours": "✏️ Set hours",
        "btn_always": "♾ Always on",
        "btn_yes_clear": "✅ Yes, clear it",
        "btn_yes_restore": "✅ Yes, restore",
        "btn_resume_here": "▶️ Resume the bot here",

        # ── free-text edits ──
        "p_away": ("✍️ <b>Away message</b>\n\nSend me the new text customers "
                   "get when the bot is in Away mode.\n\nCurrent:\n<i>{cur}</i>"),
        "p_prompt": ("🧠 <b>AI personality</b>\n\nSend me the new instructions: "
                     "who you are, how it should behave, what tone to use.\n\n"
                     "⚠️ Changing it clears the conversation memory.\n\n"
                     "Current:\n<i>{cur}</i>"),
        "p_kb": ("📚 <b>Business info</b>\n\nSend me the facts the AI should "
                 "know (hours, address, prices, FAQ…). It will answer from "
                 "these only, without making things up.\n\nCurrent:\n<i>{cur}</i>"),
        "p_sched": ("🕐 <b>AI hours</b> (Automatic mode)\n\nSend me the time "
                    "window as <code>09:00-19:00</code>.\n\nCurrent: <b>{cur}</b>"),
        "p_promo": ("📢 <b>Send channel invite</b>\n\nSend me the "
                    "<code>chat_id</code> of the customer to invite.\n\nYou find "
                    "it in the “{notice_name}” notices."),
        "empty_paren": "(empty)",

        # ── button answers & sub-screens ──
        "ans_mode": "Mode: {label}",
        "ans_fwd_on": "Forwarding on",
        "ans_fwd_off": "Forwarding off",
        "stats": ("📊 <b>Stats</b>\n\n"
                  "🤖 AI replies: <b>{ai}</b>\n"
                  "💤 Away replies: <b>{away}</b>\n"
                  "📨 Messages forwarded: <b>{fwd}</b>\n"
                  "↩️ Your replies relayed: <b>{rel}</b>\n"
                  "📢 Channel invites: <b>{promo}</b>\n"
                  "⏸️ Ignored (paused): <b>{paused}</b>\n"
                  "⏭️ Skipped: <b>{skipped}</b>\n\n"
                  "Chats paused now: <b>{paused_now}</b>\n"
                  "Connection: <b>{conn}</b>"),
        "conn_active": "active",
        "conn_missing": "missing",
        "kb_view": "📚 <b>Business info</b>\n\n{body}",
        "kb_empty_i": "<i>(empty)</i>",
        "ans_kb_cleared": "Info cleared",
        "sched_view": ("🕐 <b>AI hours</b> (Automatic mode)\n\nCurrent: <b>{cur}</b>\n\n"
                       "Outside these hours the bot sends the away message."),
        "ans_sched_off": "AI always on in Automatic",
        "ans_resumed": "Bot resumed in {n} chats",
        "confirm_reset": ("🗑 <b>Clear the conversation memory?</b>\n\n"
                          "The bot will forget earlier messages from every "
                          "customer. Settings and stats stay."),
        "ans_reset": "Memory cleared",
        "confirm_defaults": ("♻️ <b>Restore the defaults?</b>\n\n"
                             "Away message and AI personality go back to the "
                             "originals, and the memory is cleared. Business "
                             "info stays."),
        "ans_defaults": "Defaults restored",

        # ── confirmations ──
        "ok_away": "✅ Away message updated.",
        "ok_prompt": "✅ Personality updated (memory cleared).",
        "ok_kb": "✅ Info updated ({n} characters). The AI uses it from the next message.",
        "ok_kb_cleared": "✅ Business info cleared.",
        "ok_hours": "✅ AI hours: {start}–{end}",
        "ok_mode": "✅ Mode: {label}",
        "ok_fwd": "✅ Message forwarding: {state}",
        "ok_defaults": "✅ Defaults restored.",
        "bad_hours": "⚠️ Invalid format. Type for example 09:00-19:00",
        "bad_chat_id": "⚠️ I need a numeric chat_id. Try again.",
        "promo_off": "⚠️ Channel not configured (PROMO_CHANNEL_URL is empty).",
        "promo_sent": "✅ Channel invite sent to chat {chat_id}",
        "promo_usage": ("Usage: /promo <chat_id>, or reply to a “{notice_name}” "
                        "notice with /promo."),
        "pause_usage": ("Usage: /pause <chat_id>\n"
                        "You find the chat_id in the “{notice_name}” notices."),
        "send_failed": "⚠️ Sending failed. Try again.",

        # ── owner DM ──
        "relayed": "✅ Sent to the customer. The bot stays paused in this chat.",
        "relay_failed": "⚠️ Couldn't send it to the customer. Try again.",
        "reply_unknown": ("I can't find the conversation linked to that message. "
                          "Reply directly to a “{notice_name}” notice."),
        "welcome": ("👋 Hi! I'm your <b>Secretary</b>: I answer your Telegram "
                    "messages when you're not around.\n\n"
                    "💡 To answer a customer, <b>reply</b> to a “{notice_name}” "
                    "notice: your text goes straight to them.\n\n"
                    "Open this panel again anytime with /menu."),

        # ── bot command menu ──
        "cmd_menu": "🎛 Control panel",
        "cmd_start": "▶️ Start the bot",
    },

    "it": {
        "conn_on": ("✅ Bot collegato al tuo account.\n"
                    "connection_id: <code>{id}</code>\n"
                    "can_reply: <b>{can_reply}</b>\n"
                    "Modalità attuale: <b>{mode}</b>"),
        "conn_off": "⚠️ Bot scollegato dal tuo account.",
        "no_conn": "⚠️ Nessuna connessione business attiva.",

        "notice_name": "📨 Messaggio da inoltrare",
        "notice": ("<b>{notice_name}</b> — {reason}\n"
                   "Da: <b>{name}</b> ({uname})\n"
                   "chat_id: <code>{chat_id}</code>\n\n"
                   "💬 <i>Cliente:</i>{voice}\n{text}\n\n"
                   "🤖 <i>Risposta del bot:</i>\n{reply}\n\n"
                   "↩️ <i>Rispondi a questo messaggio per scrivere al cliente.</i>"),
        "unknown_sender": "Sconosciuto",
        "voice_tag": " 🎙️ (vocale trascritto)",
        "reason_attachment": "allegato dal cliente",
        "reason_voice_long": "vocale troppo lungo",
        "reason_human": "richiesta esplicita del cliente",
        "reason_ai": "il bot non sa rispondere",
        "media_photo": "[una foto]",
        "media_document": "[un documento]",
        "voice_long_text": "[vocale di {secs}s — troppo lungo per la trascrizione]",

        "mode_off": "🔴 Spento",
        "mode_away": "💤 Assenza",
        "mode_ai": "🤖 AI",
        "mode_auto": "⏰ Automatico",
        "descr_off": "il bot ignora tutti i messaggi",
        "descr_away": "risponde solo col messaggio di assenza",
        "descr_ai": "risponde sempre con l'AI",
        "descr_auto": "AI negli orari impostati, assenza fuori",

        "menu_title": "🤖 <b>Segretario — pannello di controllo</b>\n",
        "menu_mode": "Modalità: <b>{label}</b> ({descr})",
        "menu_hours": "Orari AI: <b>{hours}</b>",
        "menu_fwd": "Inoltro messaggi: <b>{state}</b>",
        "menu_kb": "Info attività: <b>{state}</b>",
        "menu_no_conn": "⚠️ <b>Nessuna connessione business attiva.</b>",
        "menu_no_reply": "⚠️ <b>Manca il permesso di rispondere.</b>",
        "menu_paused": "⏸️ In pausa su {n} chat",
        "menu_choose": "Scegli cosa fare 👇",
        "always_on": "sempre attivo",
        "on": "attivo",
        "off": "disattivo",
        "kb_set": "impostata ({n} caratteri)",
        "kb_empty": "vuota",

        "btn_credits": "💳 Crediti API",
        "credits": ("💳 <b>Crediti API</b>\n\n"
                    "Spesi da questo bot: <b>{spent} $</b>\n"
                    "Rimasti: al massimo <b>{left} $</b> su {total}"),
        "credits_expire": "Scadono tra <b>{days}</b> giorni",
        "credits_expired": "<b>Scaduti</b>",
        "credits_low": "⚠️ Stanno per finire: poi il bot passa da solo all'abbonamento.",
        "credits_note": ("<i>Conta solo le risposte di questo bot: se altre app usano gli "
                         "stessi crediti, ne restano meno. Il saldo esatto è nella Console.</i>"),
        "credits_off": "💳 <b>Crediti API finiti</b>: le risposte usano l'abbonamento Claude.",
        "api_switched": ("💳 Chiave API rifiutata (crediti finiti o chiave revocata): "
                         "le risposte AI ora usano l'abbonamento Claude."),

        "btn_stats": "📊 Statistiche",
        "btn_fwd": "📨 Inoltro: {state}",
        "btn_away": "✍️ Messaggio assenza",
        "btn_prompt": "🧠 Personalità AI",
        "btn_kb": "📚 Info attività",
        "btn_sched": "🕐 Orari AI",
        "btn_resume_all": "▶️ Riattiva ovunque",
        "btn_reset": "🗑 Cancella memoria",
        "btn_promo": "📢 Invia invito al canale",
        "btn_defaults": "♻️ Ripristina default",
        "btn_back": "⬅️ Torna al menu",
        "btn_cancel": "❌ Annulla",
        "btn_edit": "✏️ Modifica",
        "btn_clear": "🗑 Svuota",
        "btn_set_hours": "✏️ Imposta fascia",
        "btn_always": "♾ Sempre attivo",
        "btn_yes_clear": "✅ Sì, cancella",
        "btn_yes_restore": "✅ Sì, ripristina",
        "btn_resume_here": "▶️ Riattiva il bot qui",

        "p_away": ("✍️ <b>Messaggio di assenza</b>\n\nScrivimi il nuovo testo che i "
                   "clienti riceveranno quando il bot è in modalità Assenza.\n\n"
                   "Attuale:\n<i>{cur}</i>"),
        "p_prompt": ("🧠 <b>Personalità dell'AI</b>\n\nScrivimi le nuove istruzioni: "
                     "come deve comportarsi e che tono usare.\n\n"
                     "⚠️ Cambiandola azzero la memoria delle conversazioni.\n\n"
                     "Attuale:\n<i>{cur}</i>"),
        "p_kb": ("📚 <b>Info sull'attività</b>\n\nScrivimi i fatti che l'AI deve "
                 "conoscere (orari, indirizzo, prezzi, FAQ…). Risponderà solo in base "
                 "a questi, senza inventare.\n\nAttuale:\n<i>{cur}</i>"),
        "p_sched": ("🕐 <b>Orari AI</b> (modalità Automatico)\n\nScrivimi la fascia "
                    "oraria nel formato <code>09:00-19:00</code>.\n\nAttuale: <b>{cur}</b>"),
        "p_promo": ("📢 <b>Invia invito al canale</b>\n\nScrivimi il <code>chat_id</code> "
                    "del cliente a cui mandare l'invito.\n\nLo trovi nelle notifiche "
                    "“{notice_name}”."),
        "empty_paren": "(vuota)",

        "ans_mode": "Modalità: {label}",
        "ans_fwd_on": "Inoltro attivato",
        "ans_fwd_off": "Inoltro disattivato",
        "stats": ("📊 <b>Statistiche</b>\n\n"
                  "🤖 Risposte AI: <b>{ai}</b>\n"
                  "💤 Risposte assenza: <b>{away}</b>\n"
                  "📨 Messaggi inoltrati: <b>{fwd}</b>\n"
                  "↩️ Risposte tue inoltrate: <b>{rel}</b>\n"
                  "📢 Canale proposto: <b>{promo}</b> volte\n"
                  "⏸️ Ignorati (pausa): <b>{paused}</b>\n"
                  "⏭️ Saltati: <b>{skipped}</b>\n\n"
                  "Chat in pausa adesso: <b>{paused_now}</b>\n"
                  "Connessione: <b>{conn}</b>"),
        "conn_active": "attiva",
        "conn_missing": "assente",
        "kb_view": "📚 <b>Info sull'attività</b>\n\n{body}",
        "kb_empty_i": "<i>(vuota)</i>",
        "ans_kb_cleared": "Info svuotate",
        "sched_view": ("🕐 <b>Orari AI</b> (modalità Automatico)\n\nAttuale: <b>{cur}</b>\n\n"
                       "Fuori da questa fascia il bot manda il messaggio di assenza."),
        "ans_sched_off": "AI sempre attiva in Automatico",
        "ans_resumed": "Bot riattivato su {n} chat",
        "confirm_reset": ("🗑 <b>Cancellare la memoria delle conversazioni?</b>\n\n"
                          "Il bot dimenticherà i messaggi precedenti di tutti i clienti. "
                          "Impostazioni e statistiche restano."),
        "ans_reset": "Memoria cancellata",
        "confirm_defaults": ("♻️ <b>Ripristinare i valori di default?</b>\n\n"
                             "Messaggio di assenza e personalità dell'AI tornano come "
                             "all'inizio, e la memoria viene azzerata. Le info "
                             "sull'attività restano."),
        "ans_defaults": "Default ripristinati",

        "ok_away": "✅ Messaggio di assenza aggiornato.",
        "ok_prompt": "✅ Personalità aggiornata (memoria azzerata).",
        "ok_kb": "✅ Info aggiornate ({n} caratteri). L'AI le userà dal prossimo messaggio.",
        "ok_kb_cleared": "✅ Info sull'attività svuotate.",
        "ok_hours": "✅ Orari AI: {start}–{end}",
        "ok_mode": "✅ Modalità: {label}",
        "ok_fwd": "✅ Inoltro messaggi: {state}",
        "ok_defaults": "✅ Valori di default ripristinati.",
        "bad_hours": "⚠️ Formato non valido. Scrivi ad esempio 09:00-19:00",
        "bad_chat_id": "⚠️ Serve un chat_id numerico. Riprova.",
        "promo_off": "⚠️ Canale non configurato (PROMO_CHANNEL_URL è vuoto).",
        "promo_sent": "✅ Invito al canale inviato alla chat {chat_id}",
        "promo_usage": ("Uso: /promo <chat_id>, oppure fai reply a una notifica "
                        "“{notice_name}” con /promo."),
        "pause_usage": ("Uso: /pause <chat_id>\n"
                        "Il chat_id lo trovi nelle notifiche “{notice_name}”."),
        "send_failed": "⚠️ Invio fallito. Riprova.",

        "relayed": "✅ Inviato al cliente. Il bot resta in pausa su questa chat.",
        "relay_failed": "⚠️ Invio al cliente fallito. Riprova.",
        "reply_unknown": ("Non trovo la conversazione collegata a quel messaggio. "
                          "Fai reply direttamente sulla notifica “{notice_name}”."),
        "welcome": ("👋 Ciao! Sono il tuo <b>Segretario</b>: rispondo io ai messaggi "
                    "Telegram quando non ci sei.\n\n"
                    "💡 Per rispondere a un cliente, fai <b>reply</b> alla notifica "
                    "“{notice_name}”: il tuo testo gli arriva direttamente.\n\n"
                    "Riapri questo pannello quando vuoi con /menu."),

        "cmd_menu": "🎛 Pannello di controllo",
        "cmd_start": "▶️ Avvia il bot",
    },
}

SUPPORTED = tuple(STRINGS)
LANG = UI_LANGUAGE if UI_LANGUAGE in STRINGS else "en"


def t(key: str, **kwargs) -> str:
    """The text for `key` in the configured UI language (English fallback).
    `{notice_name}` is always available, so any text can name the notice."""
    text = STRINGS[LANG].get(key) or STRINGS["en"][key]
    kwargs.setdefault("notice_name", STRINGS[LANG].get("notice_name")
                      or STRINGS["en"]["notice_name"])
    return text.format(**kwargs)
