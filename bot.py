"""Salon booking bot (python-telegram-bot v21+).

Run:  python bot.py
"""
import html
import logging
import os
import re
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from telegram import InlineKeyboardButton as Btn  # noqa: E402
from telegram import InlineKeyboardMarkup as Markup  # noqa: E402
from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update  # noqa: E402
from telegram.constants import ParseMode  # noqa: E402
from telegram.error import BadRequest, Forbidden  # noqa: E402
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,  # noqa: E402
                          ContextTypes, MessageHandler, filters)

import db  # noqa: E402
from texts import day_label, t  # noqa: E402

log = logging.getLogger("salon-bot")
esc = html.escape


# ---------------------------------------------------------------- helpers
def get_lang(context, user_id):
    lang = context.user_data.get("lang")
    if not lang:
        c = db.get_customer(user_id)
        lang = c["lang"] if c and c["lang"] else "en"
        context.user_data["lang"] = lang
    return lang


def svc_name(s, lang):
    return s["name_am"] if lang == "am" and s["name_am"] else s["name_en"]


def rows_of(buttons, per_row):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


async def send(update, text, markup=None):
    """Edit the message a button was pressed on, or send a new message."""
    q = update.callback_query
    if q:
        try:
            await q.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            return
        except BadRequest:
            pass  # message unchanged or too old: send a fresh one instead
        await q.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def notify_owner(context, text):
    owner = os.environ.get("OWNER_CHAT_ID", "").strip()
    if not owner:
        return
    try:
        await context.bot.send_message(int(owner), text, parse_mode=ParseMode.HTML)
    except Exception as exc:  # never let an alert break a customer's booking
        log.warning("Could not notify owner: %s", exc)


def menu_kb(lang):
    return Markup([
        [Btn(t(lang, "b_book"), callback_data="m:book")],
        [Btn(t(lang, "b_my"), callback_data="m:my"), Btn(t(lang, "b_info"), callback_data="m:info")],
        [Btn(t(lang, "b_help"), callback_data="m:help"), Btn(t(lang, "b_lang"), callback_data="m:lang")],
    ])


def lang_kb():
    return Markup([[Btn("English", callback_data="lang:en"), Btn("አማርኛ", callback_data="lang:am")]])


def back_kb(lang, target="m:menu"):
    return Markup([[Btn(t(lang, "back"), callback_data=target)]])


async def show_menu(update, context, lang):
    salon = esc(db.get_settings()["salon_name"])
    await send(update, t(lang, "menu", salon=salon), menu_kb(lang))


async def ask_phone(update, context, lang):
    context.user_data["awaiting"] = "phone"
    context.user_data["phone_asked"] = True
    kb = ReplyKeyboardMarkup([[KeyboardButton(t(lang, "share_phone"), request_contact=True)],
                              [KeyboardButton(t(lang, "skip"))]],
                             resize_keyboard=True, one_time_keyboard=True)
    await update.effective_chat.send_message(t(lang, "ask_phone"), reply_markup=kb)


# ---------------------------------------------------------------- commands
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_customer(user.id, name=user.full_name)
    c = db.get_customer(user.id)
    if not c["lang"]:
        await update.message.reply_text(t("en", "choose_lang"), reply_markup=lang_kb())
        return
    context.user_data["lang"] = c["lang"]
    await show_menu(update, context, c["lang"])


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your chat ID: {update.effective_chat.id}")


# ---------------------------------------------------------------- phone / text
async def on_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, contact = update.effective_user, update.message.contact
    lang = get_lang(context, user.id)
    if contact.user_id == user.id:  # only accept the sender's own number
        db.upsert_customer(user.id, phone=contact.phone_number)
    context.user_data.pop("awaiting", None)
    await update.message.reply_text(t(lang, "thanks"), reply_markup=ReplyKeyboardRemove())
    await show_menu(update, context, lang)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang = get_lang(context, user.id)
    if context.user_data.get("awaiting") == "phone":
        text = update.message.text.strip()
        digits = re.sub(r"\D", "", text)
        if len(digits) >= 9:
            db.upsert_customer(user.id, phone=text[:20])
        elif text not in (t("en", "skip"), t("am", "skip")):
            await update.message.reply_text(t(lang, "ask_phone"))
            return
        context.user_data.pop("awaiting", None)
        await update.message.reply_text(t(lang, "thanks"), reply_markup=ReplyKeyboardRemove())
    await show_menu(update, context, lang)


