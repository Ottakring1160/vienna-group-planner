from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from config import CUISINES, PRICE_RANGES, VIENNA_DISTRICTS, ACTIVITY_CATEGORIES
import database as db

# Conversation states
(SELECT_TYPE, NAME, CUISINE, PRICE, DISTRICT, ADDRESS, LINK,
 CATEGORY, START_DATE, END_DATE, TICKET_LINK, TAGS, CONFIRM) = range(13)


def _type_keyboard():
    buttons = [
        [InlineKeyboardButton("🍽 Restaurant", callback_data="type_restaurant")],
        [InlineKeyboardButton("🖼 Exhibition", callback_data="type_exhibition")],
        [InlineKeyboardButton("🎉 Event", callback_data="type_event")],
        [InlineKeyboardButton("🎯 Activity", callback_data="type_activity")],
    ]
    return InlineKeyboardMarkup(buttons)


def _cuisine_keyboard():
    buttons = []
    row = []
    for i, c in enumerate(CUISINES):
        row.append(InlineKeyboardButton(c, callback_data=f"cuisine_{c}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _price_keyboard():
    buttons = [[InlineKeyboardButton(p, callback_data=f"price_{p}") for p in PRICE_RANGES]]
    return InlineKeyboardMarkup(buttons)


def _district_keyboard():
    buttons = []
    row = []
    for d in VIENNA_DISTRICTS:
        row.append(InlineKeyboardButton(d, callback_data=f"district_{d}"))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


def _category_keyboard():
    buttons = []
    row = []
    for c in ACTIVITY_CATEGORIES:
        row.append(InlineKeyboardButton(c, callback_data=f"cat_{c}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_item"] = {}
    await update.message.reply_text(
        "What would you like to add?",
        reply_markup=_type_keyboard()
    )
    return SELECT_TYPE


async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_type = query.data.replace("type_", "")
    context.user_data["add_item"]["type"] = item_type

    type_labels = {
        "restaurant": "restaurant",
        "exhibition": "exhibition",
        "event": "event",
        "activity": "activity"
    }
    label = type_labels[item_type]
    await query.edit_message_text(f"Got it! What's the name of the {label}?")
    return NAME


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["add_item"]["name"] = update.message.text
    item_type = context.user_data["add_item"]["type"]

    if item_type == "restaurant":
        await update.message.reply_text(
            "What cuisine?", reply_markup=_cuisine_keyboard()
        )
        return CUISINE
    elif item_type in ("exhibition", "event", "activity"):
        await update.message.reply_text(
            "Pick a category:", reply_markup=_category_keyboard()
        )
        return CATEGORY


async def select_cuisine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_item"]["cuisine"] = query.data.replace("cuisine_", "")
    await query.edit_message_text(
        "Price range?", reply_markup=_price_keyboard()
    )
    return PRICE


async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_item"]["category"] = query.data.replace("cat_", "")

    item_type = context.user_data["add_item"]["type"]
    if item_type in ("exhibition", "event"):
        await query.edit_message_text(
            "When does it start? (YYYY-MM-DD format, or type 'skip')"
        )
        return START_DATE
    else:
        await query.edit_message_text(
            "Which district?", reply_markup=_district_keyboard()
        )
        return DISTRICT


async def select_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_item"]["price_range"] = query.data.replace("price_", "")
    await query.edit_message_text(
        "Which district?", reply_markup=_district_keyboard()
    )
    return DISTRICT


async def select_district(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["add_item"]["district"] = query.data.replace("district_", "")
    await query.edit_message_text(
        "Drop a Google Maps link or address (or type 'skip'):"
    )
    return ADDRESS


async def enter_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        if "google.com/maps" in text or "goo.gl" in text or "maps.app" in text:
            context.user_data["add_item"]["maps_link"] = text
        else:
            context.user_data["add_item"]["address"] = text

    item_type = context.user_data["add_item"]["type"]
    if item_type == "restaurant":
        await update.message.reply_text(
            "Any website or booking link? (or type 'skip')"
        )
        return LINK
    elif item_type in ("exhibition", "event"):
        await update.message.reply_text(
            "Ticket link or website? (or type 'skip')"
        )
        return TICKET_LINK
    else:
        await update.message.reply_text(
            "Add any tags separated by commas (e.g. rooftop, datenight, vegan)\n"
            "Or type 'skip':"
        )
        return TAGS


async def enter_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        context.user_data["add_item"]["start_date"] = text

    await update.message.reply_text(
        "When does it end? (YYYY-MM-DD format, or type 'skip')"
    )
    return END_DATE


async def enter_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        context.user_data["add_item"]["end_date"] = text

    await update.message.reply_text(
        "Which district?", reply_markup=_district_keyboard()
    )
    return DISTRICT


async def enter_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        context.user_data["add_item"]["website"] = text

    await update.message.reply_text(
        "Add any tags separated by commas (e.g. rooftop, datenight, vegan)\n"
        "Or type 'skip':"
    )
    return TAGS


async def enter_ticket_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        context.user_data["add_item"]["ticket_link"] = text

    await update.message.reply_text(
        "Add any tags separated by commas (e.g. rooftop, datenight, vegan)\n"
        "Or type 'skip':"
    )
    return TAGS


async def enter_tags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.lower() != "skip":
        tags = ", ".join(t.strip().lstrip("#") for t in text.split(","))
        context.user_data["add_item"]["tags"] = tags

    item = context.user_data["add_item"]
    summary = _format_item_summary(item)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Save", callback_data="confirm_save"),
         InlineKeyboardButton("Cancel", callback_data="confirm_cancel")]
    ])

    await update.message.reply_text(
        f"Here's what I've got:\n\n{summary}\n\nSave this?",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )
    return CONFIRM


def _format_item_summary(item):
    lines = []
    type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
    emoji = type_emoji.get(item["type"], "📌")
    lines.append(f"{emoji} *{item['name']}* ({item['type'].title()})")

    if item.get("cuisine"):
        lines.append(f"Cuisine: {item['cuisine']}")
    if item.get("category"):
        lines.append(f"Category: {item['category']}")
    if item.get("price_range"):
        lines.append(f"Price: {item['price_range']}")
    if item.get("district"):
        lines.append(f"District: {item['district']}")
    if item.get("address"):
        lines.append(f"Address: {item['address']}")
    if item.get("maps_link"):
        lines.append(f"Maps: {item['maps_link']}")
    if item.get("website"):
        lines.append(f"Website: {item['website']}")
    if item.get("ticket_link"):
        lines.append(f"Tickets: {item['ticket_link']}")
    if item.get("start_date"):
        dates = item["start_date"]
        if item.get("end_date"):
            dates += f" to {item['end_date']}"
        lines.append(f"Dates: {dates}")
    if item.get("tags"):
        lines.append(f"Tags: #{item['tags'].replace(', ', ' #')}")

    return "\n".join(lines)


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_cancel":
        context.user_data.pop("add_item", None)
        await query.edit_message_text("Cancelled! Nothing was saved.")
        return ConversationHandler.END

    item = context.user_data.pop("add_item")
    user = query.from_user

    item_id = await db.add_item(
        item_type=item["type"],
        name=item["name"],
        added_by_id=user.id,
        added_by_name=user.first_name,
        cuisine=item.get("cuisine"),
        price_range=item.get("price_range"),
        district=item.get("district"),
        address=item.get("address"),
        maps_link=item.get("maps_link"),
        website=item.get("website"),
        ticket_link=item.get("ticket_link"),
        category=item.get("category"),
        start_date=item.get("start_date"),
        end_date=item.get("end_date"),
        tags=item.get("tags"),
    )

    type_emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}
    emoji = type_emoji.get(item["type"], "📌")

    await query.edit_message_text(
        f"{emoji} *{item['name']}* has been added! (ID: {item_id})\n\n"
        f"Use /flag {item_id} to express interest!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("add_item", None)
    await update.message.reply_text("Adding cancelled.")
    return ConversationHandler.END


def get_add_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            SELECT_TYPE: [CallbackQueryHandler(select_type, pattern=r"^type_")],
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            CUISINE: [CallbackQueryHandler(select_cuisine, pattern=r"^cuisine_")],
            CATEGORY: [CallbackQueryHandler(select_category, pattern=r"^cat_")],
            PRICE: [CallbackQueryHandler(select_price, pattern=r"^price_")],
            DISTRICT: [CallbackQueryHandler(select_district, pattern=r"^district_")],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_address)],
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_link)],
            START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_start_date)],
            END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_end_date)],
            TICKET_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_ticket_link)],
            TAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_tags)],
            CONFIRM: [CallbackQueryHandler(confirm, pattern=r"^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
        per_chat=True,
    )
