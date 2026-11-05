"""Example extension — copy it to a name that doesn't start with "_" to enable.

bot.py imports every app/extensions/*.py (except "_*" files) at startup and
calls register(app) before wiring the built-in handlers. Within a handler
group the first match wins, so this /start handler with a payload filter is
reached before the owner's own /start.

Read your settings straight from os.environ (put non-secret ones in an overlay
personal.env, secrets in the target's .env).
"""
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters

GREETING = os.environ.get("EXAMPLE_GREETING", "Hello from an extension! 👋")


async def _hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(GREETING)


def register(app: Application) -> None:
    # Answers "/start hello" (e.g. from a t.me/<bot>?start=hello deep link)
    # for ANY user; a plain /start still reaches the owner's control panel.
    app.add_handler(CommandHandler(
        "start", _hello, filters=filters.Regex(r"^/start(@\w+)?\s+hello\b")))