# ---------------------------------------------------------------- button router
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = update.effective_user
    lang = get_lang(context, user.id)
    action, _, arg = q.data.partition(":")
    routes = {"lang": h_lang, "m": h_menu, "s": h_service, "f": h_staff, "d": h_day, "t": h_time,
              "ok": h_confirm, "back": h_back, "c": h_cancel_ask, "cy": h_cancel_do,
              "rs": h_resched, "keep": h_keep}
    handler = routes.get(action)
    if handler:
        await handler(update, context, lang, arg)


async def h_lang(update, context, lang, arg):
    if arg not in ("en", "am"):
        return
    user = update.effective_user
    db.upsert_customer(user.id, lang=arg)
    context.user_data["lang"] = arg
    c = db.get_customer(user.id)
    if not c["phone"] and not context.user_data.get("phone_asked"):
        await send(update, t(arg, "lang_set"))
        await ask_phone(update, context, arg)
    else:
        await show_menu(update, context, arg)


async def h_menu(update, context, lang, arg):
    if arg == "menu":
        await show_menu(update, context, lang)
    elif arg == "book":
        context.user_data["draft"] = {}
        await show_services(update, context, lang)
    elif arg == "my":
        await show_my(update, context, lang)
    elif arg == "info":
        s = db.get_settings()
        text = t(lang, "info", salon=esc(s["salon_name"]), address=esc(s["address"]),
                 phone=esc(s["phone"]), open=s["open_time"], close=s["close_time"])
        await send(update, text, back_kb(lang))
    elif arg == "help":
        await send(update, t(lang, "help"), back_kb(lang))
    elif arg == "lang":
        await send(update, t("en", "choose_lang"), lang_kb())


# ---------------------------------------------------------------- booking flow
async def show_services(update, context, lang):
    services = db.list_services()
    unit = "ብር" if lang == "am" else "ETB"
    buttons = [Btn(f"{svc_name(s, lang)} - {s['price']:g} {unit}", callback_data=f"s:{s['id']}")
               for s in services]
    kb = Markup(rows_of(buttons, 1) + [[Btn(t(lang, "back"), callback_data="m:menu")]])
    await send(update, t(lang, "pick_service"), kb)


async def h_service(update, context, lang, arg):
    draft = context.user_data.setdefault("draft", {})
    draft.update(service=int(arg), staff=0, day=None, time=None, assigned=None)
    staff = db.list_staff()
    if len(staff) > 1:
        buttons = [Btn(t(lang, "any_staff"), callback_data="f:0")]
        buttons += [Btn(s["name"], callback_data=f"f:{s['id']}") for s in staff]
        kb = Markup(rows_of(buttons, 1) + [[Btn(t(lang, "back"), callback_data="m:book")]])
        await send(update, t(lang, "pick_staff"), kb)
    else:
        await show_days(update, context, lang)


async def h_staff(update, context, lang, arg):
    draft = context.user_data.get("draft")
    if not draft or not draft.get("service"):
        await send(update, t(lang, "expired"), menu_kb(lang))
        return
    draft["staff"] = int(arg)
    await show_days(update, context, lang)


async def show_days(update, context, lang):
    d = context.user_data["draft"]
    settings = db.get_settings()
    today = db.now().date()
    buttons = []
    for i in range(int(settings["booking_days"])):
        day = today + timedelta(days=i)
        if db.free_slots(day, d["service"], d["staff"] or None):
            buttons.append(Btn(day_label(lang, day), callback_data=f"d:{day.isoformat()}"))
    if not buttons:
        await send(update, t(lang, "no_days", phone=esc(settings["phone"])), back_kb(lang))
        return
    kb = Markup(rows_of(buttons, 3) + [[Btn(t(lang, "back"), callback_data="m:book")]])
    await send(update, t(lang, "pick_day"), kb)


