"""All customer-facing text in English and Amharic.

Have a native Amharic speaker read through the "am" block before you launch.
"""

T = {
    "en": {
        "choose_lang": "Please choose your language / እባክዎ ቋንቋ ይምረጡ",
        "lang_set": "Language saved.",
        "ask_phone": "Share your phone number so the salon can reach you if needed.",
        "share_phone": "Share phone number",
        "skip": "Skip",
        "thanks": "Thank you!",
        "menu": "Welcome to {salon}! What would you like to do?",
        "b_book": "Book an appointment",
        "b_my": "My bookings",
        "b_info": "About the salon",
        "b_help": "Help",
        "b_lang": "Language",
        "back": "Back",
        "pick_service": "Choose a service:",
        "pick_staff": "Choose a stylist:",
        "any_staff": "Any available",
        "pick_day": "Choose a day:",
        "no_days": "No free times in the coming days. Please call the salon: {phone}",
        "pick_time": "Free times on {day}:",
        "no_slots": "No free times on this day.",
        "summary": ("Please confirm your appointment:\n\nService: {service}\nStylist: {staff}\n"
                    "Date: {day}\nTime: {time}\nPrice: {price} ETB"),
        "confirm": "Confirm",
        "booked": "Your appointment is booked ✅\n\n{service}\n{day} at {time}\n\n{address}",
        "slot_taken": "Sorry, that time was just taken. Please choose another time.",
        "my_none": "You have no upcoming bookings.",
        "my_title": "Your upcoming bookings:",
        "resched": "Reschedule",
        "cancel": "Cancel",
        "cancel_ask": "Cancel your appointment on {day} at {time}?",
        "yes_cancel": "Yes, cancel",
        "keep": "Keep it",
        "cancelled": "Your appointment has been cancelled.",
        "too_late": ("This appointment starts in less than {hours} hours, so it can't be changed here. "
                     "Please call the salon: {phone}"),
        "info": "{salon}\n{address}\nPhone: {phone}\nOpen {open} to {close}",
        "help": ("Use the menu to book, view or cancel appointments. "
                 "You will get a reminder the day before and 2 hours before."),
        "reminder_day": "Reminder: you have an appointment tomorrow at {time} ({service}).",
        "reminder_soon": "Reminder: your appointment is today at {time} ({service}).",
        "still_coming": "I'm coming",
        "thanks_see": "See you soon!",
        "salon_cancelled": ("Sorry, the salon had to cancel your appointment on {day} at {time}. "
                            "Please book another time or call {phone}."),
        "expired": "This session expired. Let's start again.",
    },
    "am": {
        "choose_lang": "Please choose your language / እባክዎ ቋንቋ ይምረጡ",
        "lang_set": "ቋንቋ ተቀምጧል።",
        "ask_phone": "ሳሎኑ እንዲያገኝዎ ስልክ ቁጥርዎን ያጋሩ።",
        "share_phone": "ስልክ ቁጥር አጋራ",
        "skip": "ዝለል",
        "thanks": "አመሰግናለሁ!",
        "menu": "እንኳን ወደ {salon} በደህና መጡ! ምን ማድረግ ይፈልጋሉ?",
        "b_book": "ቀጠሮ ያዝ",
        "b_my": "ቀጠሮዎቼ",
        "b_info": "ስለ ሳሎኑ",
        "b_help": "እርዳታ",
        "b_lang": "ቋንቋ",
        "back": "ተመለስ",
        "pick_service": "አገልግሎት ይምረጡ፦",
        "pick_staff": "ባለሙያ ይምረጡ፦",
        "any_staff": "ማንኛውም ነፃ ባለሙያ",
        "pick_day": "ቀን ይምረጡ፦",
        "no_days": "በቀጣዮቹ ቀናት ነፃ ሰዓት የለም። እባክዎ ሳሎኑን ይደውሉ፦ {phone}",
        "pick_time": "{day} ያሉ ነፃ ሰዓቶች፦",
        "no_slots": "በዚህ ቀን ነፃ ሰዓት የለም።",
        "summary": ("እባክዎ ቀጠሮዎን ያረጋግጡ፦\n\nአገልግሎት፦ {service}\nባለሙያ፦ {staff}\n"
                    "ቀን፦ {day}\nሰዓት፦ {time}\nዋጋ፦ {price} ብር"),
        "confirm": "አረጋግጥ",
        "booked": "ቀጠሮዎ ተይዟል ✅\n\n{service}\n{day} ሰዓት {time}\n\n{address}",
        "slot_taken": "ይቅርታ፣ ይህ ሰዓት ተይዟል። እባክዎ ሌላ ሰዓት ይምረጡ።",
        "my_none": "ምንም የሚመጣ ቀጠሮ የለዎትም።",
        "my_title": "የሚመጡ ቀጠሮዎችዎ፦",
        "resched": "ቀይር",
        "cancel": "ሰርዝ",
        "cancel_ask": "በ{day} ሰዓት {time} ያለዎትን ቀጠሮ ይሰርዙ?",
        "yes_cancel": "አዎ፣ ሰርዝ",
        "keep": "አቆየው",
        "cancelled": "ቀጠሮዎ ተሰርዟል።",
        "too_late": ("ቀጠሮው ከ{hours} ሰዓት ባነሰ ጊዜ ውስጥ ስለሚጀምር እዚህ መቀየር አይቻልም። "
                     "እባክዎ ሳሎኑን ይደውሉ፦ {phone}"),
        "info": "{salon}\n{address}\nስልክ፦ {phone}\nየስራ ሰዓት፦ {open} እስከ {close}",
        "help": ("ቀጠሮ ለመያዝ፣ ለማየት ወይም ለመሰረዝ ምናሌውን ይጠቀሙ። "
                 "ከቀጠሮው አንድ ቀን በፊትና 2 ሰዓት በፊት ማስታወሻ ይላክልዎታል።"),
        "reminder_day": "ማስታወሻ፦ ነገ ሰዓት {time} ቀጠሮ አለዎት ({service})።",
        "reminder_soon": "ማስታወሻ፦ ዛሬ ሰዓት {time} ቀጠሮ አለዎት ({service})።",
        "still_coming": "እመጣለሁ",
        "thanks_see": "በቅርቡ እንገናኛለን!",
        "salon_cancelled": ("ይቅርታ፣ ሳሎኑ በ{day} ሰዓት {time} የነበረዎትን ቀጠሮ መሰረዝ ነበረበት። "
                            "እባክዎ ሌላ ሰዓት ይያዙ ወይም ይደውሉ፦ {phone}"),
        "expired": "ክፍለ ጊዜው አብቅቷል። እንደገና እንጀምር።",
    },
}

WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "am": ["ሰኞ", "ማክሰኞ", "ረቡዕ", "ሐሙስ", "አርብ", "ቅዳሜ", "እሑድ"],
}


def t(lang, key, **kw):
    text = T.get(lang, T["en"]).get(key) or T["en"][key]
    return text.format(**kw) if kw else text


def day_label(lang, d):
    """Short label such as 'Wed 8/10' (day/month, Gregorian calendar)."""
    return f"{WEEKDAYS.get(lang, WEEKDAYS['en'])[d.weekday()]} {d.day}/{d.month}"
