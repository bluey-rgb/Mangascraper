"""App configuration, read from environment variables.

Keeping config here means the app behaves the same whether you run it locally
or in Docker — you just set the variables differently (a .env file for Docker,
or `VAR=value` on the command line locally).
"""
import os
import secrets
from pathlib import Path

# The password required to log in. There is no default on purpose: the site
# should never be reachable without one.
APP_PASSWORD = os.environ.get("APP_PASSWORD", "").strip()

# Secret used to sign the login cookie. If you don't set one, a random key is
# generated at startup — that works, but everyone gets logged out whenever the
# app restarts. Set SECRET_KEY in your .env to keep sessions stable.
SECRET_KEY = os.environ.get("SECRET_KEY", "").strip() or secrets.token_hex(32)

# Where the SQLite database lives. In Docker this points at a mounted volume so
# your library survives container restarts.
DB_PATH = Path(
    os.environ.get(
        "DB_PATH",
        str(Path(__file__).resolve().parent.parent / "data" / "manga.db"),
    )
)


def require_password() -> str:
    """Return the configured password, or raise a clear error if it's missing."""
    if not APP_PASSWORD:
        raise RuntimeError(
            "APP_PASSWORD is not set. Set it before starting the app, e.g.\n"
            "  APP_PASSWORD=your-secret ./venv/bin/uvicorn app.main:app\n"
            "or put it in a .env file when using Docker."
        )
    return APP_PASSWORD
