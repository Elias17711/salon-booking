"""Data layer shared by the Telegram bot and the web dashboard.

Two storage back-ends, one set of functions:
  * a SQLite file (default; simplest on your own PC), or
  * PostgreSQL, used automatically when the DATABASE_URL environment variable is
    set. A hosted Postgres keeps your data when a host such as Render restarts.

All times are stored as local Addis Ababa time in the text format
"YYYY-MM-DD HH:MM", which sorts correctly as plain text.
"""
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

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


def database_url():
    return os.environ.get("DATABASE_URL", "").strip()


def using_postgres():
    return bool(database_url())


def now():
    """Current local time in Addis Ababa as a naive datetime."""
    return datetime.now(TZ).replace(tzinfo=None)


# ---------- PostgreSQL support ----------
_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            _pool = ConnectionPool(
                database_url(), min_size=1, max_size=5, timeout=30, open=True,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": None},
                check=ConnectionPool.check_connection,  # replaces connections the host closed while idle
            )
        return _pool


def close_pool():
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


def _pg_sql(sql):
    """Turn the SQLite-style statements used in this file into PostgreSQL."""
    s = sql.strip()
    ignore = bool(re.match(r"INSERT OR IGNORE INTO", s, re.I))
    if ignore:
        s = re.sub(r"INSERT OR IGNORE INTO", "INSERT INTO", s, count=1, flags=re.I)
    s = s.replace("?", "%s")
    return s + " ON CONFLICT DO NOTHING" if ignore else s


def _pg_schema(schema):
    s = schema.replace("chat_id INTEGER PRIMARY KEY", "chat_id BIGINT PRIMARY KEY")
    s = s.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
    s = s.replace("chat_id INTEGER,", "chat_id BIGINT,")  # Telegram ids can exceed 32 bits
    return s.replace("price REAL", "price DOUBLE PRECISION")


class PgConn:
    """Gives a psycopg connection the small sqlite3-style surface this app uses."""

    def __init__(self, raw):
        self.raw = raw

    def execute(self, sql, params=()):
        return self.raw.execute(_pg_sql(sql), params)

    def executescript(self, script):
        for stmt in script.split(";"):
            if stmt.strip():
                self.raw.execute(stmt)


@contextmanager
def conn():
    if using_postgres():
        with _get_pool().connection() as raw:
            yield PgConn(raw)
        return
    c = sqlite3.connect(db_path(), timeout=10, isolation_level=None)  # autocommit
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
    finally:
        c.close()


def _begin_write(c):
    """Start a transaction that only one writer at a time can hold."""
    if isinstance(c, PgConn):
        c.execute("BEGIN")
        c.execute("LOCK TABLE bookings IN SHARE ROW EXCLUSIVE MODE")
    else:
        c.execute("BEGIN IMMEDIATE")


def fmt(dt):
    return dt.strftime(FMT)


def parse(text):
    return datetime.strptime(text, FMT)


_ready = set()
_init_lock = threading.Lock()


def init_db():
    """Create tables and sample data once per process (cheap to call repeatedly)."""
    key = database_url() or db_path()
    with _init_lock:
        if key in _ready and (using_postgres() or os.path.exists(db_path())):
            return
        with conn() as c:
            c.executescript(_pg_schema(SCHEMA) if using_postgres() else SCHEMA)
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
        _ready.add(key)


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


def _load_context(service_id, staff_id):
    settings = get_settings()
    svc = get_service(service_id)
    candidates = [get_staff(staff_id)] if staff_id else list_staff()
    return settings, svc, [x for x in candidates if x and x["active"]]


def _busy_map(staff_ids, first_day, last_day):
    """{staff_id: [(start, end), ...]} of occupied time between two days (inclusive)."""
    busy = {i: [] for i in staff_ids}
    if not staff_ids:
        return busy
    marks = ",".join("?" * len(staff_ids))
    with conn() as c:
        rows = c.execute(
            f"SELECT staff_id, start_at, end_at FROM bookings WHERE staff_id IN ({marks}) "
            f"AND status IN {BLOCKING} AND start_at >= ? AND start_at < ?",
            (*staff_ids, first_day.isoformat(), (last_day + timedelta(days=1)).isoformat())).fetchall()
    for r in rows:
        busy[r["staff_id"]].append((parse(r["start_at"]), parse(r["end_at"])))
    return busy


def _compute_slots(day, s, svc, staff, busy):
    wd = str(day.weekday())
    if wd in s["closed_days"].split(","):
        return []
    working = [x for x in staff if wd in x["work_days"].split(",")]
    dur = timedelta(minutes=svc["duration_min"])
    step = timedelta(minutes=max(5, int(s["slot_step"])))
    midnight = datetime.combine(day, datetime.min.time())
    opens, closes = midnight + _hhmm(s["open_time"]), midnight + _hhmm(s["close_time"])
    earliest = now() + timedelta(minutes=int(s["min_lead_min"]))
    slots = {}
    t = opens
    while t + dur <= closes:
        if t >= earliest:
            for x in working:
                if all(t + dur <= b0 or t >= b1 for b0, b1 in busy.get(x["id"], [])):
                    slots.setdefault(t.strftime("%H:%M"), x["id"])
                    break
        t += step
    return sorted(slots.items())


def free_slots(day, service_id, staff_id=None):
    """Return [("HH:MM", staff_id), ...] of bookable start times on `day`.

    With staff_id=None, each time is offered if ANY working stylist is free and
    the first free stylist is assigned.
    """
    s, svc, staff = _load_context(service_id, staff_id)
    if not svc:
        return []
    busy = _busy_map([x["id"] for x in staff], day, day)
    return _compute_slots(day, s, svc, staff, busy)


def available_days(service_id, staff_id=None):
    """Days (from today) that still have at least one free time. Uses few queries."""
    s, svc, staff = _load_context(service_id, staff_id)
    if not svc:
        return []
    today, n = now().date(), int(s["booking_days"])
    busy = _busy_map([x["id"] for x in staff], today, today + timedelta(days=n - 1))
    days = (today + timedelta(days=i) for i in range(n))
    return [d for d in days if _compute_slots(d, s, svc, staff, busy)]


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
        _begin_write(c)
        try:
            clash = c.execute(
                f"SELECT 1 FROM bookings WHERE staff_id=? AND status IN {BLOCKING} "
                "AND start_at < ? AND end_at > ?", (staff_id, fmt(end), fmt(start))).fetchone()
            if clash:
                c.execute("ROLLBACK")
                return None
            rows = c.execute(
                "INSERT INTO bookings(chat_id, customer_name, phone, service_id, staff_id, start_at, end_at,"
                " source, note, reminded_day, reminded_soon, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
                "RETURNING id",
                (chat_id, name, phone, service_id, staff_id, fmt(start), fmt(end), source, note,
                 1 if start - n <= timedelta(hours=24) else 0,
                 1 if start - n <= timedelta(hours=2) else 0, fmt(n))).fetchall()
            c.execute("COMMIT")
            return rows[0]["id"]
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
