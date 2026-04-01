from telegram import Update
from telegram.ext import ContextTypes
import database as db


async def reserve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/reserved <event_id> <time> [details]`\n"
            "Example: `/reserved 1 19:30 Table for 8, confirmation #A1234`",
            parse_mode="Markdown"
        )
        return

    try:
        event_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("First argument must be the event ID number.")
        return

    event = await db.get_event(event_id)
    if not event:
        await update.message.reply_text(f"Event #{event_id} not found.")
        return

    time_str = context.args[1]
    details = " ".join(context.args[2:]) if len(context.args) > 2 else None

    # Get the chosen restaurant name
    restaurant_name = "TBD"
    if event["chosen_item_id"]:
        item = await db.get_item(event["chosen_item_id"])
        if item:
            restaurant_name = item["name"]

    # Count available people
    avail = await db.get_availability(event_id)
    party_size = sum(1 for a in avail if a["status"] == "yes")

    # Parse confirmation number from details
    confirmation = None
    notes = details
    if details and "#" in details:
        parts = details.split("#", 1)
        confirmation = "#" + parts[1].split()[0] if parts[1] else None
        notes = parts[0].strip() if parts[0].strip() else None

    user = update.effective_user
    await db.add_reservation(
        event_id=event_id,
        restaurant_name=restaurant_name,
        time=time_str,
        party_size=party_size,
        confirmation=confirmation,
        notes=notes,
        reserved_by_id=user.id,
        reserved_by_name=user.first_name
    )

    await db.update_event_status(event_id, "decided")

    text = (
        f"🔖 *Reservation Confirmed!*\n\n"
        f"📅 *{event['title']}*\n"
        f"📍 {restaurant_name}\n"
        f"🕐 {event['date']} at {time_str}\n"
        f"👥 Party of {party_size}\n"
    )
    if confirmation:
        text += f"✅ Confirmation: {confirmation}\n"
    if notes:
        text += f"📝 Notes: {notes}\n"
    text += f"\n_Reserved by {user.first_name}_"

    # Send and pin the message
    msg = await update.message.reply_text(text, parse_mode="Markdown")

    try:
        await msg.pin()
    except Exception:
        pass  # Bot may not have pin permissions
