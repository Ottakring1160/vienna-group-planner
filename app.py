from flask import Flask, render_template, request, jsonify, session
import sqlite3
import os
import json
import re
import requests
from urllib.parse import unquote
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "vienna-planner-prototype-secret"

# Google Places API key
GOOGLE_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "AIzaSyDSSwkwXjyE3Sm8DthXm89AvYReQjzjp_4")

# Database: PostgreSQL on Render, SQLite locally
DATABASE_URL = os.environ.get("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith("postgres")

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # Render uses postgres:// but psycopg2 needs postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "vienna_planner.db")

# Simulated group members for prototype
GROUP_MEMBERS = [
    {"id": 1, "name": "You"},
    {"id": 2, "name": "Anna"},
    {"id": 3, "name": "Max"},
    {"id": 4, "name": "Sophie"},
    {"id": 5, "name": "Lukas"},
    {"id": 6, "name": "Elena"},
    {"id": 7, "name": "David"},
    {"id": 8, "name": "Mia"},
    {"id": 9, "name": "Felix"},
    {"id": 10, "name": "Laura"},
    {"id": 11, "name": "Jonas"},
    {"id": 12, "name": "Sarah"},
]


class DictRow(dict):
    """Make dict behave like sqlite3.Row for compatibility."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class DBConnection:
    """Wrapper that provides the same interface for both SQLite and PostgreSQL."""
    def __init__(self):
        if USE_POSTGRES:
            self.conn = psycopg2.connect(DATABASE_URL)
            self.is_pg = True
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row
            self.is_pg = False

    def execute(self, query, params=None):
        if self.is_pg:
            query = query.replace("?", "%s")
            # Handle INSERT OR REPLACE: convert to upsert
            if "INSERT OR REPLACE INTO" in query:
                query = self._convert_upsert(query, "REPLACE")
            elif "INSERT OR IGNORE INTO" in query:
                query = self._convert_upsert(query, "IGNORE")
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            # Add RETURNING id for INSERT statements to get lastrowid
            if query.strip().upper().startswith("INSERT") and "RETURNING" not in query.upper() and "ON CONFLICT" not in query.upper():
                query = query.rstrip().rstrip(";") + " RETURNING id"
            try:
                cur.execute(query, params or ())
            except psycopg2.errors.UniqueViolation:
                self.conn.rollback()
                return PGCursor(cur, False)
            except Exception as e:
                self.conn.rollback()
                raise
            return PGCursor(cur, query.strip().upper().startswith("INSERT"))
        else:
            return self.conn.execute(query, params or ())

    def _convert_upsert(self, query, mode):
        """Convert INSERT OR REPLACE/IGNORE to PostgreSQL ON CONFLICT."""
        query = query.replace("INSERT OR REPLACE INTO", "INSERT INTO")
        query = query.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        # For simplicity, use ON CONFLICT DO NOTHING for both modes
        # This prevents duplicate key errors
        if "ON CONFLICT" not in query:
            query = query.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return query

    def executescript(self, script):
        if self.is_pg:
            # Convert SQLite syntax to PostgreSQL
            script = script.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            script = script.replace("datetime('now')", "NOW()")
            script = script.replace("UNIQUE(", "UNIQUE (")
            cur = self.conn.cursor()
            cur.execute(script)
            self.conn.commit()
        else:
            self.conn.executescript(script)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PGCursor:
    """Wrapper around psycopg2 cursor to match sqlite3 interface."""
    def __init__(self, cursor, is_insert=False):
        self.cursor = cursor
        self.lastrowid = None
        if is_insert:
            try:
                row = cursor.fetchone()
                if row and "id" in row:
                    self.lastrowid = row["id"]
            except Exception:
                pass

    def fetchone(self):
        row = self.cursor.fetchone()
        return DictRow(row) if row else None

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [DictRow(r) for r in rows]


def get_db():
    return DBConnection()


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            cuisine TEXT,
            price_range TEXT,
            district TEXT,
            address TEXT,
            maps_link TEXT,
            website TEXT,
            ticket_link TEXT,
            category TEXT,
            start_date TEXT,
            end_date TEXT,
            tags TEXT,
            added_by_id INTEGER,
            added_by_name TEXT,
            recommender_note TEXT,
            recommender_rating INTEGER,
            lat REAL,
            lng REAL,
            created_at TEXT DEFAULT (datetime('now')),
            archived INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            rating INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS shortlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS post_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            event_id INTEGER,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, event_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS vouches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            note TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(item_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            date TEXT NOT NULL,
            time TEXT,
            status TEXT DEFAULT 'planning',
            quorum INTEGER DEFAULT 6,
            created_by_id INTEGER,
            created_by_name TEXT,
            chosen_item_id INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS availability (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            status TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(event_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS poll_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            user_name TEXT,
            poll_option_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
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
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS museums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            district TEXT,
            address TEXT,
            maps_link TEXT,
            website TEXT,
            image_url TEXT,
            description TEXT,
            lat REAL,
            lng REAL
        );

        CREATE TABLE IF NOT EXISTS exhibitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            museum_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            start_date TEXT,
            end_date TEXT,
            price TEXT,
            ticket_link TEXT,
            image_url TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (museum_id) REFERENCES museums(id)
        );
    """)
    conn.commit()
    conn.close()


def seed_museums():
    """Seed Vienna art museums and their exhibitions."""
    conn = get_db()
    existing = conn.execute("SELECT COUNT(*) FROM museums").fetchone()[0]
    if existing > 0:
        conn.close()
        return

    museums_data = [
        {
            "name": "Kunsthistorisches Museum",
            "district": "1.", "lat": 48.2036, "lng": 16.3614,
            "address": "Maria-Theresien-Platz, 1010 Wien",
            "website": "https://www.khm.at",
            "description": "One of the world's great art museums, housing imperial collections spanning 5,000 years.",
            "exhibitions": [
                {"title": "Satisfying: Art and the Essential", "start_date": "2025-10-14", "end_date": "2026-04-13", "price": "€21", "description": "A journey through art that explores the human need for fulfilment and satisfaction."},
                {"title": "The Habsburg Collection: Masterpieces Rediscovered", "start_date": "2026-02-01", "end_date": "2026-08-30", "price": "€21", "description": "Newly restored masterpieces from the imperial collection on display for the first time."},
            ]
        },
        {
            "name": "Albertina",
            "district": "1.", "lat": 48.2047, "lng": 16.3685,
            "address": "Albertinapl. 1, 1010 Wien",
            "website": "https://www.albertina.at",
            "description": "World-class collection of graphic arts, from Durer to contemporary, in a historic Habsburg palace.",
            "exhibitions": [
                {"title": "Roy Lichtenstein: Retrospective", "start_date": "2026-01-23", "end_date": "2026-05-18", "price": "€18.90", "description": "The most comprehensive Lichtenstein retrospective in Europe, spanning his entire career."},
                {"title": "Monet to Picasso: The Batliner Collection", "start_date": "2025-01-01", "end_date": "2027-12-31", "price": "€18.90", "description": "Permanent highlights of Impressionism to Cubism from the renowned Batliner Collection."},
            ]
        },
        {
            "name": "Albertina Modern",
            "district": "1.", "lat": 48.2003, "lng": 16.3711,
            "address": "Karlsplatz 5, 1010 Wien",
            "website": "https://www.albertina.at/albertina-modern",
            "description": "The Albertina's contemporary art venue in the Kunstlerhaus on Karlsplatz.",
            "exhibitions": [
                {"title": "Austrian Art Since 1945", "start_date": "2025-09-01", "end_date": "2026-06-15", "price": "€14.90", "description": "A sweeping survey of Austrian postwar and contemporary art movements."},
                {"title": "New Perspectives: Emerging Vienna", "start_date": "2026-03-01", "end_date": "2026-07-20", "price": "€14.90", "description": "Young Vienna-based artists reshaping contemporary art."},
            ]
        },
        {
            "name": "Heidi Horten Collection",
            "district": "1.", "lat": 48.2041, "lng": 16.3670,
            "address": "Hanuschgasse 3, 1010 Wien",
            "website": "https://www.heidihortencollection.com",
            "description": "One of Europe's most significant private art collections, spanning from the classic modern period to today.",
            "exhibitions": [
                {"title": "WOW! The Heidi Horten Collection", "start_date": "2025-06-01", "end_date": "2026-12-31", "price": "€15", "description": "The spectacular permanent collection featuring works by Warhol, Basquiat, Koons, and more."},
                {"title": "Open: Art for All", "start_date": "2026-02-15", "end_date": "2026-06-30", "price": "€15", "description": "An exhibition exploring how art creates community and shared experiences."},
            ]
        },
        {
            "name": "Leopold Museum",
            "district": "7.", "lat": 48.2035, "lng": 16.3585,
            "address": "Museumsplatz 1, 1070 Wien",
            "website": "https://www.leopoldmuseum.org",
            "description": "Houses the world's largest Egon Schiele collection and key works of Viennese art around 1900.",
            "exhibitions": [
                {"title": "Egon Schiele: Masterworks from the Collection", "start_date": "2025-01-01", "end_date": "2027-12-31", "price": "€16", "description": "The definitive permanent display of Schiele's radical works."},
                {"title": "Vienna 1900: Climate of Art and Modernity", "start_date": "2026-02-07", "end_date": "2026-08-31", "price": "€16", "description": "How Vienna's unique cultural climate around 1900 produced revolutionary art and design."},
            ]
        },
        {
            "name": "Belvedere",
            "district": "3.", "lat": 48.1913, "lng": 16.3808,
            "address": "Prinz-Eugen-Str. 27, 1030 Wien",
            "website": "https://www.belvedere.at",
            "description": "Baroque palace complex housing Austria's most important art collection, including Klimt's The Kiss.",
            "exhibitions": [
                {"title": "Gustav Klimt: The Kiss and Beyond", "start_date": "2025-01-01", "end_date": "2027-12-31", "price": "€17.50", "description": "The iconic permanent collection featuring Klimt, Schiele, and Austrian art masterworks."},
                {"title": "Into the Future: Austrian Art in Transition", "start_date": "2026-01-20", "end_date": "2026-05-25", "price": "€17.50", "description": "How contemporary Austrian artists are reimagining tradition and identity."},
            ]
        },
    ]

    for museum in museums_data:
        cursor = conn.execute(
            "INSERT INTO museums (name, district, address, website, description, lat, lng) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (museum["name"], museum["district"], museum["address"], museum["website"], museum["description"],
             museum.get("lat"), museum.get("lng"))
        )
        museum_id = cursor.lastrowid
        for ex in museum["exhibitions"]:
            conn.execute(
                "INSERT INTO exhibitions (museum_id, title, description, start_date, end_date, price) VALUES (?, ?, ?, ?, ?, ?)",
                (museum_id, ex["title"], ex["description"], ex["start_date"], ex["end_date"], ex["price"])
            )
    conn.commit()
    conn.close()


