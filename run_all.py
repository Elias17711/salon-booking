"""Run the dashboard and the Telegram bot in ONE program."""
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
    port = int(os.environ.get("PORT") or os.environ.get("DASHBOARD_PORT") or 8000)
    print(f"Dashboard listening on {host}:{port}", flush=True)
    serve(dashboard.app, host=host, port=port)


if __name__ == "__main__":
    if not dashboard.password():
        raise SystemExit("DASHBOARD_PASSWORD is missing. Add it in the host's environment variables.")
    db.init_db()
    threading.Thread(target=serve_dashboard, daemon=True).start()
    bot.main()