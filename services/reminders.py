from datetime import datetime, timedelta
from telegram.ext import ContextTypes
import database as db
from config import REMINDER_HOURS


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Job callback: runs every 30 minutes to check for upcoming events."""
    events = await db.get_active_events()
    now = datetime.now()

    for event in events:
        try:
            event_dt = datetime.strptime(f"{event['date']} {event['time']}", "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            continue

        hours_until = (event_dt - now).total_seconds() / 3600

        for reminder_h in REMINDER_HOURS:
            # Send reminder if we're within 30 min of the reminder time
            if reminder_h - 0.5 <= hours_until <= reminder_h + 0.5:
                avail = await db.get_availability(event["id"])
                yes_names = [a["user_name"] for a in avail if a["status"] == "yes"]
                maybe_names = [a["user_name"] for a in avail if a["status"] == "maybe"]

                reservation = await db.get_reservation(event["id"])
                res_text = ""
                if reservation:
                    res_text = (
                        f"\n📍 {reservation['restaurant_name']}"
                        f"\n🕐 {reservation['time']}"
                    )
                    if reservation["confirmation"]:
                        res_text += f"\n✅ {reservation['confirmation']}"

                time_label = f"{reminder_h}h" if reminder_h >= 1 else f"{int(reminder_h * 60)}min"
                text = (
                    f"⏰ *Reminder: {event['title']}*\n"
                    f"📅 {event['date']} at {event['time']} — in ~{time_label}!\n"
                    f"{res_text}\n\n"
                    f"✅ Going ({len(yes_names)}): {', '.join(yes_names) or 'nobody yet!'}\n"
                    f"🤔 Maybe ({len(maybe_names)}): {', '.join(maybe_names) or 'none'}"
                )

                # Send to the chat where the event was created
                chat_id = context.job.chat_id
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )


async def archive_old_items(context: ContextTypes.DEFAULT_TYPE):
    """Job callback: runs daily to archive expired exhibitions/events."""
    await db.archive_expired_items()
