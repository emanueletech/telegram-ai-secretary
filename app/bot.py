import importlib.util
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import BotCommand
from telegram.ext import (Application, BusinessConnectionHandler,
                          CallbackQueryHandler, CommandHandler,
                          MessageHandler, filters)

import handlers
from config import BOT_TOKEN, HEALTH_FILE, LOG_DIR
from i18n import t


def setup_logging() -> None:
    fmt = "%(asctime)s %(levelname)s %(name)s — %(message)s"
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # stdout first: this is what `docker logs` shows, so it must always work.
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(fmt))
    root.addHandler(sh)
    # The rotating file is a convenience. If data/logs isn't writable, warn and
    # keep going on stdout — a log file must never be what kills the bot.
    try:
        fh = RotatingFileHandler(LOG_DIR / "bot.log", maxBytes=2_000_000, backupCount=5)
        fh.setFormatter(logging.Formatter(fmt))
        root.addHandler(fh)
    except OSError as e:
        root.warning("file logging disabled (%s) — stdout only", e)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def heartbeat(context) -> None:
    HEALTH_FILE.write_text(str(int(time.time())))


async def post_init(app: Application) -> None:
    """Register the command menu so the owner gets autocomplete in the bot DM.
    Best effort: a failure here must not stop the bot."""
    try:
        # The button panel (/menu) covers everything: keep the list short.
        # The slash commands still work, they just aren't advertised.
        await app.bot.set_my_commands([
            BotCommand("menu", t("cmd_menu")),
            BotCommand("start", t("cmd_start")),
        ])
    except Exception:
        logging.getLogger(__name__).warning("set_my_commands failed", exc_info=True)


def load_extensions(app: Application) -> None:
    """Load every app/extensions/*.py (not starting with "_" or ".") and call its
    register(app). This is how a deployment adds its own handlers without
    forking the code: drop a module in that folder before building the image.
    A broken extension is logged and skipped — it must never stop the bot."""
    log = logging.getLogger(__name__)
    ext_dir = Path(__file__).parent / "extensions"
    for path in sorted(ext_dir.glob("*.py")):
        if path.name.startswith(("_", ".")):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"extensions.{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if register is None:
                log.warning("extension %s has no register(app) — skipped", path.name)
                continue
            register(app)
            log.info("extension loaded: %s", path.name)
        except Exception:
            log.exception("extension %s failed to load — skipped", path.name)


def main() -> None:
    setup_logging()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # business updates
    app.add_handler(BusinessConnectionHandler(handlers.on_business_connection))
    app.add_handler(MessageHandler(filters.UpdateType.BUSINESS_MESSAGE,
                                   handlers.on_business_message))

    # Optional extensions (app/extensions/*.py) go first: within a handler group
    # the first matching handler wins, so an extension can claim e.g.
    # "/start <payload>" before the owner's /start below.
    load_extensions(app)

    # pannello di controllo del titolare (bottoni inline)
    app.add_handler(CallbackQueryHandler(handlers.on_menu_callback, pattern="^m:"))

    # owner commands (DM al bot)
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_start))
    # button panel — the main entry point (Italian aliases kept for habit)
    app.add_handler(CommandHandler(["menu", "impostazioni", "pannello"],
                                   handlers.cmd_menu))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("mode", handlers.cmd_mode))
    app.add_handler(CommandHandler("away", handlers.cmd_away))
    app.add_handler(CommandHandler("prompt", handlers.cmd_prompt))
    app.add_handler(CommandHandler("kb", handlers.cmd_kb))
    app.add_handler(CommandHandler("faq", handlers.cmd_kb))
    app.add_handler(CommandHandler("schedule", handlers.cmd_schedule))
    app.add_handler(CommandHandler("forward", handlers.cmd_forward))
    app.add_handler(CommandHandler("pause", handlers.cmd_pause))
    app.add_handler(CommandHandler("promo", handlers.cmd_promo))
    app.add_handler(CommandHandler("resume", handlers.cmd_resume))
    app.add_handler(CommandHandler("reset_history", handlers.cmd_reset_history))
    app.add_handler(CommandHandler("defaults", handlers.cmd_defaults))

    # owner replies in the bot DM (reply to a forwarded notice → relay to customer)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
        handlers.on_owner_dm,
    ))

    app.job_queue.run_repeating(heartbeat, interval=60, first=5)

    logging.info("Starting polling…")
    # NB: Telegram delivers ONLY the update types listed here. Any new handler
    # that needs a type not in this list would silently never fire —
    # "callback_query" powers every inline button (control panel, promo, extensions).
    app.run_polling(allowed_updates=[
        "message", "edited_message", "callback_query", "business_connection",
        "business_message", "edited_business_message", "deleted_business_messages",
    ])


if __name__ == "__main__":
    main()