# --- Routes ---

@app.route("/")
def index():
    return render_template("app.html", members=GROUP_MEMBERS)


@app.route("/api/dashboard", methods=["GET"])
def api_dashboard():
    conn = get_db()
    restaurants_raw = conn.execute(
        "SELECT i.*, COUNT(f.id) as flag_count, AVG(f.rating) as avg_rating FROM items i LEFT JOIN flags f ON i.id = f.item_id WHERE i.type = 'restaurant' AND i.archived = 0 GROUP BY i.id ORDER BY flag_count DESC, i.created_at DESC"
    ).fetchall()
    # Add vouch counts
    restaurants = []
    for r in restaurants_raw:
        d = dict(r)
        vc = conn.execute("SELECT COUNT(*) as c FROM vouches WHERE item_id = ?", (d["id"],)).fetchone()
        d["vouch_count"] = vc["c"] if vc else 0
        vnames = conn.execute("SELECT user_name FROM vouches WHERE item_id = ? LIMIT 3", (d["id"],)).fetchall()
        d["vouch_names"] = [v["user_name"] for v in vnames]
        restaurants.append(d)
    activities = conn.execute(
        "SELECT i.*, COUNT(f.id) as flag_count FROM items i LEFT JOIN flags f ON i.id = f.item_id WHERE i.type = 'activity' AND i.archived = 0 GROUP BY i.id ORDER BY i.created_at DESC"
    ).fetchall()
    events_items = conn.execute(
        "SELECT i.*, COUNT(f.id) as flag_count FROM items i LEFT JOIN flags f ON i.id = f.item_id WHERE i.type = 'event' AND i.archived = 0 GROUP BY i.id ORDER BY i.start_date ASC"
    ).fetchall()
    active_events = conn.execute(
        "SELECT * FROM events WHERE status IN ('planning', 'polling', 'decided') ORDER BY date ASC"
    ).fetchall()
    conn.close()
    return jsonify({
        "restaurants": [dict(r) for r in restaurants],
        "activities": [dict(a) for a in activities],
        "events": [dict(e) for e in events_items],
        "active_plans": [dict(e) for e in active_events],
    })


@app.route("/api/museums", methods=["GET"])
def api_museums():
    conn = get_db()
    museums = conn.execute("SELECT * FROM museums ORDER BY name").fetchall()
    result = []
    for m in museums:
        exhibitions = conn.execute(
            "SELECT * FROM exhibitions WHERE museum_id = ? ORDER BY end_date ASC",
            (m["id"],)
        ).fetchall()
        museum_dict = dict(m)
        museum_dict["exhibitions"] = [dict(e) for e in exhibitions]
        # Check which exhibitions are current
        today = datetime.now().strftime("%Y-%m-%d")
        for ex in museum_dict["exhibitions"]:
            ex["is_current"] = (ex.get("start_date", "") <= today <= ex.get("end_date", "9999-12-31"))
            # Days remaining
            if ex.get("end_date"):
                try:
                    end = datetime.strptime(ex["end_date"], "%Y-%m-%d")
                    delta = (end - datetime.now()).days
                    ex["days_remaining"] = delta
                except ValueError:
                    ex["days_remaining"] = None
        result.append(museum_dict)
    conn.close()
    return jsonify({"museums": result})


