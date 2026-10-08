"""Salon dashboard (Flask).

Run:  python dashboard.py     then open http://127.0.0.1:8000
"""
import os
import secrets
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for  # noqa: E402

import db  # noqa: E402
import tg  # noqa: E402
from texts import day_label, t  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True,
                  PERMANENT_SESSION_LIFETIME=timedelta(days=14))

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def password():
    return os.environ.get("DASHBOARD_PASSWORD", "")


# ---------------------------------------------------------------- auth + CSRF
@app.before_request
def guard():
    db.init_db()
    if request.endpoint in (None, "static", "login"):
        return
    if not session.get("ok"):
        return redirect(url_for("login"))
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf", ""), session.get("csrf", "x")):
            abort(400)


@app.context_processor
def inject():
    return {"csrf": session.get("csrf", ""), "salon": db.get_settings()["salon_name"],
            "weekdays": WEEKDAYS}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if password() and secrets.compare_digest(request.form.get("password", ""), password()):
            session.clear()
            session.permanent = True
            session["ok"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("today"))
        time.sleep(1)  # slows down password guessing
        flash("That password is not correct.", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------- today
def parse_day(text):
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return db.now().date()


@app.route("/")
def today():
    day = parse_day(request.args.get("d"))
    rows = db.bookings_for_day(day)
    n = db.now()
    is_today = day == n.date()
    marker = None
    if is_today:
        marker = next((i for i, r in enumerate(rows) if r["start_at"] >= db.fmt(n)), len(rows))
    return render_template(
        "today.html", day=day, rows=rows, is_today=is_today, marker=marker, now_hm=n.strftime("%H:%M"),
        prev_day=day - timedelta(days=1), next_day=day + timedelta(days=1),
        services=db.list_services(), staff=db.list_staff(),
        open_count=sum(1 for r in rows if r["status"] == "confirmed" and r["source"] != "block"))


@app.post("/booking/<int:bid>/<action>")
def booking_action(bid, action):
    b = db.get_booking(bid)
    statuses = {"done": "done", "no_show": "no_show", "cancel": "cancelled"}
    if not b or action not in statuses:
        abort(404)
    db.set_status(bid, statuses[action])
    if action == "cancel" and b["chat_id"] and b["status"] == "confirmed":
        cust = db.get_customer(b["chat_id"])
        lang = cust["lang"] if cust and cust["lang"] else "en"
        start = db.parse(b["start_at"])
        sent = tg.send_message(b["chat_id"], t(lang, "salon_cancelled", day=day_label(lang, start.date()),
                                               time=f"{start:%H:%M}", phone=db.get_settings()["phone"]))
        flash("Booking cancelled" + (" and the customer was told." if sent else
                                     ". Could not message the customer, so please call them."), "ok")
    nxt = request.form.get("next", "")
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = url_for("today")
    return redirect(nxt)


@app.post("/walkin")
def walkin():
    day = request.form.get("day", "")
    try:
        svc = db.get_service(int(request.form["service"]))
        staff_id = int(request.form["staff"])
        start = datetime.strptime(f"{day} {request.form['time']}", db.FMT)
    except (KeyError, ValueError):
        flash("Please fill in the service, stylist and time.", "error")
        return redirect(url_for("today", d=day))
    bid = db.create_booking(staff_id=staff_id, start=start, minutes=svc["duration_min"],
                            service_id=svc["id"], source="walkin", phone=request.form.get("phone", "")[:20],
                            name=request.form.get("name", "").strip()[:60] or "Walk-in")
    flash("Walk-in added." if bid else "That time overlaps another booking for this stylist.",
          "ok" if bid else "error")
    return redirect(url_for("today", d=day))


@app.post("/block")
def block():
    day = request.form.get("day", "")
    try:
        start = datetime.strptime(f"{day} {request.form['time']}", db.FMT)
        minutes = max(5, min(600, int(request.form["minutes"])))
        who = request.form["staff"]
        ids = [s["id"] for s in db.list_staff()] if who == "all" else [int(who)]
    except (KeyError, ValueError):
        flash("Please fill in the time and length.", "error")
        return redirect(url_for("today", d=day))
    note = request.form.get("note", "").strip()[:80] or "Blocked"
    failed = [i for i in ids if db.create_booking(staff_id=i, start=start, minutes=minutes,
                                                  source="block", name="", note=note) is None]
    if failed:
        flash("Some times overlap existing bookings, so they were not blocked.", "error")
    else:
        flash("Time blocked.", "ok")
    return redirect(url_for("today", d=day))


# ---------------------------------------------------------------- services
def num(name, default=0.0):
    try:
        return float(request.form.get(name, default))
    except ValueError:
        return default


@app.get("/services")
def services():
    return render_template("services.html", services=db.list_services(active_only=False))


@app.post("/services/add")
def services_add():
    name = request.form.get("name_en", "").strip()
    if not name:
        flash("Give the service a name.", "error")
    else:
        db.add_service(name[:60], request.form.get("name_am", "").strip()[:60],
                       max(5, int(num("minutes", 30))), max(0, num("price")))
        flash("Service added.", "ok")
    return redirect(url_for("services"))


@app.post("/services/<int:sid>/save")
def services_save(sid):
    db.update_service(sid, request.form.get("name_en", "").strip()[:60] or "Service",
                      request.form.get("name_am", "").strip()[:60],
                      max(5, int(num("minutes", 30))), max(0, num("price")))
    flash("Service saved.", "ok")
    return redirect(url_for("services"))


@app.post("/services/<int:sid>/toggle")
def services_toggle(sid):
    db.toggle_service(sid)
    return redirect(url_for("services"))


# ---------------------------------------------------------------- stylists
def days_from_form():
    picked = sorted({d for d in request.form.getlist("days") if d in "0123456" and d})
    return ",".join(picked)


@app.get("/staff")
def staff():
    return render_template("staff.html", staff=db.list_staff(active_only=False))


@app.post("/staff/add")
def staff_add():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Give the stylist a name.", "error")
    else:
        db.add_staff(name[:60], days_from_form() or "0,1,2,3,4,5")
        flash("Stylist added.", "ok")
    return redirect(url_for("staff"))


@app.post("/staff/<int:stid>/save")
def staff_save(stid):
    db.update_staff(stid, request.form.get("name", "").strip()[:60] or "Stylist", days_from_form())
    flash("Stylist saved.", "ok")
    return redirect(url_for("staff"))


@app.post("/staff/<int:stid>/toggle")
def staff_toggle(stid):
    db.toggle_staff(stid)
    return redirect(url_for("staff"))


# ---------------------------------------------------------------- settings + stats
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        f = request.form
        values = {k: f.get(k, "").strip() for k in
                  ("salon_name", "address", "phone", "open_time", "close_time")}
        values["closed_days"] = ",".join(sorted(d for d in f.getlist("closed") if d in list("0123456")))
        for k, lo, hi in (("slot_step", 5, 120), ("cancel_hours", 0, 72),
                          ("min_lead_min", 0, 600), ("booking_days", 1, 60)):
            try:
                values[k] = max(lo, min(hi, int(f.get(k, ""))))
            except ValueError:
                pass
        db.set_settings({k: v for k, v in values.items() if v != ""})
        flash("Settings saved.", "ok")
        return redirect(url_for("settings"))
    s = db.get_settings()
    return render_template("settings.html", s=s, closed=s["closed_days"].split(","))


@app.get("/numbers")
def numbers():
    return render_template("stats.html", st=db.stats(7))


if __name__ == "__main__":
    if not password():
        raise SystemExit("DASHBOARD_PASSWORD is missing. Copy .env.example to .env and fill it in.")
    db.init_db()
    from waitress import serve
    host = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("DASHBOARD_PORT", "8000")))
    print(f"Dashboard running on http://{host}:{port}")
    serve(app, host=host, port=port)
