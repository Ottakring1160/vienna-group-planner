from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🇦🇹 *Vienna Group Planner — Commands*\n\n"

        "*📌 Add & Browse*\n"
        "/add — Add a restaurant, exhibition, event, or activity\n"
        "/list — Browse all items (or `/list restaurants`, `/list events`...)\n"
        "/search `<query>` — Search by name, cuisine, tag, or district\n"
        "/info `<id>` — Show details for an item\n\n"

        "*🚩 Interest & Discovery*\n"
        "/flag `<id>` — Flag interest in something\n"
        "/trending — See most popular items\n"
        "/expiring — Exhibitions/events ending soon\n\n"

        "*📅 Plan an Outing*\n"
        "/dinner `<date> [time] [title]` — Create a new event\n"
        "/poll — Start a restaurant vote for an event\n"
        "/status — Show all active events\n\n"

        "*🔖 Reservations*\n"
        "/reserved `<event_id> <time> [details]` — Confirm a reservation\n\n"

        "*💡 Tips*\n"
        "• Use item IDs (shown as #123) to flag or reference items\n"
        "• Tag items with whatever you want — #rooftop #datenight #vegan\n"
        "• Exhibitions/events with end dates will show in /expiring\n"
        "• The bot sends reminders 24h and 2h before events\n"
        "• When enough people flag something, the bot will suggest planning it!\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
