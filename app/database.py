"""SQLite storage for tracked series and their chapters.

We use Python's built-in `sqlite3` module so there is nothing extra to install.
The whole database lives in a single file: data/manga.db
"""
import sqlite3
from pathlib import Path

# Path to the database file (created automatically on first run).
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "manga.db"


def get_connection() -> sqlite3.Connection:
    """Open a connection to the database.

    `row_factory = sqlite3.Row` lets us read columns by name (row["title"])
    instead of by number, which is much easier to read.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Enforce foreign keys so deleting a series removes its chapters too.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the tables if they don't exist yet. Safe to call every startup."""
    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS series (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            title           TEXT    NOT NULL,
            source          TEXT    NOT NULL,             -- e.g. "asurascans"
            source_url      TEXT    NOT NULL UNIQUE,      -- the series page URL
            cover_url       TEXT,
            last_checked_at TEXT                          -- ISO timestamp, or NULL
        );

        CREATE TABLE IF NOT EXISTS chapters (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id  INTEGER NOT NULL,
            number     TEXT    NOT NULL,                  -- kept as text: "10.5" exists
            title      TEXT,
            url        TEXT    NOT NULL,
            is_read    INTEGER NOT NULL DEFAULT 0,        -- 0 = unread, 1 = read
            is_new     INTEGER NOT NULL DEFAULT 0,        -- 1 = added by a refresh
            added_at   TEXT,
            UNIQUE (series_id, url),
            FOREIGN KEY (series_id) REFERENCES series (id) ON DELETE CASCADE
        );
        """
    )
    conn.commit()
    conn.close()
