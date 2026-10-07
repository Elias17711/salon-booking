"""Run with:  python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TMP = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(TMP, "test.db")
os.environ["DASHBOARD_PASSWORD"] = "pw"
os.environ["SECRET_KEY"] = "test"

import db  # noqa: E402


def next_open_day():
    d = db.now().date() + timedelta(days=1)
    while str(d.weekday()) in db.get_settings()["closed_days"].split(","):
        d += timedelta(days=1)
    return d


class DataLayer(unittest.TestCase):
    def setUp(self):
        if os.path.exists(os.environ["DB_PATH"]):
            os.remove(os.environ["DB_PATH"])
        db.init_db()

    def test_slots_respect_hours_and_duration(self):
        day = next_open_day()
        svc = db.list_services()[1]  # Braids, 120 min
        slots = [s for s, _ in db.free_slots(day, svc["id"])]
        self.assertEqual(slots[0], "09:00")
        self.assertEqual(slots[-1], "17:00")  # 17:00 + 2h = closing time

    def test_closed_day_has_no_slots(self):
        d = db.now().date() + timedelta(days=1)
        while d.weekday() != 6:  # Sunday is closed by default
            d += timedelta(days=1)
        self.assertEqual(db.free_slots(d, db.list_services()[0]["id"]), [])

    def test_booking_blocks_overlap_and_prevents_double_booking(self):
        day = next_open_day()
        svc, staff = db.list_services()[0], db.list_staff()[0]  # Haircut, 30 min
        start = datetime.combine(day, datetime.strptime("10:00", "%H:%M").time())
        first = db.create_booking(staff_id=staff["id"], start=start, minutes=30, service_id=svc["id"], chat_id=1)
        self.assertIsNotNone(first)
        self.assertIsNone(db.create_booking(staff_id=staff["id"], start=start, minutes=30, chat_id=2))
        self.assertIsNone(db.create_booking(staff_id=staff["id"], start=start + timedelta(minutes=15), minutes=30))
        self.assertIsNotNone(db.create_booking(staff_id=staff["id"], start=start + timedelta(minutes=30), minutes=30))
        self.assertNotIn("10:00", [s for s, _ in db.free_slots(day, svc["id"])])

    def test_cancel_frees_the_slot(self):
        day = next_open_day()
        svc, staff = db.list_services()[0], db.list_staff()[0]
        start = datetime.combine(day, datetime.strptime("11:00", "%H:%M").time())
        bid = db.create_booking(staff_id=staff["id"], start=start, minutes=30, service_id=svc["id"], chat_id=1)
        db.set_status(bid, "cancelled")
        self.assertIn("11:00", [s for s, _ in db.free_slots(day, svc["id"])])

    def test_any_stylist_uses_second_stylist_when_first_is_busy(self):
        db.add_staff("Stylist 2", "0,1,2,3,4,5")
        day = next_open_day()
        svc, s1, s2 = db.list_services()[0], *db.list_staff()
        start = datetime.combine(day, datetime.strptime("10:00", "%H:%M").time())
        db.create_booking(staff_id=s1["id"], start=start, minutes=30)
        slots = dict(db.free_slots(day, svc["id"]))
        self.assertEqual(slots["10:00"], s2["id"])

    def test_stylist_day_off(self):
        db.update_staff(db.list_staff()[0]["id"], "Stylist 1", "")  # works no days
        self.assertEqual(db.free_slots(next_open_day(), db.list_services()[0]["id"]), [])

    def test_reminders_fire_once(self):
        svc, staff = db.list_services()[0], db.list_staff()[0]
        soon = db.now() + timedelta(hours=26)
        bid = db.create_booking(staff_id=staff["id"], start=soon, minutes=30, service_id=svc["id"], chat_id=5)
        self.assertEqual(db.due_reminders(), [])  # more than 24h away
        with db.conn() as c:  # pretend time moved on: booking is now 23h away
            c.execute("UPDATE bookings SET start_at=?, end_at=? WHERE id=?",
                      (db.fmt(db.now() + timedelta(hours=23)), db.fmt(db.now() + timedelta(hours=23, minutes=30)), bid))
        due = db.due_reminders()
        self.assertEqual([(b["id"], k) for b, k in due], [(bid, "day")])
        db.mark_reminded(bid, "day")
        self.assertEqual(db.due_reminders(), [])

    def test_booking_made_inside_reminder_window_sends_no_stale_reminder(self):
        svc, staff = db.list_services()[0], db.list_staff()[0]
        db.create_booking(staff_id=staff["id"], start=db.now() + timedelta(hours=5), minutes=30,
                          service_id=svc["id"], chat_id=5)
        self.assertEqual(db.due_reminders(), [])

    def test_stats(self):
        svc, staff = db.list_services()[0], db.list_staff()[0]
        past = db.now() - timedelta(hours=3)
        a = db.create_booking(staff_id=staff["id"], start=past, minutes=30, service_id=svc["id"], chat_id=1)
        b = db.create_booking(staff_id=staff["id"], start=past - timedelta(hours=1), minutes=30,
                              service_id=svc["id"], chat_id=2)
        db.set_status(a, "done")
        db.set_status(b, "no_show")
        st = db.stats()
        self.assertEqual((st["done"], st["no_show"], st["no_show_rate"]), (1, 1, 50))


class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dashboard
        cls.app = dashboard.app
        cls.app.config["TESTING"] = True

    def setUp(self):
        if os.path.exists(os.environ["DB_PATH"]):
            os.remove(os.environ["DB_PATH"])
        db.init_db()
        self.c = self.app.test_client()

    def login(self):
        r = self.c.post("/login", data={"password": "pw"})
        self.assertEqual(r.status_code, 302)
        with self.c.session_transaction() as s:
            return s["csrf"]

    def test_requires_login(self):
        self.assertEqual(self.c.get("/").status_code, 302)
        self.assertEqual(self.c.get("/services").status_code, 302)

    def test_wrong_password(self):
        self.assertIn(b"not correct", self.c.post("/login", data={"password": "nope"}).data)

    def test_pages_render(self):
        self.login()
        for path in ("/", "/services", "/staff", "/settings", "/numbers"):
            self.assertEqual(self.c.get(path).status_code, 200, path)

    def test_post_without_csrf_is_rejected(self):
        self.login()
        self.assertEqual(self.c.post("/services/add", data={"name_en": "X"}).status_code, 400)

    def test_walkin_block_and_actions(self):
        csrf = self.login()
        day = db.now().date().isoformat()
        svc, staff = db.list_services()[0], db.list_staff()[0]
        r = self.c.post("/walkin", data={"csrf": csrf, "day": day, "time": "23:00", "service": svc["id"],
                                         "staff": staff["id"], "name": "Sara"}, follow_redirects=True)
        self.assertIn(b"Sara", r.data)
        r = self.c.post("/walkin", data={"csrf": csrf, "day": day, "time": "23:15", "service": svc["id"],
                                         "staff": staff["id"], "name": "Overlap"}, follow_redirects=True)
        self.assertIn(b"overlaps", r.data)
        r = self.c.post("/block", data={"csrf": csrf, "day": day, "time": "20:00", "minutes": "60",
                                        "staff": "all", "note": "Lunch"}, follow_redirects=True)
        self.assertIn(b"Lunch", r.data)
        bid = db.bookings_for_day(db.now().date())[-1]["id"]
        self.c.post(f"/booking/{bid}/done", data={"csrf": csrf})
        self.assertEqual(db.get_booking(bid)["status"], "done")

    def test_edit_services_and_settings(self):
        csrf = self.login()
        self.c.post("/services/add", data={"csrf": csrf, "name_en": "Facial", "name_am": "", "minutes": "60", "price": "500"})
        self.assertIn("Facial", [s["name_en"] for s in db.list_services()])
        self.c.post("/settings", data={"csrf": csrf, "salon_name": "Lily Salon", "address": "Bole", "phone": "0911",
                                       "open_time": "08:00", "close_time": "18:00", "closed": ["6"],
                                       "slot_step": "15", "cancel_hours": "3", "min_lead_min": "20", "booking_days": "10"})
        s = db.get_settings()
        self.assertEqual((s["salon_name"], s["open_time"], s["slot_step"]), ("Lily Salon", "08:00", "15"))

    def test_open_redirect_is_blocked(self):
        csrf = self.login()
        db.create_booking(staff_id=1, start=db.now() + timedelta(days=2), minutes=30, service_id=1, chat_id=None)
        bid = db.bookings_for_day((db.now() + timedelta(days=2)).date())[0]["id"]
        r = self.c.post(f"/booking/{bid}/done", data={"csrf": csrf, "next": "//evil.example"})
        self.assertNotIn("evil", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
