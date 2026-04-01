from datetime import datetime, timedelta
from telegram.ext import ContextTypes
import database as db


async def weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    """Job callback: sends a weekly digest of what's hot and expiring."""
    chat_id = context.job.chat_id

    # Get trending items
    trending = await db.get_trending(limit=5)
    expiring = await db.get_expiring(days=7)
    active_events = await db.get_active_events()

    # Get recently added items (last 7 days)
    all_items = await db.get_items()
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    new_items = [i for i in all_items if i["created_at"] and i["created_at"] >= week_ago]

    sections = ["📬 *Weekly Vienna Planner Digest*\n"]

    # New additions
    if new_items:
        sections.append(f"*🆕 New This Week* ({len(new_items)} added)")
        for item in new_items[:5]:
            type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
            emoji = type_emoji.get(item["type"], "📌")
            sections.append(f"  {emoji} {item['name']} — added by {item['added_by_name']}")
        if len(new_items) > 5:
            sections.append(f"  _...and {len(new_items) - 5} more_")
        sections.append("")

    # Trending
    if trending:
        sections.append("*🔥 Most Wanted*")
        for i, item in enumerate(trending[:3]):
            medal = ["🥇", "🥈", "🥉"][i]
            sections.append(f"  {medal} {item['name']} — {item['flag_count']} interested")
        sections.append("")

    # Expiring soon
    if expiring:
        sections.append("*⏰ Expiring Soon*")
        for item in expiring[:5]:
            sections.append(f"  🖼 {item['name']} — ends {item['end_date']}")
        sections.append("")

    # Active plans
    if active_events:
        sections.append("*📅 Active Plans*")
        for event in active_events:
            avail = await db.get_availability(event["id"])
            yes_count = sum(1 for a in avail if a["status"] == "yes")
            sections.append(
                f"  📋 {event['title']} ({event['date']}) — "
                f"{yes_count} going, status: {event['status']}"
            )
        sections.append("")

    if len(sections) == 1:
        sections.append("Quiet week! Add some restaurants or events with /add 🙂")

    sections.append("_Use /trending, /expiring, or /list to explore!_")

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(sections),
        parse_mode="Markdown"
    )
