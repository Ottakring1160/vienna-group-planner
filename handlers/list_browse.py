from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db


def _format_item_card(item):
    type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
    emoji = type_emoji.get(item["type"], "📌")

    lines = [f"{emoji} *{item['name']}* (#{item['id']})"]

    details = []
    if item["cuisine"]:
        details.append(item["cuisine"])
    if item["category"]:
        details.append(item["category"])
    if item["price_range"]:
        details.append(item["price_range"])
    if item["district"]:
        details.append(f"District {item['district']}")
    if details:
        lines.append(" | ".join(details))

    if item["start_date"]:
        date_str = item["start_date"]
        if item["end_date"]:
            date_str += f" → {item['end_date']}"
        lines.append(f"📅 {date_str}")

    if item["tags"]:
        lines.append(f"🏷 #{item['tags'].replace(', ', ' #')}")

    if item["maps_link"]:
        lines.append(f"📍 [Maps]({item['maps_link']})")
    elif item["address"]:
        lines.append(f"📍 {item['address']}")

    if item["website"]:
        lines.append(f"🔗 [Website]({item['website']})")
    if item["ticket_link"]:
        lines.append(f"🎫 [Tickets]({item['ticket_link']})")

    lines.append(f"_Added by {item['added_by_name']}_")
    return "\n".join(lines)


async def list_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    item_type = None
    if args:
        type_map = {
            "restaurants": "restaurant", "restaurant": "restaurant",
            "exhibitions": "exhibition", "exhibition": "exhibition",
            "events": "event", "event": "event",
            "activities": "activity", "activity": "activity",
        }
        item_type = type_map.get(args[0].lower())

    items = await db.get_items(item_type=item_type)

    if not items:
        type_label = item_type + "s" if item_type else "items"
        await update.message.reply_text(f"No {type_label} found yet. Use /add to add some!")
        return

    type_label = item_type + "s" if item_type else "items"
    header = f"📋 *All {type_label.title()}* ({len(items)} total)\n\n"

    # Paginate: show 5 at a time
    page = 0
    page_size = 5
    total_pages = (len(items) - 1) // page_size + 1
    page_items = items[page * page_size:(page + 1) * page_size]

    cards = [_format_item_card(item) for item in page_items]
    text = header + "\n\n".join(cards)

    if total_pages > 1:
        text += f"\n\n_Page {page + 1}/{total_pages}_"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Next →", callback_data=f"list_{item_type or 'all'}_{page + 1}")
        ]])
        await update.message.reply_text(text, parse_mode="Markdown",
                                        reply_markup=keyboard,
                                        disable_web_page_preview=True)
    else:
        await update.message.reply_text(text, parse_mode="Markdown",
                                        disable_web_page_preview=True)


async def list_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    # list_{type}_{page}
    item_type = parts[1] if parts[1] != "all" else None
    page = int(parts[2])
    page_size = 5

    items = await db.get_items(item_type=item_type)
    total_pages = (len(items) - 1) // page_size + 1
    page_items = items[page * page_size:(page + 1) * page_size]

    if not page_items:
        await query.edit_message_text("No more items.")
        return

    type_label = (item_type + "s") if item_type else "items"
    header = f"📋 *All {type_label.title()}* ({len(items)} total)\n\n"
    cards = [_format_item_card(item) for item in page_items]
    text = header + "\n\n".join(cards)
    text += f"\n\n_Page {page + 1}/{total_pages}_"

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("← Prev",
                       callback_data=f"list_{item_type or 'all'}_{page - 1}"))
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Next →",
                       callback_data=f"list_{item_type or 'all'}_{page + 1}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=keyboard,
                                  disable_web_page_preview=True)


async def search_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: `/search <query>`\n"
            "Examples:\n"
            "  `/search italian`\n"
            "  `/search rooftop`\n"
            "  `/search 7.`",
            parse_mode="Markdown"
        )
        return

    query_text = " ".join(context.args)
    items = await db.get_items(search=query_text)

    if not items:
        await update.message.reply_text(f"No results for '{query_text}'. Try a different search term.")
        return

    header = f"🔍 *Results for '{query_text}'* ({len(items)} found)\n\n"
    cards = [_format_item_card(item) for item in items[:10]]
    text = header + "\n\n".join(cards)

    if len(items) > 10:
        text += f"\n\n_Showing first 10 of {len(items)} results._"

    await update.message.reply_text(text, parse_mode="Markdown",
                                    disable_web_page_preview=True)


async def show_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/info <id>`", parse_mode="Markdown")
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

    card = _format_item_card(item)
    flag_count = await db.get_flag_count(item_id)
    avg_rating = await db.get_avg_rating(item_id)

    extra = f"\n\n🚩 {flag_count} interested"
    if avg_rating:
        stars = "⭐" * round(avg_rating)
        extra += f" | {stars} ({avg_rating}/5)"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚩 Flag Interest", callback_data=f"flag_{item_id}"),
         InlineKeyboardButton("⭐ Rate", callback_data=f"rate_{item_id}")]
    ])

    await update.message.reply_text(
        card + extra, parse_mode="Markdown",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
