# 📚 Manga Tracker

A small, password-protected website that tracks manga/manhwa series from
**AsuraScans** so you can see new chapters and read them all in one place — no
more checking the site manually. Run it on your own machine and reach it from
your phone, tablet, or laptop.

This is a first-project-friendly codebase: one small Python web app, a single
SQLite file for storage, and plain HTML pages.

> **Why self-host at home?** AsuraScans is behind Cloudflare. The app gets past
> it by imitating a real browser, which works reliably from a home (residential)
> internet connection. Cloud datacenter IPs are blocked by Cloudflare far more
> often, so running it at home is the most dependable setup.

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

## Deploy it (self-host with Docker) — recommended

This is the easiest way to run it 24/7 at home (on a spare laptop, a mini PC, a
Raspberry Pi, etc.). You need [Docker](https://docs.docker.com/get-docker/)
installed on that machine.

```bash
# 1. Create your settings file and edit in a password + secret
cp .env.example .env
#    open .env and set APP_PASSWORD and SECRET_KEY
#    (generate a secret: python3 -c "import secrets; print(secrets.token_hex(32))")

# 2. Build and start it (runs in the background, restarts automatically)
docker compose up -d --build
```

That's it. The site is now running on port **8000**.

**Reach it from your other devices** (same home Wi-Fi): find the host machine's
local IP (e.g. `192.168.1.50`) and visit `http://192.168.1.50:8000` from your
phone or laptop. Log in with the password you set.

- View logs: `docker compose logs -f`
- Stop it: `docker compose down`
- Update after code changes: `docker compose up -d --build`

Your library is stored in `./data/manga.db` on the host, so it survives restarts
and rebuilds.

> **Want to reach it from outside your home too?** The simplest safe option is a
> tunnel like [Tailscale](https://tailscale.com/) (private, just your devices)
> or a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/).
> Avoid opening port 8000 directly to the internet.

---

## Run it locally without Docker (for development)

You only need Python 3.9+ (already on your Mac).

```bash
# 1. From the project folder, create a virtual environment (one time)
python3 -m venv venv

# 2. Install the dependencies (one time)
./venv/bin/pip install -r requirements.txt

# 3. Start the app (set a password for this run)
APP_PASSWORD=your-secret ./venv/bin/uvicorn app.main:app --reload
```

Then open **http://localhost:8000** and log in with that password.

To stop the app, press `Ctrl+C` in the terminal.

> **Tip:** Find a series on https://asurascans.com, open its page, and copy the
> URL from the address bar (it looks like
> `https://asurascans.com/comics/<name>-<code>`). Paste that into "Add a series".

---

## How it's built (a quick tour)

```
app/
  main.py            # The web app: all the pages, buttons, and login
  config.py          # Reads settings (password, secret, DB path) from the environment
  database.py        # Sets up the SQLite database
  scraper/
    fetch.py         # Downloads pages while pretending to be Chrome (beats Cloudflare)
    asura.py         # Reads titles, chapter lists, and page images from AsuraScans
    base.py          # A shared shape so more sites can be added later
  templates/         # The HTML pages you see (incl. login.html)
  static/style.css   # The styling
Dockerfile           # How to package the app into a container
docker-compose.yml   # One-command run, with a persistent data volume
.env.example         # Template for your password + secret (copy to .env)
data/manga.db        # Your library (created automatically; safe to delete to reset)
```

### Two things worth understanding

1. **Cloudflare** — AsuraScans blocks ordinary bots. `fetch.py` uses
   `curl_cffi` to imitate a real Chrome browser, which gets past it.
2. **The image proxy** (`/img` in `main.py`) — the app downloads each chapter
   image itself (with the right headers) and re-serves it to your browser. This
   keeps images working even if the site adds hotlink protection later.
3. **The login** — every page is behind a password (set via `APP_PASSWORD`). A
   small middleware in `main.py` redirects you to `/login` until you sign in, so
   the site stays private even if it's reachable on your network.

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
