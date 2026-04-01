import logging
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler
)
from config import BOT_TOKEN, DIGEST_DAY, DIGEST_HOUR
from database import init_db
from handlers.add import get_add_handler
from handlers.list_browse import list_items, search_items, show_item, list_page_callback
from handlers.events import create_dinner, availability_callback, event_status
from handlers.poll import get_poll_handler, vote_callback, close_poll_callback
from handlers.flag import flag_item, flag_inline_callback, rate_callback, trending, expiring
from handlers.reservation import reserve
from handlers.help import help_command
from services.reminders import check_reminders, archive_old_items
from services.digest import weekly_digest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def post_init(application):
    """Initialize database and set up scheduled jobs."""
    await init_db()
    logger.info("Database initialized.")


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # --- Conversation handlers (must be added first) ---
    app.add_handler(get_add_handler())
    app.add_handler(get_poll_handler())

    # --- Simple command handlers ---
    app.add_handler(CommandHandler("start", help_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_items))
    app.add_handler(CommandHandler("search", search_items))
    app.add_handler(CommandHandler("info", show_item))
    app.add_handler(CommandHandler("dinner", create_dinner))
    app.add_handler(CommandHandler("status", event_status))
    app.add_handler(CommandHandler("flag", flag_item))
    app.add_handler(CommandHandler("trending", trending))
    app.add_handler(CommandHandler("expiring", expiring))
    app.add_handler(CommandHandler("reserved", reserve))

    # --- Callback query handlers ---
    app.add_handler(CallbackQueryHandler(availability_callback, pattern=r"^avail_"))
    app.add_handler(CallbackQueryHandler(vote_callback, pattern=r"^vote_"))
    app.add_handler(CallbackQueryHandler(close_poll_callback, pattern=r"^closepoll_"))
    app.add_handler(CallbackQueryHandler(flag_inline_callback, pattern=r"^flag_\d+$"))
    app.add_handler(CallbackQueryHandler(rate_callback, pattern=r"^rate_"))
    app.add_handler(CallbackQueryHandler(list_page_callback, pattern=r"^list_"))

    # --- Scheduled jobs ---
    job_queue = app.job_queue

    # Check for reminders every 30 minutes
    job_queue.run_repeating(check_reminders, interval=1800, first=60)

    # Archive expired items daily at 3 AM
    job_queue.run_daily(archive_old_items, time=__import__("datetime").time(3, 0))

    # Weekly digest (Monday at configured hour)
    job_queue.run_daily(
        weekly_digest,
        time=__import__("datetime").time(DIGEST_HOUR, 0),
        days=(DIGEST_DAY,)
    )

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