@app.route("/api/shortlist", methods=["GET", "POST", "DELETE"])
def api_shortlist():
    user_id = request.args.get("user_id", 1, type=int)
    user_name = request.args.get("user_name", "You")
    conn = get_db()

    if request.method == "POST":
        data = request.json
        item_id = data.get("item_id")
        conn.execute("INSERT OR IGNORE INTO shortlist (item_id, user_id, user_name) VALUES (?, ?, ?)",
                     (item_id, user_id, user_name))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    if request.method == "DELETE":
        data = request.json
        item_id = data.get("item_id")
        conn.execute("DELETE FROM shortlist WHERE item_id = ? AND user_id = ?", (item_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    # GET — return user's shortlist with item details
    items = conn.execute("""
        SELECT i.*, s.created_at as shortlisted_at,
               COUNT(f.id) as flag_count, AVG(f.rating) as avg_rating
        FROM shortlist s
        JOIN items i ON s.item_id = i.id
        LEFT JOIN flags f ON i.id = f.item_id
        WHERE s.user_id = ? AND i.archived = 0
        GROUP BY i.id ORDER BY s.created_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return jsonify({"shortlist": [dict(i) for i in items]})


@app.route("/api/post-rate", methods=["POST"])
def api_post_rate():
    data = request.json
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO post_ratings (item_id, event_id, user_id, user_name, rating, comment) VALUES (?, ?, ?, ?, ?, ?)",
        (data["item_id"], data.get("event_id"), data["user_id"], data["user_name"], data["rating"], data.get("comment"))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/leaderboard", methods=["GET"])
def api_leaderboard():
    conn = get_db()
    # For each person who added restaurants, calculate:
    # - taste_score: avg group post-visit rating of their recommendations
    # - accuracy: how close their recommender_rating was to the group average
    # - total recommendations
    recommenders = conn.execute("""
        SELECT i.added_by_id, i.added_by_name,
               COUNT(DISTINCT i.id) as total_recs,
               AVG(i.recommender_rating) as avg_recommender_rating,
               AVG(pr.rating) as avg_group_rating,
               COUNT(DISTINCT pr.id) as total_group_reviews
        FROM items i
        LEFT JOIN post_ratings pr ON i.id = pr.item_id
        WHERE i.type = 'restaurant' AND i.archived = 0
        GROUP BY i.added_by_id
        HAVING total_recs > 0
        ORDER BY avg_group_rating DESC
    """).fetchall()

    leaderboard = []
    for r in recommenders:
        d = dict(r)
        # Accuracy: lower is better (abs difference between their rating and group avg)
        if d["avg_recommender_rating"] and d["avg_group_rating"]:
            d["accuracy"] = round(abs(d["avg_recommender_rating"] - d["avg_group_rating"]), 1)
        else:
            d["accuracy"] = None
        d["avg_group_rating"] = round(d["avg_group_rating"], 1) if d["avg_group_rating"] else None
        d["avg_recommender_rating"] = round(d["avg_recommender_rating"], 1) if d["avg_recommender_rating"] else None
        leaderboard.append(d)

    conn.close()
    return jsonify({"leaderboard": leaderboard})


@app.route("/api/restaurant/<int:item_id>", methods=["GET"])
def api_restaurant_detail(item_id):
    conn = get_db()
    item = conn.execute(
        "SELECT i.*, COUNT(f.id) as flag_count, AVG(f.rating) as avg_rating FROM items i LEFT JOIN flags f ON i.id = f.item_id WHERE i.id = ? GROUP BY i.id",
        (item_id,)
    ).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    vouches = conn.execute(
        "SELECT * FROM vouches WHERE item_id = ? ORDER BY created_at DESC", (item_id,)
    ).fetchall()

    post_ratings = conn.execute(
        "SELECT * FROM post_ratings WHERE item_id = ? ORDER BY created_at DESC", (item_id,)
    ).fetchall()

    shortlist_count = conn.execute(
        "SELECT COUNT(*) as c FROM shortlist WHERE item_id = ?", (item_id,)
    ).fetchone()["c"]

    conn.close()
    return jsonify({
        "item": dict(item),
        "vouches": [dict(v) for v in vouches],
        "post_ratings": [dict(r) for r in post_ratings],
        "shortlist_count": shortlist_count
    })


@app.route("/api/vouch", methods=["POST"])
def api_vouch():
    data = request.json
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO vouches (item_id, user_id, user_name, note) VALUES (?, ?, ?, ?)",
        (data["item_id"], data["user_id"], data["user_name"], data.get("note", ""))
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/bulk-import", methods=["POST"])
def api_bulk_import():
    """Import multiple restaurants from a list of names or Google Maps links."""
    data = request.json
    lines = data.get("items", [])
    user_id = data.get("user_id", 1)
    user_name = data.get("user_name", "Guest")

    if not lines:
        return jsonify({"error": "No items to import"}), 400

    results = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Determine if it's a URL or a name
        is_url = any(x in line for x in ["google", "goo.gl", "http", "share."])

        try:
            if is_url or (not is_url and GOOGLE_API_KEY):
                # Use the maps lookup logic
                import io
                from flask import Request
                # Call internal lookup
                place_name = line
                resolved_url = line

                if is_url:
                    # Follow redirects
                    if any(x in line for x in ["goo.gl", "maps.app", "share.google", "g.co"]):
                        try:
                            resp = requests.get(line, allow_redirects=True, timeout=10,
                                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
                            resolved_url = resp.url
                            all_urls = [h.headers.get("Location", "") for h in resp.history] + [resp.url]
                            candidates = []
                            for loc in all_urls:
                                if not loc:
                                    continue
                                loc_decoded = unquote(loc)
                                pm = re.search(r'/place/([^/@]+)', loc_decoded)
                                if pm:
                                    candidates.append(unquote(pm.group(1)).replace('+', ' '))
                                for qm in re.finditer(r'[?&]q=([^&]+)', loc_decoded):
                                    c = unquote(qm.group(1)).replace('+', ' ')
                                    if len(c) > 3 and not c.startswith('http') and ' ' in c:
                                        candidates.append(c)
                            for c in candidates:
                                if ' ' in c:
                                    place_name = c
                                    break
                            if place_name == line and candidates:
                                place_name = candidates[-1]
                        except Exception:
                            pass

                    place_match = re.search(r'/place/([^/@]+)', resolved_url)
                    if place_match and place_name == line:
                        place_name = unquote(place_match.group(1)).replace('+', ' ')

                if GOOGLE_API_KEY:
                    search_query = place_name if place_name != line else line
                    # Call Places API
                    search_url = "https://places.googleapis.com/v1/places:searchText"
                    headers = {
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": GOOGLE_API_KEY,
                        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.types,places.priceLevel,places.rating,places.userRatingCount,places.websiteUri,places.googleMapsUri,places.location,places.primaryType,places.primaryTypeDisplayName"
                    }
                    body = {
                        "textQuery": search_query + (" Vienna" if "vienna" not in search_query.lower() and "wien" not in search_query.lower() else ""),
                        "locationBias": {
                            "circle": {
                                "center": {"latitude": 48.2082, "longitude": 16.3738},
                                "radius": 15000.0
                            }
                        }
                    }
                    api_resp = requests.post(search_url, json=body, headers=headers, timeout=10)
                    api_result = api_resp.json()

                    if api_result.get("places"):
                        place = api_result["places"][0]
                        price_map = {
                            "PRICE_LEVEL_FREE": "Free",
                            "PRICE_LEVEL_INEXPENSIVE": "€",
                            "PRICE_LEVEL_MODERATE": "€€",
                            "PRICE_LEVEL_EXPENSIVE": "€€€",
                            "PRICE_LEVEL_VERY_EXPENSIVE": "€€€€",
                        }
                        cuisine = _guess_cuisine(place.get("types", []), place.get("primaryTypeDisplayName", {}).get("text", ""))
                        address = place.get("formattedAddress", "")
                        district = _extract_district(address)
                        loc = place.get("location", {})

                        # Save to DB
                        conn = get_db()
                        cursor = conn.execute(
                            """INSERT INTO items (type, name, cuisine, price_range, district, address,
                               maps_link, website, lat, lng, added_by_id, added_by_name)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            ("restaurant",
                             place.get("displayName", {}).get("text", place_name),
                             cuisine,
                             price_map.get(place.get("priceLevel", ""), ""),
                             district,
                             address,
                             place.get("googleMapsUri", resolved_url if "google" in resolved_url else ""),
                             place.get("websiteUri", ""),
                             loc.get("latitude"),
                             loc.get("longitude"),
                             user_id, user_name)
                        )
                        item_id = cursor.lastrowid
                        conn.commit()
                        conn.close()

                        results.append({
                            "status": "ok",
                            "name": place.get("displayName", {}).get("text", place_name),
                            "id": item_id,
                            "cuisine": cuisine,
                            "district": district,
                            "rating": place.get("rating")
                        })
                        continue

            # Fallback: just save the name
            conn = get_db()
            cursor = conn.execute(
                "INSERT INTO items (type, name, added_by_id, added_by_name) VALUES (?, ?, ?, ?)",
                ("restaurant", place_name if place_name != line else line, user_id, user_name)
            )
            conn.commit()
            conn.close()
            results.append({"status": "partial", "name": place_name or line, "id": cursor.lastrowid})

        except Exception as e:
            results.append({"status": "error", "input": line, "error": str(e)})

    return jsonify({
        "imported": len([r for r in results if r["status"] in ("ok", "partial")]),
        "errors": len([r for r in results if r["status"] == "error"]),
        "results": results
    })


@app.route("/api/maps-lookup", methods=["POST"])
def maps_lookup():
    """Resolve a Google Maps link into structured restaurant data."""
    data = request.json
    maps_input = data.get("url", "").strip()

    if not maps_input:
        return jsonify({"error": "No URL provided"}), 400

    # Step 1: Extract place name from Google Maps URL
    place_name = None
    resolved_url = maps_input

    # Follow short/share links to resolve the full URL
    if any(x in maps_input for x in ["goo.gl", "maps.app", "share.google", "g.co"]):
        try:
            resp = requests.get(maps_input, allow_redirects=True, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
            resolved_url = resp.url
            # Check all URLs in the redirect chain for place info
            # Collect all candidates, prefer the most human-readable one
            all_urls = [h.headers.get("Location", "") for h in resp.history] + [resp.url]
            candidates = []
            for loc in all_urls:
                if not loc:
                    continue
                loc_decoded = unquote(loc)
                pm = re.search(r'/place/([^/@]+)', loc_decoded)
                if pm:
                    candidates.append(unquote(pm.group(1)).replace('+', ' '))
                # Find all q= params
                for qm in re.finditer(r'[?&]q=([^&]+)', loc_decoded):
                    c = unquote(qm.group(1)).replace('+', ' ')
                    if len(c) > 3 and not c.startswith('http') and ' ' in c:
                        candidates.append(c)
            # Pick the best candidate: prefer ones with spaces (real names)
            for c in candidates:
                if ' ' in c:
                    place_name = c
                    break
            if not place_name and candidates:
                place_name = candidates[-1]
        except Exception:
            pass

    # Also try to extract from the final resolved URL and consent redirects
    # Google consent pages contain the original query in the 'continue' param
    if not place_name:
        continue_match = re.search(r'continue=([^&]+)', resolved_url)
        if continue_match:
            inner_url = unquote(continue_match.group(1))
            qm = re.search(r'[?&]q=([^&]+)', inner_url)
            if qm:
                place_name = unquote(qm.group(1)).replace('+', ' ')

    # Parse place name from various Google Maps URL patterns
    # Pattern 1: /maps/place/Restaurant+Name/...
    if not place_name:
        place_match = re.search(r'/place/([^/@]+)', resolved_url)
        if place_match:
            place_name = unquote(place_match.group(1)).replace('+', ' ')

    # Pattern 2: search query in URL ?q=Restaurant+Name
    if not place_name:
        q_match = re.search(r'[?&]q=([^&]+)', resolved_url)
        if q_match:
            place_name = unquote(q_match.group(1)).replace('+', ' ')

    # If not a URL at all, treat the input as a search query directly
    if not place_name and not any(x in maps_input for x in ["google", "goo.gl", "http", "share."]):
        place_name = maps_input

    # Step 2: If we have a Google API key, use Places API
    if GOOGLE_API_KEY:
        # If no place name extracted, try searching with the original URL or resolved URL
        search_query = place_name or maps_input
        return _lookup_with_api(search_query, resolved_url)

    # Step 3: Fallback — return what we parsed from the URL
    # Extract coordinates if present
    coords_match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', resolved_url)
    lat, lng = None, None
    if coords_match:
        lat, lng = coords_match.group(1), coords_match.group(2)

    # Guess district from Vienna postal codes in URL if present
    district = _guess_district_from_name(place_name)

    # If we couldn't extract a name at all, tell the user
    if not place_name or place_name == maps_input:
        return jsonify({
            "error": "Couldn't resolve this link without a Google API key. Set GOOGLE_MAPS_API_KEY or try pasting a longer Google Maps URL (e.g. google.com/maps/place/...)."
        }), 400

    return jsonify({
        "success": True,
        "source": "url_parse",
        "data": {
            "name": place_name,
            "address": "",
            "district": district,
            "cuisine": "",
            "price_range": "",
            "maps_link": resolved_url if "google" in resolved_url else maps_input,
            "website": "",
            "rating": None,
            "lat": lat,
            "lng": lng,
        },
        "message": "Parsed from URL. Set GOOGLE_MAPS_API_KEY for full details (cuisine, price, rating, address)."
    })


def _lookup_with_api(place_name, original_url):
    """Use Google Places API to get full restaurant details."""
    # Text Search to find the place
    search_url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.types,places.priceLevel,places.rating,places.userRatingCount,places.websiteUri,places.googleMapsUri,places.location,places.primaryType,places.primaryTypeDisplayName"
    }
    body = {
        "textQuery": place_name + " Vienna",
        "locationBias": {
            "circle": {
                "center": {"latitude": 48.2082, "longitude": 16.3738},
                "radius": 15000.0
            }
        }
    }

    try:
        resp = requests.post(search_url, json=body, headers=headers, timeout=10)
        result = resp.json()
    except Exception as e:
        return jsonify({"error": f"API error: {str(e)}"}), 500

    if not result.get("places"):
        return jsonify({"error": f"No results found for '{place_name}'"}), 404

    place = result["places"][0]

    # Map Google price levels to our format
    price_map = {
        "PRICE_LEVEL_FREE": "Free",
        "PRICE_LEVEL_INEXPENSIVE": "€",
        "PRICE_LEVEL_MODERATE": "€€",
        "PRICE_LEVEL_EXPENSIVE": "€€€",
        "PRICE_LEVEL_VERY_EXPENSIVE": "€€€€",
    }

    # Guess cuisine from types
    cuisine = _guess_cuisine(place.get("types", []), place.get("primaryTypeDisplayName", {}).get("text", ""))

    # Extract district from Vienna address
    address = place.get("formattedAddress", "")
    district = _extract_district(address)

    loc = place.get("location", {})

    return jsonify({
        "success": True,
        "source": "google_api",
        "data": {
            "name": place.get("displayName", {}).get("text", place_name),
            "address": address,
            "district": district,
            "cuisine": cuisine,
            "price_range": price_map.get(place.get("priceLevel", ""), ""),
            "maps_link": place.get("googleMapsUri", original_url),
            "website": place.get("websiteUri", ""),
            "rating": place.get("rating"),
            "rating_count": place.get("userRatingCount"),
            "primary_type": place.get("primaryTypeDisplayName", {}).get("text", ""),
            "lat": loc.get("latitude"),
            "lng": loc.get("longitude"),
        }
    })


def _guess_cuisine(types, primary_type):
    """Map Google place types to cuisine categories."""
    type_map = {
        "japanese_restaurant": "Japanese", "sushi_restaurant": "Japanese",
        "italian_restaurant": "Italian", "pizza_restaurant": "Italian",
        "chinese_restaurant": "Chinese", "thai_restaurant": "Thai",
        "indian_restaurant": "Indian", "mexican_restaurant": "Mexican",
        "greek_restaurant": "Greek", "french_restaurant": "French",
        "american_restaurant": "American", "turkish_restaurant": "Turkish",
        "vietnamese_restaurant": "Vietnamese", "korean_restaurant": "Korean",
        "seafood_restaurant": "Seafood", "vegan_restaurant": "Vegetarian/Vegan",
        "vegetarian_restaurant": "Vegetarian/Vegan",
        "bar": "Bar/Drinks", "cafe": "Brunch/Cafe", "coffee_shop": "Brunch/Cafe",
        "brunch_restaurant": "Brunch/Cafe", "hamburger_restaurant": "American",
        "steak_house": "American", "mediterranean_restaurant": "Greek",
        "middle_eastern_restaurant": "Middle Eastern",
    }
    for t in types:
        if t in type_map:
            return type_map[t]
    # Check primary type display name
    pt_lower = primary_type.lower()
    for keyword, cuisine in [("austrian", "Austrian"), ("wiener", "Austrian"),
                              ("italian", "Italian"), ("asian", "Asian"),
                              ("japanese", "Japanese"), ("chinese", "Chinese")]:
        if keyword in pt_lower:
            return cuisine
    return ""


def _extract_district(address):
    """Extract Vienna district from address like '1010 Wien' -> '1.'"""
    match = re.search(r'(\d{4})\s*Wien', address)
    if match:
        plz = match.group(1)
        district_num = int(plz[1:3])  # 1010 -> 01 -> 1
        if 1 <= district_num <= 23:
            return f"{district_num}."
    return ""


def _guess_district_from_name(name):
    """Last resort: check if district info is in the name."""
    return ""


@app.route("/api/send", methods=["POST"])
def send_message():
    data = request.json
    text = data.get("text", "").strip()
    user_id = data.get("user_id", 1)
    user_name = data.get("user_name", "You")

    if text.startswith("/"):
        return process_command(text, user_id, user_name)
    else:
        return jsonify({"messages": [{"type": "text", "text": f"Type /help to see available commands."}]})


@app.route("/api/action", methods=["POST"])
def handle_action():
    data = request.json
    action = data.get("action", "")
    user_id = data.get("user_id", 1)
    user_name = data.get("user_name", "You")
    payload = data.get("payload", {})

    return process_action(action, user_id, user_name, payload)


@app.route("/api/items", methods=["GET"])
def api_items():
    item_type = request.args.get("type")
    conn = get_db()
    if item_type:
        items = conn.execute("SELECT * FROM items WHERE type = ? AND archived = 0 ORDER BY created_at DESC",
                             (item_type,)).fetchall()
    else:
        items = conn.execute("SELECT * FROM items WHERE archived = 0 ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify({"items": [dict(i) for i in items]})


# --- Command Processing ---

def process_command(text, user_id, user_name):
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handlers = {
        "/help": cmd_help,
        "/start": cmd_help,
        "/add": cmd_add,
        "/list": cmd_list,
        "/search": cmd_search,
        "/info": cmd_info,
        "/flag": cmd_flag,
        "/trending": cmd_trending,
        "/expiring": cmd_expiring,
        "/dinner": cmd_dinner,
        "/poll": cmd_poll,
        "/status": cmd_status,
        "/reserved": cmd_reserved,
    }

    handler = handlers.get(cmd)
    if handler:
        return handler(args, user_id, user_name)
    else:
        return jsonify({"messages": [{"type": "text", "text": f"Unknown command: {cmd}\nType /help for available commands."}]})


def cmd_help(args, user_id, user_name):
    text = """<b>Vienna Group Planner Commands</b>

<b>Add & Browse</b>
/add — Add a restaurant, exhibition, event, or activity
/list [type] — Browse items (restaurants, exhibitions, events, activities)
/search [query] — Search by name, cuisine, tag, or district
/info [id] — Show details for an item

<b>Interest & Discovery</b>
/flag [id] — Flag interest in something
/trending — See most popular items
/expiring — Exhibitions/events ending soon

<b>Plan an Outing</b>
/dinner [date] [time] [title] — Create a new event
/poll — Start a restaurant vote for an event
/status — Show all active events

<b>Reservations</b>
/reserved [event_id] [time] [details] — Confirm a reservation"""
    return jsonify({"messages": [{"type": "html", "text": text}]})


def cmd_add(args, user_id, user_name):
    return jsonify({"messages": [
        {"type": "html", "text": "What would you like to add?"},
        {"type": "buttons", "buttons": [
            {"label": "🍽 Restaurant", "action": "add_start", "payload": {"type": "restaurant"}},
            {"label": "🖼 Exhibition", "action": "add_start", "payload": {"type": "exhibition"}},
            {"label": "🎉 Event", "action": "add_start", "payload": {"type": "event"}},
            {"label": "🎯 Activity", "action": "add_start", "payload": {"type": "activity"}},
        ]}
    ]})


def cmd_list(args, user_id, user_name):
    conn = get_db()
    item_type = None
    type_map = {"restaurants": "restaurant", "restaurant": "restaurant",
                "exhibitions": "exhibition", "exhibition": "exhibition",
                "events": "event", "event": "event",
                "activities": "activity", "activity": "activity"}
    if args:
        item_type = type_map.get(args.strip().lower())

    if item_type:
        items = conn.execute("SELECT * FROM items WHERE type = ? AND archived = 0 ORDER BY created_at DESC",
                             (item_type,)).fetchall()
    else:
        items = conn.execute("SELECT * FROM items WHERE archived = 0 ORDER BY created_at DESC").fetchall()
    conn.close()

    if not items:
        label = (item_type + "s") if item_type else "items"
        return jsonify({"messages": [{"type": "text", "text": f"No {label} found yet. Use /add to add some!"}]})

    label = (item_type + "s") if item_type else "items"
    cards = []
    for item in items:
        cards.append(format_item_card(dict(item)))

    return jsonify({"messages": [
        {"type": "html", "text": f"<b>All {label.title()}</b> ({len(items)} total)"},
        *[{"type": "card", "card": c} for c in cards]
    ]})


def cmd_search(args, user_id, user_name):
    if not args:
        return jsonify({"messages": [{"type": "text", "text": "Usage: /search <query>\nExamples: /search italian, /search rooftop, /search 7."}]})

    conn = get_db()
    like = f"%{args}%"
    items = conn.execute(
        "SELECT * FROM items WHERE archived = 0 AND (name LIKE ? OR tags LIKE ? OR category LIKE ? OR cuisine LIKE ?) ORDER BY created_at DESC",
        (like, like, like, like)
    ).fetchall()
    conn.close()

    if not items:
        return jsonify({"messages": [{"type": "text", "text": f"No results for '{args}'."}]})

    cards = [format_item_card(dict(i)) for i in items[:10]]
    return jsonify({"messages": [
        {"type": "html", "text": f"<b>Results for '{args}'</b> ({len(items)} found)"},
        *[{"type": "card", "card": c} for c in cards]
    ]})


def cmd_info(args, user_id, user_name):
    if not args:
        return jsonify({"messages": [{"type": "text", "text": "Usage: /info <id>"}]})
    try:
        item_id = int(args.strip())
    except ValueError:
        return jsonify({"messages": [{"type": "text", "text": "Please provide a valid ID number."}]})

    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": f"Item #{item_id} not found."}]})

    flag_count = conn.execute("SELECT COUNT(*) as c FROM flags WHERE item_id = ?", (item_id,)).fetchone()["c"]
    avg_rating = conn.execute("SELECT AVG(rating) as a FROM flags WHERE item_id = ? AND rating IS NOT NULL", (item_id,)).fetchone()["a"]
    conn.close()

    card = format_item_card(dict(item))
    card["flag_count"] = flag_count
    card["avg_rating"] = round(avg_rating, 1) if avg_rating else None

    return jsonify({"messages": [
        {"type": "card", "card": card},
        {"type": "buttons", "buttons": [
            {"label": "🚩 Flag Interest", "action": "flag", "payload": {"item_id": item_id}},
            {"label": "⭐ 1", "action": "rate", "payload": {"item_id": item_id, "rating": 1}},
            {"label": "⭐ 2", "action": "rate", "payload": {"item_id": item_id, "rating": 2}},
            {"label": "⭐ 3", "action": "rate", "payload": {"item_id": item_id, "rating": 3}},
            {"label": "⭐ 4", "action": "rate", "payload": {"item_id": item_id, "rating": 4}},
            {"label": "⭐ 5", "action": "rate", "payload": {"item_id": item_id, "rating": 5}},
        ]}
    ]})


def cmd_flag(args, user_id, user_name):
    if not args:
        return jsonify({"messages": [{"type": "text", "text": "Usage: /flag <id> — Flag interest in something"}]})
    try:
        item_id = int(args.strip())
    except ValueError:
        return jsonify({"messages": [{"type": "text", "text": "Please provide a valid ID number."}]})

    conn = get_db()
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": f"Item #{item_id} not found."}]})

    conn.execute("INSERT OR REPLACE INTO flags (item_id, user_id, user_name) VALUES (?, ?, ?)",
                 (item_id, user_id, user_name))
    conn.commit()
    count = conn.execute("SELECT COUNT(*) as c FROM flags WHERE item_id = ?", (item_id,)).fetchone()["c"]
    conn.close()

    emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}.get(item["type"], "📌")
    text = f"🚩 {user_name} is interested in {emoji} <b>{item['name']}</b>!\nTotal interest: {count} people"
    if count >= 5:
        text += f"\n\n🔥 <b>{count} people interested!</b> Time to plan this? Use /dinner to set a date!"

    return jsonify({"messages": [
        {"type": "html", "text": text},
        {"type": "buttons", "buttons": [
            {"label": "⭐ 1", "action": "rate", "payload": {"item_id": item_id, "rating": 1}},
            {"label": "⭐ 2", "action": "rate", "payload": {"item_id": item_id, "rating": 2}},
            {"label": "⭐ 3", "action": "rate", "payload": {"item_id": item_id, "rating": 3}},
            {"label": "⭐ 4", "action": "rate", "payload": {"item_id": item_id, "rating": 4}},
            {"label": "⭐ 5", "action": "rate", "payload": {"item_id": item_id, "rating": 5}},
        ]}
    ]})


def cmd_trending(args, user_id, user_name):
    conn = get_db()
    items = conn.execute("""
        SELECT i.*, COUNT(f.id) as flag_count, AVG(f.rating) as avg_rating
        FROM items i JOIN flags f ON i.id = f.item_id
        WHERE i.archived = 0
        GROUP BY i.id ORDER BY flag_count DESC, avg_rating DESC LIMIT 10
    """).fetchall()
    conn.close()

    if not items:
        return jsonify({"messages": [{"type": "text", "text": "Nothing flagged yet! Use /flag <id> to express interest."}]})

    lines = ["<b>🔥 Trending — Most Wanted</b>\n"]
    medals = ["🥇", "🥈", "🥉"]
    for i, item in enumerate(items):
        emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}.get(item["type"], "📌")
        medal = medals[i] if i < 3 else f"{i+1}."
        line = f"{medal} {emoji} <b>{item['name']}</b> — {item['flag_count']} interested"
        if item["avg_rating"]:
            line += f" | ⭐ {round(item['avg_rating'], 1)}/5"
        lines.append(line)

    return jsonify({"messages": [{"type": "html", "text": "\n".join(lines)}]})


def cmd_expiring(args, user_id, user_name):
    days = 14
    if args:
        try:
            days = int(args.strip())
        except ValueError:
            pass

    now = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")

    conn = get_db()
    items = conn.execute("""
        SELECT i.*, COUNT(f.id) as flag_count
        FROM items i LEFT JOIN flags f ON i.id = f.item_id
        WHERE i.end_date IS NOT NULL AND i.end_date BETWEEN ? AND ? AND i.archived = 0
        GROUP BY i.id ORDER BY i.end_date ASC
    """, (now, future)).fetchall()
    conn.close()

    if not items:
        return jsonify({"messages": [{"type": "text", "text": f"No exhibitions/events expiring in the next {days} days."}]})

    lines = [f"<b>⏰ Expiring Soon</b> (next {days} days)\n"]
    for item in items:
        emoji = {"exhibition": "🖼", "event": "🎉"}.get(item["type"], "📌")
        line = f"{emoji} <b>{item['name']}</b> — ends {item['end_date']}"
        if item["flag_count"]:
            line += f" | 🚩 {item['flag_count']} interested"
        lines.append(line)

    return jsonify({"messages": [{"type": "html", "text": "\n".join(lines)}]})


def cmd_dinner(args, user_id, user_name):
    if not args:
        return jsonify({"messages": [{"type": "text",
            "text": "Usage: /dinner <date> [time] [title]\nExamples:\n  /dinner 2026-04-05 19:00 Friday dinner\n  /dinner 2026-04-12 20:00"}]})

    parts = args.split()
    date_str = parts[0]
    time_str = parts[1] if len(parts) > 1 and ":" in parts[1] else "TBD"
    title_start = 2 if time_str != "TBD" else 1
    title = " ".join(parts[title_start:]) if len(parts) > title_start else f"Dinner on {date_str}"

    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO events (title, date, time, created_by_id, created_by_name, quorum) VALUES (?, ?, ?, ?, ?, ?)",
        (title, date_str, time_str, user_id, user_name, 6)
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({"messages": [
        {"type": "html", "text": f"<b>📅 New Event: {title}</b>\nDate: {date_str}\nTime: {time_str}\nOrganized by: {user_name}\n\nWho's in? Click below!"},
        {"type": "buttons", "buttons": [
            {"label": "✅ I'm in!", "action": "availability", "payload": {"event_id": event_id, "status": "yes"}},
            {"label": "🤔 Maybe", "action": "availability", "payload": {"event_id": event_id, "status": "maybe"}},
            {"label": "❌ Can't make it", "action": "availability", "payload": {"event_id": event_id, "status": "no"}},
        ]}
    ]})


def cmd_poll(args, user_id, user_name):
    conn = get_db()
    events = conn.execute("SELECT * FROM events WHERE status = 'planning' ORDER BY date ASC").fetchall()

    if not events:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": "No events in planning phase. Create one with /dinner first!"}]})

    restaurants = conn.execute("SELECT * FROM items WHERE type = 'restaurant' AND archived = 0 ORDER BY name").fetchall()
    conn.close()

    if not restaurants:
        return jsonify({"messages": [{"type": "text", "text": "No restaurants in the database. Add some with /add first!"}]})

    # If only one event, use it directly
    event = events[0]
    event_id = event["id"]

    buttons = [{"label": f"🍽 {r['name']}" + (f" ({r['cuisine']})" if r['cuisine'] else ""),
                "action": "poll_toggle", "payload": {"event_id": event_id, "item_id": r["id"], "name": r["name"]}}
               for r in restaurants[:10]]

    return jsonify({"messages": [
        {"type": "html", "text": f"<b>🗳 Create Poll for: {event['title']}</b>\n\nSelect 2-5 restaurants, then click Start Poll:"},
        {"type": "buttons", "buttons": buttons},
        {"type": "buttons", "buttons": [
            {"label": "🗳 Start Poll", "action": "poll_launch", "payload": {"event_id": event_id}}
        ]}
    ]})


def cmd_status(args, user_id, user_name):
    conn = get_db()
    events = conn.execute("SELECT * FROM events WHERE status IN ('planning', 'polling', 'decided') ORDER BY date ASC").fetchall()

    if not events:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": "No active events. Create one with /dinner!"}]})

    messages = [{"type": "html", "text": "<b>📊 Active Events</b>"}]
    for event in events:
        avail = conn.execute("SELECT * FROM availability WHERE event_id = ?", (event["id"],)).fetchall()
        yes_count = sum(1 for a in avail if a["status"] == "yes")
        maybe_count = sum(1 for a in avail if a["status"] == "maybe")

        emoji = {"planning": "📋", "polling": "🗳", "decided": "✅"}.get(event["status"], "📌")
        text = f"{emoji} <b>{event['title']}</b> (#{event['id']})\n📅 {event['date']} at {event['time']}\nStatus: {event['status'].title()}\nResponses: ✅{yes_count} 🤔{maybe_count}\nBy: {event['created_by_name']}"

        res = conn.execute("SELECT * FROM reservations WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
                           (event["id"],)).fetchone()
        if res:
            text += f"\n\n🔖 <b>Reservation:</b>\n📍 {res['restaurant_name']}\n🕐 {res['time']}"
            if res["confirmation"]:
                text += f"\n✅ {res['confirmation']}"

        messages.append({"type": "html", "text": text})

    conn.close()
    return jsonify({"messages": messages})


def cmd_reserved(args, user_id, user_name):
    if not args:
        return jsonify({"messages": [{"type": "text",
            "text": "Usage: /reserved <event_id> <time> [details]\nExample: /reserved 1 19:30 Table for 8, confirmation #A1234"}]})

    parts = args.split(maxsplit=2)
    try:
        event_id = int(parts[0])
    except ValueError:
        return jsonify({"messages": [{"type": "text", "text": "First argument must be the event ID."}]})

    time_str = parts[1] if len(parts) > 1 else "TBD"
    details = parts[2] if len(parts) > 2 else ""

    conn = get_db()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if not event:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": f"Event #{event_id} not found."}]})

    restaurant_name = "TBD"
    if event["chosen_item_id"]:
        item = conn.execute("SELECT * FROM items WHERE id = ?", (event["chosen_item_id"],)).fetchone()
        if item:
            restaurant_name = item["name"]

    avail = conn.execute("SELECT * FROM availability WHERE event_id = ? AND status = 'yes'", (event_id,)).fetchall()
    party_size = len(avail)

    confirmation = None
    notes = details
    if "#" in details:
        p = details.split("#", 1)
        confirmation = "#" + p[1].split()[0] if p[1] else None
        notes = p[0].strip() or None

    conn.execute(
        "INSERT INTO reservations (event_id, restaurant_name, time, party_size, confirmation, notes, reserved_by_id, reserved_by_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (event_id, restaurant_name, time_str, party_size, confirmation, notes, user_id, user_name)
    )
    conn.execute("UPDATE events SET status = 'decided' WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()

    text = f"🔖 <b>Reservation Confirmed!</b>\n\n📅 <b>{event['title']}</b>\n📍 {restaurant_name}\n🕐 {event['date']} at {time_str}\n👥 Party of {party_size}"
    if confirmation:
        text += f"\n✅ Confirmation: {confirmation}"
    if notes:
        text += f"\n📝 {notes}"
    text += f"\n\n<i>Reserved by {user_name}</i>"

    return jsonify({"messages": [{"type": "html", "text": text}]})


# --- Action Processing ---

def process_action(action, user_id, user_name, payload):
    if action == "add_start":
        return action_add_start(payload, user_id, user_name)
    elif action == "add_save":
        return action_add_save(payload, user_id, user_name)
    elif action == "flag":
        return cmd_flag(str(payload.get("item_id", "")), user_id, user_name)
    elif action == "rate":
        return action_rate(payload, user_id, user_name)
    elif action == "availability":
        return action_availability(payload, user_id, user_name)
    elif action == "poll_toggle":
        return action_poll_toggle(payload, user_id, user_name)
    elif action == "poll_launch":
        return action_poll_launch(payload, user_id, user_name)
    elif action == "vote":
        return action_vote(payload, user_id, user_name)
    elif action == "close_poll":
        return action_close_poll(payload, user_id, user_name)
    elif action == "simulate_rsvps":
        return action_simulate_rsvps(payload, user_id, user_name)
    elif action == "simulate_votes":
        return action_simulate_votes(payload, user_id, user_name)
    else:
        return jsonify({"messages": [{"type": "text", "text": f"Unknown action: {action}"}]})


def action_add_start(payload, user_id, user_name):
    item_type = payload.get("type", "restaurant")

    fields = {"type": item_type}
    messages = [{"type": "html", "text": f"Adding a new <b>{item_type}</b>. Fill in the details:"}]

    if item_type == "restaurant":
        messages.append({"type": "form", "form": {
            "id": "add_item",
            "fields": [
                {"name": "name", "label": "Restaurant Name", "type": "text", "required": True},
                {"name": "cuisine", "label": "Cuisine", "type": "select",
                 "options": ["Austrian", "Italian", "Asian", "Japanese", "Chinese", "Thai",
                            "Indian", "Mexican", "Middle Eastern", "Greek", "French",
                            "American", "Balkan", "Turkish", "Vietnamese", "Korean",
                            "Vegetarian/Vegan", "Seafood", "Brunch/Cafe", "Bar/Drinks", "Other"]},
                {"name": "price_range", "label": "Price Range", "type": "select",
                 "options": ["€", "€€", "€€€", "€€€€"]},
                {"name": "district", "label": "District", "type": "select",
                 "options": [f"{i}." for i in range(1, 24)]},
                {"name": "maps_link", "label": "Google Maps Link", "type": "text", "required": False},
                {"name": "website", "label": "Website", "type": "text", "required": False},
                {"name": "tags", "label": "Tags (comma-separated)", "type": "text", "required": False,
                 "placeholder": "rooftop, datenight, vegan..."},
            ],
            "item_type": "restaurant"
        }})
    elif item_type == "exhibition":
        messages.append({"type": "form", "form": {
            "id": "add_item",
            "fields": [
                {"name": "name", "label": "Exhibition Name", "type": "text", "required": True},
                {"name": "category", "label": "Category", "type": "select",
                 "options": ["Museum", "Gallery", "Concert", "Festival", "Market",
                            "Workshop", "Tour", "Other"]},
                {"name": "district", "label": "District", "type": "select",
                 "options": [f"{i}." for i in range(1, 24)]},
                {"name": "start_date", "label": "Start Date", "type": "date", "required": False},
                {"name": "end_date", "label": "End Date", "type": "date", "required": False},
                {"name": "price_range", "label": "Price", "type": "select",
                 "options": ["Free", "€", "€€", "€€€"]},
                {"name": "maps_link", "label": "Google Maps Link", "type": "text", "required": False},
                {"name": "ticket_link", "label": "Ticket/Website Link", "type": "text", "required": False},
                {"name": "tags", "label": "Tags", "type": "text", "required": False},
            ],
            "item_type": "exhibition"
        }})
    elif item_type == "event":
        messages.append({"type": "form", "form": {
            "id": "add_item",
            "fields": [
                {"name": "name", "label": "Event Name", "type": "text", "required": True},
                {"name": "category", "label": "Category", "type": "select",
                 "options": ["Concert", "Festival", "Market", "Theater", "Cinema",
                            "Nightlife", "Sports", "Workshop", "Other"]},
                {"name": "district", "label": "District", "type": "select",
                 "options": [f"{i}." for i in range(1, 24)]},
                {"name": "start_date", "label": "Event Date", "type": "date", "required": False},
                {"name": "end_date", "label": "End Date (if multi-day)", "type": "date", "required": False},
                {"name": "price_range", "label": "Price", "type": "select",
                 "options": ["Free", "€", "€€", "€€€"]},
                {"name": "maps_link", "label": "Google Maps Link", "type": "text", "required": False},
                {"name": "ticket_link", "label": "Ticket Link", "type": "text", "required": False},
                {"name": "tags", "label": "Tags", "type": "text", "required": False},
            ],
            "item_type": "event"
        }})
    else:  # activity
        messages.append({"type": "form", "form": {
            "id": "add_item",
            "fields": [
                {"name": "name", "label": "Activity Name", "type": "text", "required": True},
                {"name": "category", "label": "Category", "type": "select",
                 "options": ["Museum", "Gallery", "Outdoor/Hiking", "Sports", "Wellness/Spa",
                            "Escape Room", "Theater", "Cinema", "Workshop", "Tour",
                            "Nightlife", "Other"]},
                {"name": "district", "label": "District", "type": "select",
                 "options": [f"{i}." for i in range(1, 24)]},
                {"name": "price_range", "label": "Price", "type": "select",
                 "options": ["Free", "€", "€€", "€€€"]},
                {"name": "maps_link", "label": "Google Maps Link", "type": "text", "required": False},
                {"name": "website", "label": "Website", "type": "text", "required": False},
                {"name": "tags", "label": "Tags", "type": "text", "required": False,
                 "placeholder": "family-friendly, outdoor, rainy-day..."},
            ],
            "item_type": "activity"
        }})

    return jsonify({"messages": messages})


def action_add_save(payload, user_id, user_name):
    item_type = payload.get("item_type", "restaurant")
    name = payload.get("name", "").strip()

    if not name:
        return jsonify({"messages": [{"type": "text", "text": "Name is required!"}]})

    tags = payload.get("tags", "")
    if tags:
        tags = ", ".join(t.strip().lstrip("#") for t in tags.split(","))

    # Parse lat/lng if provided
    lat = payload.get("lat")
    lng = payload.get("lng")
    if lat:
        try: lat = float(lat)
        except (ValueError, TypeError): lat = None
    if lng:
        try: lng = float(lng)
        except (ValueError, TypeError): lng = None

    rec_note = payload.get("recommender_note", "")
    rec_rating = payload.get("recommender_rating")
    if rec_rating:
        try: rec_rating = int(rec_rating)
        except (ValueError, TypeError): rec_rating = None

    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO items (type, name, cuisine, price_range, district, address,
           maps_link, website, ticket_link, category, start_date, end_date, tags,
           lat, lng, added_by_id, added_by_name, recommender_note, recommender_rating)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_type, name, payload.get("cuisine"), payload.get("price_range"),
         payload.get("district"), payload.get("address"), payload.get("maps_link"),
         payload.get("website"), payload.get("ticket_link"), payload.get("category"),
         payload.get("start_date"), payload.get("end_date"), tags,
         lat, lng, user_id, user_name, rec_note, rec_rating)
    )
    item_id = cursor.lastrowid
    conn.commit()
    conn.close()

    emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}.get(item_type, "📌")
    return jsonify({"messages": [
        {"type": "html", "text": f"{emoji} <b>{name}</b> has been added! (ID: #{item_id})\n\nUse /flag {item_id} to express interest!"}
    ]})


