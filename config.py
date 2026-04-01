import os

# Telegram Bot Token — get from @BotFather on Telegram
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Group settings
DEFAULT_QUORUM = 6  # Minimum votes before a poll can auto-close
FLAG_THRESHOLD = 5  # Number of flags before bot nudges the group

# Reminder settings (hours before event)
REMINDER_HOURS = [24, 2]

# Vienna districts (1-23)
VIENNA_DISTRICTS = [f"{i}." for i in range(1, 24)]

# Cuisine categories
CUISINES = [
    "Austrian", "Italian", "Asian", "Japanese", "Chinese", "Thai",
    "Indian", "Mexican", "Middle Eastern", "Greek", "French",
    "American", "Balkan", "Turkish", "Vietnamese", "Korean",
    "Vegetarian/Vegan", "Seafood", "Brunch/Cafe", "Bar/Drinks", "Other"
]

# Price ranges
PRICE_RANGES = ["€", "€€", "€€€", "€€€€"]

# Item types
ITEM_TYPES = ["restaurant", "exhibition", "event", "activity"]

# Activity categories
ACTIVITY_CATEGORIES = [
    "Museum", "Gallery", "Concert", "Festival", "Market",
    "Outdoor/Hiking", "Sports", "Wellness/Spa", "Escape Room",
    "Theater", "Cinema", "Workshop", "Tour", "Nightlife", "Other"
]

# Weekly digest day (0=Monday, 6=Sunday)
DIGEST_DAY = 0  # Monday
DIGEST_HOUR = 10  # 10 AM
