"""Run the dashboard and the Telegram bot in ONE program.

Hosts such as Render give you a single start command per service, so this file
starts the web dashboard in a background thread and the bot in the main thread.

Start command on the host:  python run_all.py
(On your own computer you can keep using bot.py and dashboard.py in two windows.)
"""
import os
import threading

from dotenv import load_dotenv

load_dotenv()

import bot  # noqa: E402
import dashboard  # noqa: E402
import db  # noqa: E402


def serve_dashboard():
    from waitress import serve

    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    # Hosts like Render tell the app which port to use through PORT.
    port = int(os.environ.get("PORT") or os.environ.get("DASHBOARD_PORT") or 8000)
    print(f"Dashboard listening on {host}:{port}", flush=True)
    serve(dashboard.app, host=host, port=port)


if __name__ == "__main__":
    if not dashboard.password():
        raise SystemExit("DASHBOARD_PASSWORD is missing. Add it in the host's environment variables.")
    db.init_db()
    threading.Thread(target=serve_dashboard, daemon=True).start()
    bot.main()  # runs in the main thread, as python-telegram-bot requires
