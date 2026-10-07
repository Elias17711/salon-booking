"""Drive the real bot handlers with fake Telegram updates (no internet or token needed).

Run:  python tests/simulate_bot.py
It prints what a customer would see at each step.
"""
import asyncio
import os
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "sim.db")
os.environ["OWNER_CHAT_ID"] = "999"

import bot  # noqa: E402
import db  # noqa: E402
from telegram import Bot, Update  # noqa: E402

SENT = []  # everything the bot "sent" to Telegram
_counter = {"n": 100}
USER = {"id": 42, "is_bot": False, "first_name": "Sara", "last_name": "T"}
BOT_USER = {"id": 1, "is_bot": True, "first_name": "SalonBot", "username": "salon_bot"}


async def fake_post(self, endpoint, data=None, **kw):
    data = data or {}
    if endpoint == "getMe":
        return BOT_USER
    if endpoint == "answerCallbackQuery":
        return True
    if endpoint in ("sendMessage", "editMessageText"):
        _counter["n"] += 1
        markup = data.get("reply_markup")
        SENT.append({"to": data.get("chat_id"), "text": data.get("text"), "markup": markup, "kind": endpoint})
        return {"message_id": _counter["n"], "date": 0, "chat": {"id": data.get("chat_id", 42), "type": "private"},
                "text": data.get("text", ""), "from": BOT_USER}
    raise RuntimeError(f"Unexpected Telegram call: {endpoint}")


Bot._post = fake_post
_uid = {"n": 0}


def message_update(text=None, contact=None):
    _uid["n"] += 1
    msg = {"message_id": _uid["n"], "date": 0, "chat": {"id": 42, "type": "private"}, "from": USER}
    if text is not None:
        msg["text"] = text
        if text.startswith("/"):
            msg["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    if contact:
        msg["contact"] = contact
    return {"update_id": _uid["n"], "message": msg}


def press_update(data):
    _uid["n"] += 1
    return {"update_id": _uid["n"], "callback_query": {
        "id": str(_uid["n"]), "from": USER, "chat_instance": "ci", "data": data,
        "message": {"message_id": 7, "date": 0, "chat": {"id": 42, "type": "private"}, "from": BOT_USER, "text": "x"}}}


def buttons(entry):
    kb = entry["markup"]
    if not kb:
        return []
    kb = kb if isinstance(kb, dict) else kb.to_dict()
    return [(b["text"], b.get("callback_data")) for row in kb.get("inline_keyboard", []) for b in row]


async def main():
    db.init_db()
    app = bot.build_app("123456:TEST")
    await app.initialize()

    async def feed(raw, label):
        before = len(SENT)
        await app.process_update(Update.de_json(raw, app.bot))
        new = SENT[before:]
        print(f"\n--- {label}")
        for e in new:
            to = "OWNER" if e["to"] == 999 else "customer"
            print(f"[{to}] {e['text']!r}")
            if buttons(e):
                print("      buttons:", [b[0] for b in buttons(e)])
        return new

    def last_customer(new):
        return [e for e in new if e["to"] != 999][-1]

    await feed(message_update("/start"), "/start (new customer)")
    await feed(press_update("lang:en"), "chooses English")
    await feed(message_update(contact={"phone_number": "+251911000000", "first_name": "Sara", "user_id": 42}),
               "shares phone number")
    new = await feed(press_update("m:book"), "Book an appointment")
    new = await feed(press_update("s:1"), "picks Haircut")
    days = [b for b in buttons(last_customer(new)) if b[1].startswith("d:")]
    assert days, "no days offered"
    new = await feed(press_update(days[0][1]), f"picks day {days[0][0]}")
    slots = [b for b in buttons(last_customer(new)) if b[1].startswith("t:")]
    assert slots, "no slots offered"
    new = await feed(press_update(slots[2][1]), f"picks time {slots[2][0]}")
    new = await feed(press_update("ok"), "confirms")
    assert any(e["to"] == 999 for e in new), "owner was not notified"
    booking = db.upcoming_for_customer(42)[0]
    print("\nDB row:", booking["start_at"], booking["status"], booking["customer_name"], booking["phone"])

    # same slot again from a second customer must fail cleanly
    start = db.parse(booking["start_at"])
    again = db.create_booking(staff_id=booking["staff_id"], start=start, minutes=30, chat_id=77)
    assert again is None

    new = await feed(press_update("m:my"), "My bookings")
    await feed(press_update(f"rs:{booking['id']}"), "Reschedule (should be allowed if > cancel window)")

    # "too late" path: move booking to 1h from now
    with db.conn() as c:
        c.execute("UPDATE bookings SET start_at=?, end_at=? WHERE id=?",
                  (db.fmt(db.now() + timedelta(hours=1)), db.fmt(db.now() + timedelta(hours=1, minutes=30)), booking["id"]))
    await feed(press_update(f"c:{booking['id']}"), "Cancel inside the 2-hour window (should be refused)")

    # cancel properly
    with db.conn() as c:
        c.execute("UPDATE bookings SET start_at=?, end_at=? WHERE id=?",
                  (db.fmt(db.now() + timedelta(days=2)), db.fmt(db.now() + timedelta(days=2, minutes=30)), booking["id"]))
    await feed(press_update(f"c:{booking['id']}"), "Cancel (asks to confirm)")
    # (reschedule is tested below, so keep this booking for now)
    await feed(press_update(f"c:{booking['id']}"), "Cancel (asks to confirm, not confirmed yet)")

    # reschedule success path: booking 2 days away, move it to another time
    new = await feed(press_update(f"rs:{booking['id']}"), "Reschedule (booking is 2 days away)")
    days = [b for b in buttons(last_customer(new)) if b[1].startswith("d:")]
    new = await feed(press_update(days[-1][1]), f"picks day {days[-1][0]}")
    slots = [b for b in buttons(last_customer(new)) if b[1].startswith("t:")]
    new = await feed(press_update(slots[0][1]), f"picks time {slots[0][0]}")
    await feed(press_update("ok"), "confirms new time")
    assert db.get_booking(booking["id"])["status"] == "cancelled", "old booking should be cancelled"
    moved = db.upcoming_for_customer(42)
    assert len(moved) == 1 and moved[0]["id"] != booking["id"], "exactly one new booking expected"
    booking = moved[0]

    # reminders
    with db.conn() as c:
        c.execute("UPDATE bookings SET status='confirmed', start_at=?, end_at=?, reminded_day=0, reminded_soon=0 WHERE id=?",
                  (db.fmt(db.now() + timedelta(hours=20)), db.fmt(db.now() + timedelta(hours=20, minutes=30)), booking["id"]))
    before = len(SENT)

    class Ctx:  # minimal stand-in for the job context
        bot = app.bot

    await bot.reminder_job(Ctx())
    print("\n--- reminder job")
    for e in SENT[before:]:
        print(f"[customer] {e['text']!r}", [b[0] for b in buttons(e)])
    assert len(SENT) == before + 1
    await bot.reminder_job(Ctx())
    assert len(SENT) == before + 1, "reminder was sent twice"

    # Amharic path
    await feed(press_update("lang:am"), "switches to Amharic")
    await feed(press_update("m:info"), "About the salon (Amharic)")
    await feed(press_update("m:book"), "Book (Amharic)")
    await app.shutdown()
    print("\nSimulation finished without errors.")


asyncio.run(main())
