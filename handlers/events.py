from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
import database as db
from config import DEFAULT_QUORUM


async def create_dinner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 1:
        await update.message.reply_text(
            "Usage: `/dinner <date> [time] [title]`\n"
            "Examples:\n"
            "  `/dinner 2026-04-05 19:00 Friday dinner`\n"
            "  `/dinner tomorrow 20:00`\n"
            "  `/dinner Saturday`",
            parse_mode="Markdown"
        )
        return

    date_str = context.args[0]
    time_str = context.args[1] if len(context.args) > 1 and ":" in context.args[1] else None
    title_start = 2 if time_str else 1
    title = " ".join(context.args[title_start:]) if len(context.args) > title_start else None

    if not title:
        title = f"Dinner on {date_str}"

    user = update.effective_user
    event_id = await db.create_event(
        title=title,
        date=date_str,
        time=time_str or "TBD",
        created_by_id=user.id,
        created_by_name=user.first_name,
        quorum=DEFAULT_QUORUM
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ I'm in!", callback_data=f"avail_{event_id}_yes"),
            InlineKeyboardButton("🤔 Maybe", callback_data=f"avail_{event_id}_maybe"),
            InlineKeyboardButton("❌ Can't", callback_data=f"avail_{event_id}_no"),
        ]
    ])

    time_display = time_str or "TBD"
    await update.message.reply_text(
        f"📅 *New Event: {title}*\n"
        f"Date: {date_str}\n"
        f"Time: {time_display}\n"
        f"Organized by: {user.first_name}\n\n"
        f"Who's in? Click below!",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def availability_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    event_id = int(parts[1])
    status = parts[2]

    user = query.from_user
    await db.set_availability(event_id, user.id, user.first_name, status)

    # Get updated availability
    avail = await db.get_availability(event_id)
    event = await db.get_event(event_id)

    yes_list = [a["user_name"] for a in avail if a["status"] == "yes"]
    maybe_list = [a["user_name"] for a in avail if a["status"] == "maybe"]
    no_list = [a["user_name"] for a in avail if a["status"] == "no"]

    status_text = (
        f"📅 *{event['title']}*\n"
        f"Date: {event['date']} at {event['time']}\n\n"
        f"✅ In ({len(yes_list)}): {', '.join(yes_list) or 'none yet'}\n"
        f"🤔 Maybe ({len(maybe_list)}): {', '.join(maybe_list) or 'none'}\n"
        f"❌ Can't ({len(no_list)}): {', '.join(no_list) or 'none'}\n\n"
        f"_{user.first_name} marked {status}_"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ I'm in!", callback_data=f"avail_{event_id}_yes"),
            InlineKeyboardButton("🤔 Maybe", callback_data=f"avail_{event_id}_maybe"),
            InlineKeyboardButton("❌ Can't", callback_data=f"avail_{event_id}_no"),
        ]
    ])

    await query.edit_message_text(status_text, parse_mode="Markdown", reply_markup=keyboard)


async def event_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = await db.get_active_events()

    if not events:
        await update.message.reply_text("No active events. Create one with /dinner!")
        return

    texts = []
    for event in events:
        avail = await db.get_availability(event["id"])
        yes_count = sum(1 for a in avail if a["status"] == "yes")
        maybe_count = sum(1 for a in avail if a["status"] == "maybe")

        status_emoji = {"planning": "📋", "polling": "🗳", "decided": "✅"}
        emoji = status_emoji.get(event["status"], "📌")

        text = (
            f"{emoji} *{event['title']}* (#{event['id']})\n"
            f"📅 {event['date']} at {event['time']}\n"
            f"Status: {event['status'].title()}\n"
            f"Responses: ✅{yes_count} 🤔{maybe_count}\n"
            f"Organized by: {event['created_by_name']}"
        )

        # Check for reservation
        reservation = await db.get_reservation(event["id"])
        if reservation:
            text += (
                f"\n\n🔖 *Reservation:*\n"
                f"📍 {reservation['restaurant_name']}\n"
                f"🕐 {reservation['time']}"
            )
            if reservation["confirmation"]:
                text += f"\n✅ Confirmation: {reservation['confirmation']}"

        texts.append(text)

    await update.message.reply_text(
        "📊 *Active Events*\n\n" + "\n\n---\n\n".join(texts),
        parse_mode="Markdown"
    )
