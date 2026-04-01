from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import database as db
from config import DEFAULT_QUORUM

SELECT_EVENT, SELECT_OPTIONS, POLL_ACTIVE = range(3)


async def start_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    events = await db.get_active_events()
    planning_events = [e for e in events if e["status"] == "planning"]

    if not planning_events:
        await update.message.reply_text(
            "No events in planning phase. Create one with /dinner first!"
        )
        return ConversationHandler.END

    if len(planning_events) == 1:
        context.user_data["poll_event_id"] = planning_events[0]["id"]
        return await _show_restaurant_picker(update, context, planning_events[0]["id"])

    buttons = [
        [InlineKeyboardButton(
            f"{e['title']} ({e['date']})",
            callback_data=f"pollevt_{e['id']}"
        )]
        for e in planning_events
    ]
    await update.message.reply_text(
        "Which event should we vote on?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECT_EVENT


async def select_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    event_id = int(query.data.replace("pollevt_", ""))
    context.user_data["poll_event_id"] = event_id
    return await _show_restaurant_picker(update, context, event_id, edit=True)


async def _show_restaurant_picker(update, context, event_id, edit=False):
    items = await db.get_items(item_type="restaurant")
    if not items:
        text = "No restaurants in the database yet. Add some with /add first!"
        if edit:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return ConversationHandler.END

    context.user_data["poll_selected"] = []

    # Show top restaurants (by flags) as options
    trending = await db.get_trending(limit=10)
    if trending:
        display_items = trending
    else:
        display_items = items[:10]

    buttons = []
    for item in display_items:
        label = f"{item['name']}"
        if item.get("cuisine"):
            label += f" ({item['cuisine']})"
        if item.get("district"):
            label += f" - {item['district']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"pollopt_{item['id']}")])

    buttons.append([InlineKeyboardButton("✅ Done — Start Poll", callback_data="polldone")])

    text = (
        f"Pick restaurants for the poll (select 2-5):\n"
        f"_Selected so far: none_"
    )
    if edit:
        await update.callback_query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    else:
        await update.message.reply_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    return SELECT_OPTIONS


async def select_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "polldone":
        return await _launch_poll(update, context)

    item_id = int(query.data.replace("pollopt_", ""))
    selected = context.user_data.get("poll_selected", [])

    if item_id in selected:
        selected.remove(item_id)
    else:
        if len(selected) >= 5:
            await query.answer("Maximum 5 options! Remove one first.", show_alert=True)
            return SELECT_OPTIONS
        selected.append(item_id)

    context.user_data["poll_selected"] = selected

    # Get names of selected items
    names = []
    for sid in selected:
        item = await db.get_item(sid)
        if item:
            names.append(item["name"])

    selected_text = ", ".join(names) if names else "none"

    # Rebuild buttons
    items = await db.get_items(item_type="restaurant")
    trending = await db.get_trending(limit=10)
    display_items = trending if trending else items[:10]

    buttons = []
    for item in display_items:
        check = "✅ " if item["id"] in selected else ""
        label = f"{check}{item['name']}"
        if item.get("cuisine"):
            label += f" ({item['cuisine']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"pollopt_{item['id']}")])

    buttons.append([InlineKeyboardButton("✅ Done — Start Poll", callback_data="polldone")])

    await query.edit_message_text(
        f"Pick restaurants for the poll (select 2-5):\n"
        f"_Selected: {selected_text}_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return SELECT_OPTIONS


async def _launch_poll(update, context):
    query = update.callback_query
    selected = context.user_data.get("poll_selected", [])
    event_id = context.user_data["poll_event_id"]

    if len(selected) < 2:
        await query.answer("Select at least 2 options!", show_alert=True)
        return SELECT_OPTIONS

    # Create poll options in DB
    await db.update_event_status(event_id, "polling")
    for item_id in selected:
        await db.create_poll_option(event_id, item_id)

    event = await db.get_event(event_id)

    # Build vote buttons
    options = await db.get_poll_options(event_id)
    buttons = []
    for opt in options:
        label = f"{opt['name']}"
        if opt["cuisine"]:
            label += f" ({opt['cuisine']})"
        label += f" — 0 votes"
        buttons.append([InlineKeyboardButton(label, callback_data=f"vote_{event_id}_{opt['option_id']}")])

    buttons.append([InlineKeyboardButton("🔒 Close Poll", callback_data=f"closepoll_{event_id}")])

    await query.edit_message_text(
        f"🗳 *VOTE: {event['title']}*\n"
        f"📅 {event['date']} at {event['time']}\n\n"
        f"Pick your favorite! (Quorum: {event['quorum']} votes needed)\n"
        f"Votes: 0",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

    context.user_data.pop("poll_selected", None)
    context.user_data.pop("poll_event_id", None)
    return ConversationHandler.END


async def vote_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    event_id = int(parts[1])
    option_id = int(parts[2])

    user = query.from_user
    await db.cast_vote(event_id, user.id, user.first_name, option_id)

    # Refresh vote counts
    event = await db.get_event(event_id)
    options = await db.get_poll_options(event_id)
    total_votes = await db.get_vote_count(event_id)

    buttons = []
    for opt in options:
        bar = "█" * opt["vote_count"] + "░" * max(0, 5 - opt["vote_count"])
        label = f"{opt['name']} [{bar}] {opt['vote_count']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"vote_{event_id}_{opt['option_id']}")])

    buttons.append([InlineKeyboardButton("🔒 Close Poll", callback_data=f"closepoll_{event_id}")])

    quorum_text = ""
    if total_votes >= event["quorum"]:
        quorum_text = "\n✅ Quorum reached! Organizer can close the poll."

    await query.edit_message_text(
        f"🗳 *VOTE: {event['title']}*\n"
        f"📅 {event['date']} at {event['time']}\n\n"
        f"Votes: {total_votes}/{event['quorum']}{quorum_text}\n"
        f"_{user.first_name} voted!_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


async def close_poll_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    event_id = int(query.data.replace("closepoll_", ""))

    event = await db.get_event(event_id)
    if query.from_user.id != event["created_by_id"]:
        await query.answer("Only the organizer can close the poll!", show_alert=True)
        return

    await query.answer()

    options = await db.get_poll_options(event_id)
    if not options:
        await query.edit_message_text("No votes recorded.")
        return

    # Find winner
    winner = max(options, key=lambda o: o["vote_count"])
    await db.update_event_status(event_id, "decided", chosen_item_id=winner["item_id"])

    results = []
    for i, opt in enumerate(options):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
        bar = "█" * opt["vote_count"]
        results.append(f"{medal} {opt['name']} — {opt['vote_count']} votes {bar}")

    winner_item = await db.get_item(winner["item_id"])
    winner_extra = ""
    if winner_item.get("maps_link"):
        winner_extra = f"\n📍 [Google Maps]({winner_item['maps_link']})"
    elif winner_item.get("address"):
        winner_extra = f"\n📍 {winner_item['address']}"

    await query.edit_message_text(
        f"🏆 *Poll Results: {event['title']}*\n\n"
        + "\n".join(results) +
        f"\n\n🎉 *Winner: {winner['name']}!*{winner_extra}\n\n"
        f"Use `/reserved {event_id} <time> <details>` to confirm the reservation!",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )


def get_poll_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("poll", start_poll)],
        states={
            SELECT_EVENT: [CallbackQueryHandler(select_event, pattern=r"^pollevt_")],
            SELECT_OPTIONS: [CallbackQueryHandler(select_option, pattern=r"^(pollopt_|polldone)")],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
        per_user=True,
        per_chat=True,
    )
