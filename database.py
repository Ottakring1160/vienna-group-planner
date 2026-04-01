import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "vienna_planner.db")


async def get_db():
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    async with await get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,  -- restaurant, exhibition, event, activity
                name TEXT NOT NULL,
                cuisine TEXT,
                price_range TEXT,
                district TEXT,
                address TEXT,
                maps_link TEXT,
                website TEXT,
                ticket_link TEXT,
                category TEXT,  -- for activities/exhibitions
                start_date TEXT,  -- for time-limited items
                end_date TEXT,
                tags TEXT,  -- comma-separated free-form tags
                added_by_id INTEGER,
                added_by_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                archived INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS flags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rating INTEGER,  -- optional 1-5 star rating
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (item_id) REFERENCES items(id),
                UNIQUE(item_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                date TEXT NOT NULL,
                time TEXT,
                status TEXT DEFAULT 'planning',  -- planning, polling, decided, completed
                quorum INTEGER DEFAULT 6,
                created_by_id INTEGER,
                created_by_name TEXT,
                chosen_item_id INTEGER,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (chosen_item_id) REFERENCES items(id)
            );

            CREATE TABLE IF NOT EXISTS availability (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                status TEXT NOT NULL,  -- yes, maybe, no
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (event_id) REFERENCES events(id),
                UNIQUE(event_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                item_id INTEGER NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id),
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT,
                poll_option_id INTEGER NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (event_id) REFERENCES events(id),
                FOREIGN KEY (poll_option_id) REFERENCES poll_options(id),
                UNIQUE(event_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                restaurant_name TEXT,
                time TEXT,
                party_size INTEGER,
                confirmation TEXT,
                notes TEXT,
                reserved_by_id INTEGER,
                reserved_by_name TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (event_id) REFERENCES events(id)
            );
        """)
        await db.commit()


# --- Item CRUD ---

async def add_item(item_type, name, added_by_id, added_by_name, **kwargs):
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO items (type, name, cuisine, price_range, district, address,
               maps_link, website, ticket_link, category, start_date, end_date, tags,
               added_by_id, added_by_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_type, name, kwargs.get("cuisine"), kwargs.get("price_range"),
             kwargs.get("district"), kwargs.get("address"), kwargs.get("maps_link"),
             kwargs.get("website"), kwargs.get("ticket_link"), kwargs.get("category"),
             kwargs.get("start_date"), kwargs.get("end_date"), kwargs.get("tags"),
             added_by_id, added_by_name)
        )
        await db.commit()
        return cursor.lastrowid


async def get_items(item_type=None, search=None, district=None, cuisine=None,
                    price_range=None, tag=None, include_archived=False):
    conditions = []
    params = []

    if not include_archived:
        conditions.append("archived = 0")
    if item_type:
        conditions.append("type = ?")
        params.append(item_type)
    if search:
        conditions.append("(name LIKE ? OR tags LIKE ? OR category LIKE ? OR cuisine LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like, like])
    if district:
        conditions.append("district = ?")
        params.append(district)
    if cuisine:
        conditions.append("cuisine = ?")
        params.append(cuisine)
    if price_range:
        conditions.append("price_range = ?")
        params.append(price_range)
    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")

    where = " AND ".join(conditions) if conditions else "1=1"

    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM items WHERE {where} ORDER BY created_at DESC", params
        )
        return await cursor.fetchall()


async def get_item(item_id):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        return await cursor.fetchone()


async def archive_expired_items():
    now = datetime.now().strftime("%Y-%m-%d")
    async with await get_db() as db:
        await db.execute(
            "UPDATE items SET archived = 1 WHERE end_date IS NOT NULL AND end_date < ? AND archived = 0",
            (now,)
        )
        await db.commit()


# --- Flags ---

async def add_flag(item_id, user_id, rating=None):
    async with await get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO flags (item_id, user_id, rating) VALUES (?, ?, ?)",
            (item_id, user_id, rating)
        )
        await db.commit()


async def get_flag_count(item_id):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM flags WHERE item_id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        return row[0]


async def get_avg_rating(item_id):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT AVG(rating) FROM flags WHERE item_id = ? AND rating IS NOT NULL",
            (item_id,)
        )
        row = await cursor.fetchone()
        return round(row[0], 1) if row[0] else None


async def get_trending(limit=10):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT i.*, COUNT(f.id) as flag_count, AVG(f.rating) as avg_rating
            FROM items i
            JOIN flags f ON i.id = f.item_id
            WHERE i.archived = 0
            GROUP BY i.id
            ORDER BY flag_count DESC, avg_rating DESC
            LIMIT ?
        """, (limit,))
        return await cursor.fetchall()


