"""Tiny helper so the dashboard can message a customer (uses only the standard library)."""
import os
import urllib.parse
import urllib.request


def send_message(chat_id, text):
    token = os.environ.get("BOT_TOKEN")
    if not token or not chat_id:
        return False
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=10)
        return True
    except Exception:
        return False
