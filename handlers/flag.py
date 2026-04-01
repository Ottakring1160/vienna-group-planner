from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from config import FLAG_THRESHOLD


async def flag_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/flag <item_id>` — Flag interest in a restaurant/event\n"
            "Find IDs with /list or /search",
            parse_mode="Markdown"
        )
        return

    try:
        item_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Please provide a valid item ID number.")
        return

    item = await db.get_item(item_id)
    if not item:
        await update.message.reply_text(f"Item #{item_id} not found.")
        return

    user = update.effective_user
    await db.add_flag(item_id, user.id)
    count = await db.get_flag_count(item_id)

    type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
    emoji = type_emoji.get(item["type"], "📌")

    text = f"🚩 {user.first_name} is interested in {emoji} *{item['name']}*!\n"
    text += f"Total interest: {count} people"

    # Rate button
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⭐ Rate 1", callback_data=f"rate_{item_id}_1"),
        InlineKeyboardButton("⭐ 2", callback_data=f"rate_{item_id}_2"),
        InlineKeyboardButton("⭐ 3", callback_data=f"rate_{item_id}_3"),
        InlineKeyboardButton("⭐ 4", callback_data=f"rate_{item_id}_4"),
        InlineKeyboardButton("⭐ 5", callback_data=f"rate_{item_id}_5"),
    ]])

    if count >= FLAG_THRESHOLD:
        text += f"\n\n🔥 *{count} people interested!* Should we plan this? Use /dinner to set a date!"

    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def flag_inline_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle flag button from /info command."""
    query = update.callback_query
    await query.answer()

    item_id = int(query.data.replace("flag_", ""))
    user = query.from_user
    await db.add_flag(item_id, user.id)
    count = await db.get_flag_count(item_id)

    await query.answer(f"Flagged! {count} people interested.", show_alert=True)


async def rate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split("_")
    item_id = int(parts[1])
    rating = int(parts[2])

    user = query.from_user
    await db.add_flag(item_id, user.id, rating=rating)

    avg = await db.get_avg_rating(item_id)
    count = await db.get_flag_count(item_id)
    stars = "⭐" * rating

    await query.answer(f"Rated {stars}! Average: {avg}/5 ({count} people)", show_alert=True)


async def trending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    items = await db.get_trending(limit=10)

    if not items:
        await update.message.reply_text(
            "Nothing flagged yet! Use `/flag <id>` to express interest in items.",
            parse_mode="Markdown"
        )
        return

    lines = ["🔥 *Trending — Most Wanted*\n"]
    for i, item in enumerate(items):
        type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
        emoji = type_emoji.get(item["type"], "📌")
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."

        line = f"{medal} {emoji} *{item['name']}* — {item['flag_count']} interested"
        if item["avg_rating"]:
            line += f" | ⭐ {round(item['avg_rating'], 1)}/5"
        if item.get("district"):
            line += f" | {item['district']}"
        lines.append(line)

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def expiring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = 7
    if context.args:
        try:
            days = int(context.args[0])
        except ValueError:
            pass

    items = await db.get_expiring(days=days)

    if not items:
        await update.message.reply_text(
            f"No exhibitions/events expiring in the next {days} days."
        )
        return

    lines = [f"⏰ *Expiring Soon* (next {days} days)\n"]
    for item in items:
        type_emoji = {"exhibition": "🖼", "event": "🎉"}
        emoji = type_emoji.get(item["type"], "📌")

        line = f"{emoji} *{item['name']}* — ends {item['end_date']}"
        if item["flag_count"]:
            line += f" | 🚩 {item['flag_count']} interested"
        lines.append(line)

    lines.append("\n_Don't miss out! Use /dinner to plan a visit._")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