def action_rate(payload, user_id, user_name):
    item_id = payload.get("item_id")
    rating = payload.get("rating")

    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO flags (item_id, user_id, user_name, rating) VALUES (?, ?, ?, ?)",
                 (item_id, user_id, user_name, rating))
    conn.commit()
    avg = conn.execute("SELECT AVG(rating) as a FROM flags WHERE item_id = ? AND rating IS NOT NULL",
                       (item_id,)).fetchone()["a"]
    count = conn.execute("SELECT COUNT(*) as c FROM flags WHERE item_id = ?", (item_id,)).fetchone()["c"]
    item = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
    conn.close()

    stars = "⭐" * rating
    return jsonify({"messages": [
        {"type": "html", "text": f"{stars} {user_name} rated <b>{item['name']}</b> {rating}/5\nAverage: {round(avg, 1) if avg else rating}/5 ({count} ratings)"}
    ]})


def action_availability(payload, user_id, user_name):
    event_id = payload.get("event_id")
    status = payload.get("status")

    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO availability (event_id, user_id, user_name, status) VALUES (?, ?, ?, ?)",
                 (event_id, user_id, user_name, status))
    conn.commit()

    avail = conn.execute("SELECT * FROM availability WHERE event_id = ?", (event_id,)).fetchall()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()

    yes_list = [a["user_name"] for a in avail if a["status"] == "yes"]
    maybe_list = [a["user_name"] for a in avail if a["status"] == "maybe"]
    no_list = [a["user_name"] for a in avail if a["status"] == "no"]

    text = (f"<b>📅 {event['title']}</b>\n{event['date']} at {event['time']}\n\n"
            f"✅ In ({len(yes_list)}): {', '.join(yes_list) or 'none yet'}\n"
            f"🤔 Maybe ({len(maybe_list)}): {', '.join(maybe_list) or 'none'}\n"
            f"❌ Can't ({len(no_list)}): {', '.join(no_list) or 'none'}\n\n"
            f"<i>{user_name} marked {status}</i>")

    return jsonify({"messages": [
        {"type": "html", "text": text},
        {"type": "buttons", "buttons": [
            {"label": "✅ I'm in!", "action": "availability", "payload": {"event_id": event_id, "status": "yes"}},
            {"label": "🤔 Maybe", "action": "availability", "payload": {"event_id": event_id, "status": "maybe"}},
            {"label": "❌ Can't", "action": "availability", "payload": {"event_id": event_id, "status": "no"}},
            {"label": "🤖 Simulate others RSVPing", "action": "simulate_rsvps", "payload": {"event_id": event_id}},
        ]}
    ]})


