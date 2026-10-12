# Salon booking bot and dashboard

A Telegram bot where customers book salon appointments (English and Amharic), plus a small web dashboard where the salon manages the day. No payments in this version.

## What is inside

| File | Job |
|---|---|
| `bot.py` | The Telegram bot: booking flow, my bookings, cancel and reschedule, reminders, owner alerts |
| `dashboard.py` + `templates/` + `static/` | The web dashboard for the salon |
| `db.py` | The database (SQLite file, or PostgreSQL when `DATABASE_URL` is set), the free-time calculation and the double-booking protection |
| `run_all.py` | Starts the dashboard and the bot together (used on hosts with one start command) |
| `texts.py` | Every customer-facing message in English and Amharic |
| `tg.py` | Lets the dashboard message a customer when the salon cancels |
| `tests/` | Automated tests and an offline bot simulation |

The bot and the dashboard are two programs that share one database file (`salon.db`).

## 1. Create the bot on Telegram

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Choose a name and a username ending in `bot`.
3. Copy the token it gives you.

## 2. Install

You need Python 3.10 or newer.

```
python -m venv .venv
.venv\Scripts\activate          (Windows)
source .venv/bin/activate       (Mac or Linux)
pip install -r requirements.txt
```

## 3. Configure

Copy `.env.example` to `.env` and fill it in:

- `BOT_TOKEN`: the token from BotFather.
- `DASHBOARD_PASSWORD`: a long password for the dashboard.
- `SECRET_KEY`: any long random text.
- `OWNER_CHAT_ID`: leave empty for now.

## 4. Run

Open two terminals (both with the virtual environment active):

```
python bot.py
python dashboard.py
```

Open http://127.0.0.1:8000 and sign in.

## 5. Get alerts for new bookings

1. Message your bot on Telegram and send `/myid`. It replies with a number.
2. Put that number in `.env` as `OWNER_CHAT_ID`.
3. Restart `bot.py`.

From then on you get a Telegram message whenever a customer books, reschedules or cancels. To alert several people, make a Telegram group, add the bot, and use the group's chat ID (send `/myid` inside the group).

## 6. Set up your salon (in the dashboard)

1. **Hours and details**: salon name, phone, address, opening hours, closed days.
2. **Services**: replace the three sample services with yours. Add the Amharic name so Amharic customers see it.
3. **Stylists**: add each stylist and the days they work.
4. Open your bot on Telegram and make a test booking.

## Testing without Telegram

```
python -m unittest discover -s tests -v
python tests/simulate_bot.py
```

To run the same checks against PostgreSQL, set `DATABASE_URL` first. The tests wipe that database, so use an empty test one.

The first runs 18 checks on the database and dashboard. The second drives the real bot handlers with fake Telegram messages and prints what a customer would see.

## Keeping your data on a host that restarts (Render and similar)

Free hosts such as Render erase local files when they restart, which would delete `salon.db`. To avoid that, give the app a hosted PostgreSQL database:

1. Create a free database (for example at neon.com) and copy its connection address. It starts with `postgresql://` and ends with `sslmode=require`.
2. On the host, add an environment variable named `DATABASE_URL` with that address. Keep it secret.
3. Redeploy. The app now stores everything in that database instead of `salon.db`. Tables are created automatically on first start.

When `DATABASE_URL` is empty, the app keeps using the local `salon.db` file.

To keep a sleeping free host awake, point a free uptime monitor at `https://YOUR-ADDRESS/healthz`. It answers `ok` and does not touch the database.

## Keeping it running

On your own computer the bot only works while both programs are running. For real use, run them on a cheap always-on server (a small VPS) or a spare PC that stays on. Use a service manager (for example `systemd` on Linux) so they restart after a reboot.

If the dashboard is reachable from the internet, put it behind HTTPS (Caddy or Cloudflare Tunnel are the easiest options) and use a strong password. By default it only listens on your own computer (`127.0.0.1`).

## Backups

Everything lives in `salon.db` (plus `salon.db-wal` while running). Copy it somewhere safe every day.

## Known limits of version 1

- One salon per installation.
- Times are shown in the 24-hour Western clock (09:00, 14:30). Many Ethiopians say time on the Ethiopian clock (6 hours different), so the bot and your staff must agree which one is used.
- Dates use the Gregorian calendar (Wed 7/10). Ethiopian calendar dates are not supported yet.
- The Amharic text should be checked by a native speaker.
- No payments, deposits or no-show penalties.
- Telegram bots can't message someone who hasn't started the bot, so customers must open the bot themselves first.