async def get_expiring(days=7):
    now = datetime.now().strftime("%Y-%m-%d")
    future = datetime.now()
    from datetime import timedelta
    future = (future + timedelta(days=days)).strftime("%Y-%m-%d")
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT i.*, COUNT(f.id) as flag_count
            FROM items i
            LEFT JOIN flags f ON i.id = f.item_id
            WHERE i.end_date IS NOT NULL AND i.end_date BETWEEN ? AND ?
            AND i.archived = 0
            GROUP BY i.id
            ORDER BY i.end_date ASC
        """, (now, future))
        return await cursor.fetchall()


# --- Events ---

async def create_event(title, date, time, created_by_id, created_by_name, quorum=6):
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO events (title, date, time, created_by_id, created_by_name, quorum)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, date, time, created_by_id, created_by_name, quorum)
        )
        await db.commit()
        return cursor.lastrowid


async def get_event(event_id):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        return await cursor.fetchone()


async def get_active_events():
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE status IN ('planning', 'polling') ORDER BY date ASC"
        )
        return await cursor.fetchall()


async def update_event_status(event_id, status, chosen_item_id=None):
    async with await get_db() as db:
        if chosen_item_id:
            await db.execute(
                "UPDATE events SET status = ?, chosen_item_id = ? WHERE id = ?",
                (status, chosen_item_id, event_id)
            )
        else:
            await db.execute(
                "UPDATE events SET status = ? WHERE id = ?", (status, event_id)
            )
        await db.commit()


# --- Availability ---

async def set_availability(event_id, user_id, user_name, status):
    async with await get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO availability (event_id, user_id, user_name, status) VALUES (?, ?, ?, ?)",
            (event_id, user_id, user_name, status)
        )
        await db.commit()


async def get_availability(event_id):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM availability WHERE event_id = ?", (event_id,)
        )
        return await cursor.fetchall()


# --- Polls ---

async def create_poll_option(event_id, item_id):
    async with await get_db() as db:
        cursor = await db.execute(
            "INSERT INTO poll_options (event_id, item_id) VALUES (?, ?)",
            (event_id, item_id)
        )
        await db.commit()
        return cursor.lastrowid


async def get_poll_options(event_id):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT po.id as option_id, po.item_id, i.name, i.type, i.cuisine,
                   i.price_range, i.district, COUNT(v.id) as vote_count
            FROM poll_options po
            JOIN items i ON po.item_id = i.id
            LEFT JOIN votes v ON po.id = v.poll_option_id
            WHERE po.event_id = ?
            GROUP BY po.id
            ORDER BY vote_count DESC
        """, (event_id,))
        return await cursor.fetchall()


async def cast_vote(event_id, user_id, user_name, poll_option_id):
    async with await get_db() as db:
        await db.execute(
            "INSERT OR REPLACE INTO votes (event_id, user_id, user_name, poll_option_id) VALUES (?, ?, ?, ?)",
            (event_id, user_id, user_name, poll_option_id)
        )
        await db.commit()


async def get_vote_count(event_id):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT COUNT(DISTINCT user_id) FROM votes WHERE event_id = ?", (event_id,)
        )
        row = await cursor.fetchone()
        return row[0]


# --- Reservations ---

async def add_reservation(event_id, restaurant_name, time, party_size,
                          confirmation, notes, reserved_by_id, reserved_by_name):
    async with await get_db() as db:
        cursor = await db.execute(
            """INSERT INTO reservations (event_id, restaurant_name, time, party_size,
               confirmation, notes, reserved_by_id, reserved_by_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_id, restaurant_name, time, party_size, confirmation, notes,
             reserved_by_id, reserved_by_name)
        )
        await db.commit()
        return cursor.lastrowid


async def get_reservation(event_id):
    async with await get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM reservations WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
            (event_id,)
        )
        return await cursor.fetchone()