def action_poll_toggle(payload, user_id, user_name):
    # Store selected items in a simple way — return updated selection UI
    return jsonify({"messages": [
        {"type": "html", "text": f"✅ Toggled <b>{payload.get('name', '')}</b> for the poll.\n\n<i>Select your restaurants then click Start Poll.</i>"}
    ]})


def action_poll_launch(payload, user_id, user_name):
    event_id = payload.get("event_id")
    selected_ids = payload.get("selected_ids", [])

    conn = get_db()

    if not selected_ids:
        # Auto-pick top restaurants if none selected
        items = conn.execute("SELECT id FROM items WHERE type = 'restaurant' AND archived = 0 ORDER BY name LIMIT 4").fetchall()
        selected_ids = [i["id"] for i in items]

    if len(selected_ids) < 2:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": "Need at least 2 restaurants for a poll!"}]})

    conn.execute("UPDATE events SET status = 'polling' WHERE id = ?", (event_id,))
    for item_id in selected_ids:
        conn.execute("INSERT INTO poll_options (event_id, item_id) VALUES (?, ?)", (event_id, item_id))
    conn.commit()

    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    options = conn.execute("""
        SELECT po.id as option_id, i.name, i.cuisine, i.price_range, i.district
        FROM poll_options po JOIN items i ON po.item_id = i.id
        WHERE po.event_id = ?
    """, (event_id,)).fetchall()
    conn.close()

    buttons = []
    for opt in options:
        label = f"🍽 {opt['name']}"
        if opt["cuisine"]:
            label += f" ({opt['cuisine']})"
        buttons.append({"label": label, "action": "vote",
                       "payload": {"event_id": event_id, "option_id": opt["option_id"]}})

    return jsonify({"messages": [
        {"type": "html", "text": f"<b>🗳 VOTE: {event['title']}</b>\n📅 {event['date']} at {event['time']}\n\nPick your favorite! (Quorum: {event['quorum']} votes)"},
        {"type": "buttons", "buttons": buttons},
        {"type": "buttons", "buttons": [
            {"label": "🔒 Close Poll", "action": "close_poll", "payload": {"event_id": event_id}},
            {"label": "🤖 Simulate others voting", "action": "simulate_votes", "payload": {"event_id": event_id}},
        ]}
    ]})


