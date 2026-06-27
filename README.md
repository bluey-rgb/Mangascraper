# 📚 Manga Tracker

A small local web app that tracks manga/manhwa series from **AsuraScans** so you
can see new chapters and read them all in one place — no more checking the site
manually.

This is a first-project-friendly codebase: one small Python web app, a single
SQLite file for storage, and plain HTML pages.

---

## What it does

- **Add a series** by pasting its AsuraScans URL.
- **Library view** showing every series you track, with a **NEW** badge when
  there are unread new chapters.
- **Read chapters in the browser** — pages are shown top to bottom.
- **Check for new chapters** with one button; anything that appeared since you
  added it gets flagged **NEW**.
- Opening a chapter marks it **read**.

---

## How to run it

You only need Python 3.9+ (already on your Mac).

```bash
# 1. From the project folder, create a virtual environment (one time)
python3 -m venv venv

# 2. Install the dependencies (one time)
./venv/bin/pip install -r requirements.txt

# 3. Start the app (every time you want to use it)
./venv/bin/uvicorn app.main:app --reload
```

Then open **http://localhost:8000** in your browser.

To stop the app, press `Ctrl+C` in the terminal.

> **Tip:** Find a series on https://asurascans.com, open its page, and copy the
> URL from the address bar (it looks like
> `https://asurascans.com/comics/<name>-<code>`). Paste that into "Add a series".

---

## How it's built (a quick tour)

```
app/
  main.py            # The web app: all the pages and buttons
  database.py        # Sets up the SQLite database (data/manga.db)
  scraper/
    fetch.py         # Downloads pages while pretending to be Chrome (beats Cloudflare)
    asura.py         # Reads titles, chapter lists, and page images from AsuraScans
    base.py          # A shared shape so more sites can be added later
  templates/         # The HTML pages you see
  static/style.css   # The styling
data/manga.db        # Your library (created automatically; safe to delete to reset)
```

### Two things worth understanding

1. **Cloudflare** — AsuraScans blocks ordinary bots. `fetch.py` uses
   `curl_cffi` to imitate a real Chrome browser, which gets past it.
2. **The image proxy** (`/img` in `main.py`) — the app downloads each chapter
   image itself (with the right headers) and re-serves it to your browser. This
   keeps images working even if the site adds hotlink protection later.

---

## Adding another site later

Copy `app/scraper/asura.py` to a new file, change the parsing to match the new
site's HTML, and call `register(...)` at the bottom. The rest of the app
(library, reader, refresh) works automatically because every scraper shares the
same shape defined in `base.py`.

---

## Please use this responsibly

This is for **personal use only**. The app already waits a moment between
requests and only checks for updates when you click the button — please keep it
that way so you don't overload the site or get your IP blocked. Don't
redistribute anything you download.