async def h_day(update, context, lang, arg):
    d = context.user_data.get("draft")
    if not d or not d.get("service"):
        await send(update, t(lang, "expired"), menu_kb(lang))
        return
    d["day"] = arg
    day = datetime.strptime(arg, "%Y-%m-%d").date()
    slots = db.free_slots(day, d["service"], d["staff"] or None)
    if not slots:
        await send(update, t(lang, "no_slots"), back_kb(lang, "back:days"))
        return
    buttons = [Btn(hhmm, callback_data=f"t:{hhmm.replace(':', '')}:{sid}") for hhmm, sid in slots]
    kb = Markup(rows_of(buttons, 4) + [[Btn(t(lang, "back"), callback_data="back:days")]])
    await send(update, t(lang, "pick_time", day=day_label(lang, day)), kb)


async def h_back(update, context, lang, arg):
    if arg == "days" and context.user_data.get("draft", {}).get("service"):
        await show_days(update, context, lang)
    else:
        await show_menu(update, context, lang)


async def h_time(update, context, lang, arg):
    d = context.user_data.get("draft")
    if not d or not d.get("day"):
        await send(update, t(lang, "expired"), menu_kb(lang))
        return
    hhmm, _, staff_id = arg.partition(":")
    d["time"] = f"{hhmm[:2]}:{hhmm[2:]}"
    d["assigned"] = int(staff_id)
    svc, staff = db.get_service(d["service"]), db.get_staff(d["assigned"])
    day = datetime.strptime(d["day"], "%Y-%m-%d").date()
    text = t(lang, "summary", service=esc(svc_name(svc, lang)), staff=esc(staff["name"]),
             day=day_label(lang, day), time=d["time"], price=f"{svc['price']:g}")
    kb = Markup([[Btn(t(lang, "confirm"), callback_data="ok")],
                 [Btn(t(lang, "back"), callback_data=f"d:{d['day']}")]])
    await send(update, text, kb)


async def h_confirm(update, context, lang, arg):
    d = context.user_data.get("draft")
    if not d or not d.get("time"):
        await send(update, t(lang, "expired"), menu_kb(lang))
        return
    user = update.effective_user
    cust = db.get_customer(user.id)
    svc = db.get_service(d["service"])
    start = datetime.strptime(f"{d['day']} {d['time']}", db.FMT)
    bid = db.create_booking(staff_id=d["assigned"], start=start, minutes=svc["duration_min"],
                            service_id=svc["id"], chat_id=user.id,
                            name=(cust["name"] if cust else "") or user.full_name,
                            phone=cust["phone"] if cust else "")
    if bid is None:
        d["time"] = None
        await send(update, t(lang, "slot_taken"))
        await h_day(update, context, lang, d["day"])
        return
    old = d.get("replace")
    if old:
        prev = db.get_booking(old)
        if prev and prev["chat_id"] == user.id and prev["status"] == "confirmed":
            db.set_status(old, "cancelled")
    context.user_data.pop("draft", None)
    s = db.get_settings()
    day = start.date()
    await send(update, t(lang, "booked", service=esc(svc_name(svc, lang)), day=day_label(lang, day),
                         time=d["time"], address=esc(s["address"])),
               back_kb(lang))
    staff = db.get_staff(d["assigned"])
    label = "Rescheduled" if old else "New booking"
    await notify_owner(context, f"<b>{label}</b>: {esc(user.full_name)} {esc(cust['phone'] if cust else '')}\n"
                                f"{esc(svc['name_en'])} with {esc(staff['name'])}, "
                                f"{day_label('en', day)} at {d['time']}")


# ---------------------------------------------------------------- my bookings
async def show_my(update, context, lang):
    rows = db.upcoming_for_customer(update.effective_user.id)
    if not rows:
        await send(update, t(lang, "my_none"), back_kb(lang))
        return
    lines, kb_rows = [t(lang, "my_title")], []
    for b in rows:
        start = db.parse(b["start_at"])
        label = f"{day_label(lang, start.date())} {start:%H:%M}"
        lines.append(f"• {label}  {esc(svc_name({'name_en': b['service_en'], 'name_am': b['service_am']}, lang))}")
        kb_rows.append([Btn(f"{t(lang, 'resched')} {label}", callback_data=f"rs:{b['id']}"),
                        Btn(f"{t(lang, 'cancel')} {label}", callback_data=f"c:{b['id']}")])
    kb_rows.append([Btn(t(lang, "back"), callback_data="m:menu")])
    await send(update, "\n".join(lines), Markup(kb_rows))