def action_vote(payload, user_id, user_name):
    event_id = payload.get("event_id")
    option_id = payload.get("option_id")

    conn = get_db()
    conn.execute("INSERT OR REPLACE INTO votes (event_id, user_id, user_name, poll_option_id) VALUES (?, ?, ?, ?)",
                 (event_id, user_id, user_name, option_id))
    conn.commit()

    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    options = conn.execute("""
        SELECT po.id as option_id, i.name, i.cuisine, COUNT(v.id) as vote_count
        FROM poll_options po JOIN items i ON po.item_id = i.id
        LEFT JOIN votes v ON po.id = v.poll_option_id
        WHERE po.event_id = ?
        GROUP BY po.id ORDER BY vote_count DESC
    """, (event_id,)).fetchall()
    total_votes = conn.execute("SELECT COUNT(DISTINCT user_id) FROM votes WHERE event_id = ?",
                               (event_id,)).fetchone()[0]
    conn.close()

    lines = [f"<b>🗳 VOTE: {event['title']}</b>\n📅 {event['date']} at {event['time']}\n"]
    for opt in options:
        bar = "█" * opt["vote_count"] + "░" * max(0, 5 - opt["vote_count"])
        lines.append(f"🍽 <b>{opt['name']}</b>  [{bar}] {opt['vote_count']}")

    lines.append(f"\nVotes: {total_votes}/{event['quorum']}")
    if total_votes >= event["quorum"]:
        lines.append("✅ <b>Quorum reached!</b> Organizer can close the poll.")
    lines.append(f"\n<i>{user_name} voted!</i>")

    buttons = [{"label": f"🍽 {opt['name']}", "action": "vote",
                "payload": {"event_id": event_id, "option_id": opt["option_id"]}} for opt in options]

    return jsonify({"messages": [
        {"type": "html", "text": "\n".join(lines)},
        {"type": "buttons", "buttons": buttons},
        {"type": "buttons", "buttons": [
            {"label": "🔒 Close Poll", "action": "close_poll", "payload": {"event_id": event_id}},
            {"label": "🤖 Simulate others voting", "action": "simulate_votes", "payload": {"event_id": event_id}},
        ]}
    ]})


