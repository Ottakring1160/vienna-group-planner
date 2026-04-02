# Vienna Group Planner — Friend's Guide

## The App

**Live:** https://the-jee-plan.onrender.com
**Code:** https://github.com/Ottakring1160/vienna-group-planner

A group planner for our crew in Vienna — restaurants, events, trips, and more.

---

## How to Use the App

### Add Restaurants
1. Go to **Restaurants** tab
2. Type a restaurant name (e.g. "Plachutta Wollzeile") in the search bar and click **Add from Maps**
3. It auto-fills everything from Google — cuisine, price, district, address, map pin
4. Add your personal note and rating before saving
5. You can also **Bulk Import** — paste multiple names, one per line

### What's On in Vienna
- Browse concerts, comedy, exhibitions, festivals, markets
- Click **"I'm interested"** so the group sees who wants to go
- **Share** sends it to WhatsApp
- Add events you find with **+ Add Event**

### Plan an Outing
1. Click **Plan Outing** in the sidebar
2. Pick type: Restaurant (brunch/lunch/dinner), Day Trip, Overnight, or Week Trip
3. Fill in the details — destination, dates, transport, accommodation, activities
4. Hit **Send via WhatsApp** — it generates a formatted message for the group

### Restaurant Features
- **Shortlist** — your personal "want to go" list
- **Vouch** — endorse a restaurant with a note ("Best schnitzel in Vienna!")
- **Rate Visit** — after going, rate it 1-5 stars. Feeds into the Leaderboard
- **Delete** — remove restaurants you added by mistake (trash icon)

### Leaderboard
Who has the best taste? Rankings based on how the group rates your recommendations.

---

## How to Contribute to the Code

### Quick Edits (no setup needed)
1. Go to https://github.com/Ottakring1160/vienna-group-planner
2. Navigate to the file you want to edit
3. Click the pencil icon to edit
4. Make your changes
5. Click **Commit changes** — Render auto-deploys in ~60 seconds

### Local Development
```bash
# Clone the repo
git clone https://github.com/Ottakring1160/vienna-group-planner.git
cd vienna-group-planner

# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py
# Open http://localhost:5000
```

### Key Files
| File | What it does |
|---|---|
| `app.py` | Backend — all API routes, database, Google Maps integration |
| `templates/app.html` | Frontend — all pages, JavaScript, UI |
| `static/style.css` | Styling — CSS variables, components, layout |
| `requirements.txt` | Python dependencies |

### Project Structure
- **Database:** PostgreSQL on Render (persistent), SQLite locally
- **Frontend:** Single-page app with vanilla JS (no framework)
- **Maps:** Leaflet.js with CARTO Voyager tiles
- **Restaurant data:** Google Places API (key set in Render env vars)
- **Deployment:** Auto-deploys from GitHub to Render on every push

### Environment Variables (on Render)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Render) |
| `GOOGLE_MAPS_API_KEY` | Google Places API for restaurant lookup |

### Making Changes
1. Create a branch: `git checkout -b my-feature`
2. Make your changes
3. Test locally: `python app.py`
4. Push: `git push origin my-feature`
5. Create a Pull Request on GitHub
6. Once merged to `master`, Render auto-deploys

---

## Ideas for Contributions
- Add new restaurant cuisines/categories
- Improve the map design or add clustering
- Add new Vienna events
- Build a proper voting/polling system
- Add photo uploads for restaurants
- Improve mobile responsive design
- Add dark mode toggle
- Build WhatsApp webhook for incoming votes
