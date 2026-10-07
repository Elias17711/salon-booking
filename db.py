"""SQLite data layer shared by the Telegram bot and the web dashboard.

All times are stored as local Addis Ababa time in the text format
"YYYY-MM-DD HH:MM", which sorts correctly as plain text.
"""
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

TZ = timezone(timedelta(hours=3))  # Africa/Addis_Ababa, no daylight saving
FMT = "%Y-%m-%d %H:%M"
BLOCKING = "('confirmed','done')"  # statuses that occupy a time slot

DEFAULT_SETTINGS = {
    "salon_name": "My Salon",
    "address": "",
    "phone": "",
    "open_time": "09:00",
    "close_time": "19:00",
    "closed_days": "6",     # weekday numbers, Monday=0 ... Sunday=6
    "slot_step": "30",      # minutes between bookable start times
    "cancel_hours": "2",    # customers can't cancel/reschedule inside this window
    "min_lead_min": "30",   # earliest bookable time from now
    "booking_days": "7",    # how many days ahead customers can book
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY, name_en TEXT NOT NULL, name_am TEXT DEFAULT '',
  duration_min INTEGER NOT NULL, price REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS staff (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL,
  work_days TEXT NOT NULL DEFAULT '0,1,2,3,4,5', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS customers (
  chat_id INTEGER PRIMARY KEY, name TEXT DEFAULT '', phone TEXT DEFAULT '', lang TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS bookings (
  id INTEGER PRIMARY KEY, chat_id INTEGER, customer_name TEXT DEFAULT '', phone TEXT DEFAULT '',
  service_id INTEGER, staff_id INTEGER NOT NULL,
  start_at TEXT NOT NULL, end_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'confirmed',   -- confirmed | done | no_show | cancelled
  source TEXT NOT NULL DEFAULT 'bot',         -- bot | walkin | block
  note TEXT DEFAULT '',
  reminded_day INTEGER NOT NULL DEFAULT 0, reminded_soon INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_bookings_staff_start ON bookings(staff_id, start_at);
CREATE INDEX IF NOT EXISTS idx_bookings_chat ON bookings(chat_id, start_at);
"""

BOOKING_SELECT = """
SELECT b.*, s.name_en AS service_en, s.name_am AS service_am, s.price AS price,
       st.name AS staff_name
FROM bookings b
LEFT JOIN services s ON s.id = b.service_id
LEFT JOIN staff st ON st.id = b.staff_id
"""


def db_path():
    return os.environ.get("DB_PATH", "salon.db")


def now():
    """Current local time in Addis Ababa as a naive datetime."""
    return datetime.now(TZ).replace(tzinfo=None)


@contextmanager
def conn():
    c = sqlite3.connect(db_path(), timeout=10, isolation_level=None)  # autocommit
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()


def fmt(dt):
    return dt.strftime(FMT)


def parse(text):
    return datetime.strptime(text, FMT)


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        if not c.execute("SELECT 1 FROM services LIMIT 1").fetchone():
            # Sample data so the bot works on first run. Edit these in the dashboard.
            for en, am, mins, price in [("Haircut", "የፀጉር ቁርጥ", 30, 300),
                                        ("Braids", "ሹሩባ", 120, 800),
                                        ("Manicure", "የጥፍር ውበት", 45, 250)]:
                c.execute("INSERT INTO services(name_en, name_am, duration_min, price) VALUES(?,?,?,?)",
                          (en, am, mins, price))
        if not c.execute("SELECT 1 FROM staff LIMIT 1").fetchone():
            c.execute("INSERT INTO staff(name) VALUES('Stylist 1')")


# ---------- settings ----------
def get_settings():
    with conn() as c:
        data = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
    return {**DEFAULT_SETTINGS, **data}


def set_settings(values):
    with conn() as c:
        for k, v in values.items():
            if k in DEFAULT_SETTINGS:
                c.execute("INSERT INTO settings(key, value) VALUES(?, ?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))


# ---------- services ----------
def list_services(active_only=True):
    sql = "SELECT * FROM services" + (" WHERE active=1" if active_only else "") + " ORDER BY id"
    with conn() as c:
        return c.execute(sql).fetchall()


def get_service(sid):
    with conn() as c:
        return c.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()


def add_service(name_en, name_am, minutes, price):
    with conn() as c:
        c.execute("INSERT INTO services(name_en, name_am, duration_min, price) VALUES(?,?,?,?)",
                  (name_en, name_am, minutes, price))


def update_service(sid, name_en, name_am, minutes, price):
    with conn() as c:
        c.execute("UPDATE services SET name_en=?, name_am=?, duration_min=?, price=? WHERE id=?",
                  (name_en, name_am, minutes, price, sid))


def toggle_service(sid):
    with conn() as c:
        c.execute("UPDATE services SET active = 1 - active WHERE id=?", (sid,))


# ---------- staff ----------
def list_staff(active_only=True):
    sql = "SELECT * FROM staff" + (" WHERE active=1" if active_only else "") + " ORDER BY id"
    with conn() as c:
        return c.execute(sql).fetchall()


def get_staff(stid):
    with conn() as c:
        return c.execute("SELECT * FROM staff WHERE id=?", (stid,)).fetchone()


def add_staff(name, work_days):
    with conn() as c:
        c.execute("INSERT INTO staff(name, work_days) VALUES(?,?)", (name, work_days))


def update_staff(stid, name, work_days):
    with conn() as c:
        c.execute("UPDATE staff SET name=?, work_days=? WHERE id=?", (name, work_days, stid))


def toggle_staff(stid):
    with conn() as c:
        c.execute("UPDATE staff SET active = 1 - active WHERE id=?", (stid,))


# ---------- customers ----------
def get_customer(chat_id):
    with conn() as c:
        return c.execute("SELECT * FROM customers WHERE chat_id=?", (chat_id,)).fetchone()


def upsert_customer(chat_id, name=None, phone=None, lang=None):
    with conn() as c:
        c.execute("INSERT OR IGNORE INTO customers(chat_id) VALUES(?)", (chat_id,))
        for col, val in (("name", name), ("phone", phone), ("lang", lang)):
            if val is not None:
                c.execute(f"UPDATE customers SET {col}=? WHERE chat_id=?", (val, chat_id))


# ---------- availability ----------
def _hhmm(text):
    h, m = text.split(":")
    return timedelta(hours=int(h), minutes=int(m))


def free_slots(day, service_id, staff_id=None):
    """Return [(\"HH:MM\", staff_id), ...] of bookable start times on `day`.

    With staff_id=None, each time is offered if ANY working stylist is free and
    the first free stylist is assigned.
    """
    s = get_settings()
    wd = str(day.weekday())
    if wd in s["closed_days"].split(","):
        return []
    svc = get_service(service_id)
    if not svc:
        return []
    dur = timedelta(minutes=svc["duration_min"])
    step = timedelta(minutes=max(5, int(s["slot_step"])))
    midnight = datetime.combine(day, datetime.min.time())
    opens, closes = midnight + _hhmm(s["open_time"]), midnight + _hhmm(s["close_time"])
    earliest = now() + timedelta(minutes=int(s["min_lead_min"]))

    candidates = [get_staff(staff_id)] if staff_id else list_staff()
    staff = [x for x in candidates if x and x["active"] and wd in x["work_days"].split(",")]
    busy = {}
    with conn() as c:
        for x in staff:
            rows = c.execute(
                f"SELECT start_at, end_at FROM bookings WHERE staff_id=? AND status IN {BLOCKING} "
                "AND substr(start_at,1,10)=?", (x["id"], day.isoformat())).fetchall()
            busy[x["id"]] = [(parse(r["start_at"]), parse(r["end_at"])) for r in rows]

    slots = {}
    t = opens
    while t + dur <= closes:
        if t >= earliest:
            for x in staff:
                if all(t + dur <= b0 or t >= b1 for b0, b1 in busy[x["id"]]):
                    slots.setdefault(t.strftime("%H:%M"), x["id"])
                    break
        t += step
    return sorted(slots.items())


# ---------- bookings ----------
def create_booking(*, staff_id, start, minutes, service_id=None, chat_id=None,
                   name="", phone="", source="bot", note=""):
    """Insert a booking unless it overlaps another one for the same stylist.

    Returns the new booking id, or None if the time is no longer free. The check
    and the insert run in one write transaction, so two customers can't both win.
    """
    end = start + timedelta(minutes=minutes)
    n = now()
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            clash = c.execute(
                f"SELECT 1 FROM bookings WHERE staff_id=? AND status IN {BLOCKING} "
                "AND start_at < ? AND end_at > ?", (staff_id, fmt(end), fmt(start))).fetchone()
            if clash:
                c.execute("ROLLBACK")
                return None
            cur = c.execute(
                "INSERT INTO bookings(chat_id, customer_name, phone, service_id, staff_id, start_at, end_at,"
                " source, note, reminded_day, reminded_soon, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (chat_id, name, phone, service_id, staff_id, fmt(start), fmt(end), source, note,
                 1 if start - n <= timedelta(hours=24) else 0,
                 1 if start - n <= timedelta(hours=2) else 0, fmt(n)))
            c.execute("COMMIT")
            return cur.lastrowid
        except Exception:
            c.execute("ROLLBACK")
            raise


def get_booking(bid):
    with conn() as c:
        return c.execute(BOOKING_SELECT + " WHERE b.id=?", (bid,)).fetchone()


def set_status(bid, status):
    with conn() as c:
        c.execute("UPDATE bookings SET status=? WHERE id=?", (status, bid))


def bookings_for_day(day):
    with conn() as c:
        return c.execute(BOOKING_SELECT + " WHERE substr(b.start_at,1,10)=? "
                         "ORDER BY b.start_at, st.name", (day.isoformat(),)).fetchall()


def upcoming_for_customer(chat_id):
    with conn() as c:
        return c.execute(BOOKING_SELECT + " WHERE b.chat_id=? AND b.status='confirmed' AND b.start_at>=? "
                         "ORDER BY b.start_at", (chat_id, fmt(now()))).fetchall()


def due_reminders():
    """Return [(booking_row, 'day' | 'soon'), ...] that should be sent now."""
    n = now()
    out = []
    with conn() as c:
        base = BOOKING_SELECT + (" WHERE b.status='confirmed' AND b.chat_id IS NOT NULL "
                                 "AND b.start_at > ? AND b.start_at <= ? ")
        for r in c.execute(base + "AND b.reminded_day=0", (fmt(n), fmt(n + timedelta(hours=24)))):
            out.append((r, "day"))
        for r in c.execute(base + "AND b.reminded_soon=0", (fmt(n), fmt(n + timedelta(hours=2)))):
            out.append((r, "soon"))
    return out


def mark_reminded(bid, kind):
    col = "reminded_day" if kind == "day" else "reminded_soon"
    with conn() as c:
        c.execute(f"UPDATE bookings SET {col}=1 WHERE id=?", (bid,))
        if kind == "soon":  # a 2-hour reminder makes the 24-hour one pointless
            c.execute("UPDATE bookings SET reminded_day=1 WHERE id=?", (bid,))


# ---------- numbers for the dashboard ----------
def stats(days=7):
    n = now()
    since, until = fmt(n - timedelta(days=days)), fmt(n)
    with conn() as c:
        by_status = {r["status"]: r["n"] for r in c.execute(
            "SELECT status, COUNT(*) AS n FROM bookings WHERE source!='block' "
            "AND start_at>=? AND start_at<=? GROUP BY status", (since, until))}
        busiest = c.execute(
            f"SELECT substr(start_at,12,2) AS hour, COUNT(*) AS n FROM bookings WHERE source!='block' "
            f"AND status IN {BLOCKING} AND start_at>=? AND start_at<=? GROUP BY hour "
            "ORDER BY n DESC, hour LIMIT 3", (since, until)).fetchall()
        top_services = c.execute(
            f"SELECT s.name_en AS name, COUNT(*) AS n FROM bookings b JOIN services s ON s.id=b.service_id "
            f"WHERE b.status IN {BLOCKING} AND b.start_at>=? AND b.start_at<=? "
            "GROUP BY s.id ORDER BY n DESC LIMIT 3", (since, until)).fetchall()
    done, no_show = by_status.get("done", 0), by_status.get("no_show", 0)
    return {
        "done": done, "no_show": no_show, "cancelled": by_status.get("cancelled", 0),
        "unmarked": by_status.get("confirmed", 0),
        "no_show_rate": round(100 * no_show / (done + no_show)) if done + no_show else None,
        "busiest": busiest, "top_services": top_services, "days": days,
    }