def action_close_poll(payload, user_id, user_name):
    event_id = payload.get("event_id")

    conn = get_db()
    options = conn.execute("""
        SELECT po.id as option_id, po.item_id, i.name, i.cuisine, i.maps_link, i.address,
               COUNT(v.id) as vote_count
        FROM poll_options po JOIN items i ON po.item_id = i.id
        LEFT JOIN votes v ON po.id = v.poll_option_id
        WHERE po.event_id = ? GROUP BY po.id ORDER BY vote_count DESC
    """, (event_id,)).fetchall()

    if not options:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": "No votes recorded."}]})

    winner = options[0]
    conn.execute("UPDATE events SET status = 'decided', chosen_item_id = ? WHERE id = ?",
                 (winner["item_id"], event_id))
    conn.commit()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()

    medals = ["🥇", "🥈", "🥉"]
    results = []
    for i, opt in enumerate(options):
        medal = medals[i] if i < 3 else f"{i+1}."
        bar = "█" * opt["vote_count"]
        results.append(f"{medal} <b>{opt['name']}</b> — {opt['vote_count']} votes {bar}")

    location = ""
    if winner["maps_link"]:
        location = f"\n📍 <a href='{winner['maps_link']}'>Google Maps</a>"
    elif winner["address"]:
        location = f"\n📍 {winner['address']}"

    text = (f"<b>🏆 Poll Results: {event['title']}</b>\n\n"
            + "\n".join(results)
            + f"\n\n🎉 <b>Winner: {winner['name']}!</b>{location}"
            + f"\n\nUse /reserved {event_id} [time] [details] to confirm the reservation!")

    return jsonify({"messages": [{"type": "html", "text": text}]})