def own_booking(update, bid):
    b = db.get_booking(int(bid)) if str(bid).isdigit() else None
    if b and b["chat_id"] == update.effective_user.id and b["status"] == "confirmed":
        return b
    return None


async def too_late(update, lang, b):
    s = db.get_settings()
    if db.parse(b["start_at"]) - db.now() < timedelta(hours=int(s["cancel_hours"])):
        await send(update, t(lang, "too_late", hours=s["cancel_hours"], phone=esc(s["phone"])),
                   back_kb(lang))
        return True
    return False


async def h_cancel_ask(update, context, lang, arg):
    b = own_booking(update, arg)
    if not b:
        await show_my(update, context, lang)
        return
    if await too_late(update, lang, b):
        return
    start = db.parse(b["start_at"])
    kb = Markup([[Btn(t(lang, "yes_cancel"), callback_data=f"cy:{b['id']}")],
                 [Btn(t(lang, "keep"), callback_data="m:my")]])
    await send(update, t(lang, "cancel_ask", day=day_label(lang, start.date()), time=f"{start:%H:%M}"), kb)


async def h_cancel_do(update, context, lang, arg):
    b = own_booking(update, arg)
    if not b:
        await show_my(update, context, lang)
        return
    if await too_late(update, lang, b):
        return
    db.set_status(b["id"], "cancelled")
    start = db.parse(b["start_at"])
    await send(update, t(lang, "cancelled"), menu_kb(lang))
    await notify_owner(context, f"<b>Cancelled</b>: {esc(b['customer_name'])} {esc(b['phone'])}\n"
                                f"{esc(b['service_en'] or '')} with {esc(b['staff_name'])}, "
                                f"{day_label('en', start.date())} at {start:%H:%M}")


async def h_resched(update, context, lang, arg):
    b = own_booking(update, arg)
    if not b:
        await show_my(update, context, lang)
        return
    if await too_late(update, lang, b):
        return
    context.user_data["draft"] = {"service": b["service_id"], "staff": b["staff_id"],
                                  "replace": b["id"], "day": None, "time": None, "assigned": None}
    await show_days(update, context, lang)


async def h_keep(update, context, lang, arg):
    await send(update, t(lang, "thanks_see"), menu_kb(lang))


# ---------------------------------------------------------------- reminders
async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    for b, kind in db.due_reminders():
        c = db.get_customer(b["chat_id"])
        lang = c["lang"] if c and c["lang"] else "en"
        start = db.parse(b["start_at"])
        name = svc_name({"name_en": b["service_en"] or "", "name_am": b["service_am"] or ""}, lang)
        # "tomorrow" is only right if the appointment really is on another calendar day
        same_day = kind == "soon" or start.date() == db.now().date()
        text = t(lang, "reminder_soon" if same_day else "reminder_day",
                 time=f"{start:%H:%M}", service=esc(name))
        kb = Markup([[Btn(t(lang, "still_coming"), callback_data=f"keep:{b['id']}")],
                     [Btn(t(lang, "resched"), callback_data=f"rs:{b['id']}"),
                      Btn(t(lang, "cancel"), callback_data=f"c:{b['id']}")]])
        try:
            await context.bot.send_message(b["chat_id"], text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Forbidden:
            pass  # the customer blocked the bot
        except Exception as exc:
            log.warning("Reminder for booking %s failed: %s", b["id"], exc)
        db.mark_reminded(b["id"], kind)  # mark even on failure so we never spam retries


# ---------------------------------------------------------------- app
def build_app(token):
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_start))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.CONTACT, on_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    if app.job_queue is None:
        raise RuntimeError('Reminders need the job-queue extra: pip install "python-telegram-bot[job-queue]"')
    app.job_queue.run_repeating(reminder_job, interval=60, first=15)
    return app


def main():
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN is missing. Copy .env.example to .env and fill it in.")
    db.init_db()
    log.info("Bot started. Press Ctrl+C to stop.")
    build_app(token).run_polling()


if __name__ == "__main__":
    main()
