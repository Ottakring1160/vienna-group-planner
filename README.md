# Vienna Group Planner — Telegram Bot

A Telegram bot for friend groups in Vienna to discover restaurants, exhibitions, events, and activities — then coordinate outings with polls, availability tracking, and reservation management.

## Features

- **Add & Browse** — Restaurants, exhibitions, events, and activities with categories, districts, price ranges, and custom tags
- **Interest Flagging** — Flag items you want to do; when enough people flag something, the bot nudges the group
- **Star Ratings** — Rate items 1-5 stars alongside flagging
- **Dinner Planning** — Create events, collect availability (yes/maybe/no)
- **Restaurant Polls** — Vote on where to go with live results and quorum thresholds
- **Reservation Tracking** — Confirm bookings and pin details in chat
- **Reminders** — Automatic 24h and 2h reminders before events
- **Weekly Digest** — Monday morning summary of trending items, expiring exhibitions, and active plans
- **Auto-Archive** — Expired exhibitions/events are automatically cleaned up

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token you receive

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Set your bot token as an environment variable:

```bash
# Linux/Mac
export TELEGRAM_BOT_TOKEN="your-token-here"

# Windows
set TELEGRAM_BOT_TOKEN=your-token-here
```

Or edit `config.py` directly (not recommended for production).

You can also customize in `config.py`:
- `DEFAULT_QUORUM` — Minimum votes to close a poll (default: 6)
- `FLAG_THRESHOLD` — Flags needed before bot nudges the group (default: 5)
- `REMINDER_HOURS` — When to send reminders (default: 24h and 2h before)
- `DIGEST_DAY` / `DIGEST_HOUR` — When to send the weekly digest

### 4. Run

```bash
python bot.py
```

### 5. Add to Your Group Chat

1. Add the bot to your Telegram group
2. Make it an admin (needed for pinning reservation messages)
3. Type `/help` to see all commands

## Commands

| Command | Description |
|---|---|
| `/add` | Interactive flow to add a restaurant, exhibition, event, or activity |
| `/list [type]` | Browse items — e.g. `/list restaurants`, `/list events` |
| `/search <query>` | Search by name, cuisine, tag, or district |
| `/info <id>` | Show full details for an item |
| `/flag <id>` | Flag interest in an item |
| `/trending` | See most popular items |
| `/expiring [days]` | Exhibitions/events ending soon |
| `/dinner <date> [time] [title]` | Create a new group event |
| `/poll` | Start a restaurant vote for an active event |
| `/status` | Show all active events and their status |
| `/reserved <event_id> <time> [details]` | Confirm a reservation |
| `/help` | Show all commands |

## Example Flow

1. **Add places**: `/add` → Restaurant → "Figlmueller" → Austrian → €€ → 1. → ...
2. **Flag interest**: `/flag 1` → rate it 5 stars
3. **Plan dinner**: `/dinner 2026-04-05 19:00 Friday dinner`
4. **Collect RSVPs**: Everyone clicks "I'm in!", "Maybe", or "Can't"
5. **Vote**: `/poll` → pick 3 restaurants → everyone votes
6. **Book**: `/reserved 1 19:30 Table for 8, confirmation #F1234`
7. **Show up** — bot reminds everyone 24h and 2h before!