def action_simulate_rsvps(payload, user_id, user_name):
    """Simulate other group members RSVPing for testing."""
    import random
    event_id = payload.get("event_id")
    conn = get_db()

    for member in GROUP_MEMBERS[1:]:  # Skip "You"
        status = random.choice(["yes", "yes", "yes", "maybe", "no"])
        conn.execute("INSERT OR REPLACE INTO availability (event_id, user_id, user_name, status) VALUES (?, ?, ?, ?)",
                     (event_id, member["id"], member["name"], status))
    conn.commit()

    avail = conn.execute("SELECT * FROM availability WHERE event_id = ?", (event_id,)).fetchall()
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()

    yes_list = [a["user_name"] for a in avail if a["status"] == "yes"]
    maybe_list = [a["user_name"] for a in avail if a["status"] == "maybe"]
    no_list = [a["user_name"] for a in avail if a["status"] == "no"]

    text = (f"🤖 <b>Simulated RSVPs for {event['title']}</b>\n\n"
            f"✅ In ({len(yes_list)}): {', '.join(yes_list)}\n"
            f"🤔 Maybe ({len(maybe_list)}): {', '.join(maybe_list)}\n"
            f"❌ Can't ({len(no_list)}): {', '.join(no_list)}")

    return jsonify({"messages": [{"type": "html", "text": text}]})


def action_simulate_votes(payload, user_id, user_name):
    """Simulate other group members voting for testing."""
    import random
    event_id = payload.get("event_id")
    conn = get_db()

    options = conn.execute("SELECT id FROM poll_options WHERE event_id = ?", (event_id,)).fetchall()
    if not options:
        conn.close()
        return jsonify({"messages": [{"type": "text", "text": "No poll options found."}]})

    option_ids = [o["id"] for o in options]
    for member in GROUP_MEMBERS[1:8]:  # Simulate 7 others voting
        chosen = random.choice(option_ids)
        conn.execute("INSERT OR REPLACE INTO votes (event_id, user_id, user_name, poll_option_id) VALUES (?, ?, ?, ?)",
                     (event_id, member["id"], member["name"], chosen))
    conn.commit()

    # Show updated results
    results = conn.execute("""
        SELECT po.id as option_id, i.name, COUNT(v.id) as vote_count
        FROM poll_options po JOIN items i ON po.item_id = i.id
        LEFT JOIN votes v ON po.id = v.poll_option_id
        WHERE po.event_id = ? GROUP BY po.id ORDER BY vote_count DESC
    """, (event_id,)).fetchall()
    total = conn.execute("SELECT COUNT(DISTINCT user_id) FROM votes WHERE event_id = ?", (event_id,)).fetchone()[0]
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    conn.close()

    lines = [f"🤖 <b>Simulated votes for {event['title']}</b>\n"]
    for opt in results:
        bar = "█" * opt["vote_count"] + "░" * max(0, 5 - opt["vote_count"])
        lines.append(f"🍽 <b>{opt['name']}</b>  [{bar}] {opt['vote_count']}")
    lines.append(f"\nTotal: {total} votes")
    if total >= event["quorum"]:
        lines.append("✅ <b>Quorum reached!</b>")

    buttons = [{"label": "🔒 Close Poll & See Winner", "action": "close_poll", "payload": {"event_id": event_id}}]

    return jsonify({"messages": [
        {"type": "html", "text": "\n".join(lines)},
        {"type": "buttons", "buttons": buttons}
    ]})


def format_item_card(item):
    emoji = {"restaurant": "🍽", "exhibition": "🖼", "event": "🎉", "activity": "🎯"}.get(item.get("type", ""), "📌")
    card = {
        "id": item["id"],
        "type": item["type"],
        "emoji": emoji,
        "name": item["name"],
        "details": [],
    }
    if item.get("cuisine"):
        card["details"].append(item["cuisine"])
    if item.get("category"):
        card["details"].append(item["category"])
    if item.get("price_range"):
        card["details"].append(item["price_range"])
    if item.get("district"):
        card["details"].append(f"District {item['district']}")
    if item.get("start_date"):
        dates = item["start_date"]
        if item.get("end_date"):
            dates += f" → {item['end_date']}"
        card["dates"] = dates
    if item.get("tags"):
        card["tags"] = [f"#{t.strip()}" for t in item["tags"].split(",")]
    if item.get("maps_link"):
        card["maps_link"] = item["maps_link"]
    if item.get("address"):
        card["address"] = item["address"]
    if item.get("website"):
        card["website"] = item["website"]
    if item.get("ticket_link"):
        card["ticket_link"] = item["ticket_link"]
    card["added_by"] = item.get("added_by_name", "Unknown")
    return card


# Initialize DB on import (needed for gunicorn on Render)
try:
    init_db()
    seed_museums()
except Exception as e:
    print(f"DB init warning: {e}")

if __name__ == "__main__":
    print("Database initialized.")
    print("Starting Vienna Group Planner prototype...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=False, host="0.0.0.0", port=5000)
