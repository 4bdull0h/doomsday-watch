#!/usr/bin/env python3
"""Watch Cinematica (Tashkent City) and notify in Russian when Avengers: Doomsday tickets go on sale."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://cinematica.uz/api/v1"
SITE = "https://cinematica.uz"
CINEMA_ID = 1  # Tashkent City
TITLE_RE = re.compile(r"doomsday|судн\w*\s+д[еэ]н|qiyomat", re.IGNORECASE)
INTERVAL = int(os.environ.get("CHECK_INTERVAL", "120"))
STATE = Path(__file__).with_name("state.json")

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TG_CHAT_ID", "")


def get(path, attempts=3):
    req = urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(5)


def notify(text):
    print(text, flush=True)
    if BOT_TOKEN and CHAT_ID:
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": "false"}).encode()
        try:
            urllib.request.urlopen(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data, timeout=20)
        except Exception as e:
            print(f"telegram error: {e}", file=sys.stderr)
    try:
        subprocess.run(["notify-send", "-u", "critical", "Cinematica", text], check=False)
    except FileNotFoundError:
        pass


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {"announced": [], "on_sale": []}


def find_movies():
    found = {}
    for path in ("/movies", "/movies/today", "/movies/soon"):
        for m in get(path).get("list", []):
            if TITLE_RE.search(m.get("name") or ""):
                found[m["id"]] = m
    return found


def open_sessions(movie_id):
    sessions = get(f"/repertory/movie/{movie_id}/grouped").get("list", [])
    return [
        s for s in sessions
        if s.get("cinema_id") == CINEMA_ID and not s.get("disable_sales") and not s.get("is_disabled")
    ]


def check():
    state = load_state()
    for mid, m in find_movies().items():
        name = m["name"].strip()
        url = f"{SITE}/movies/{mid}"
        if mid not in state["announced"]:
            state["announced"].append(mid)
            notify(f"🎬 На сайте Синематики появился фильм «{name}»!\n"
                   f"Премьера: {(m.get('date_start') or '')[:10]}\n"
                   f"Билетов пока нет — сообщу, как только откроется продажа.\n{url}")
        if mid in state["on_sale"]:
            continue
        sessions = open_sessions(mid)
        if sessions:
            state["on_sale"].append(mid)
            first = sorted(sessions, key=lambda s: (s["date"][6:], s["date"][3:5], s["date"][:2], s["time"]))[:5]
            lines = "\n".join(f"• {s['date']} {s['time']} — {s['hall']}, {int(float(s['price'])):_} сум".replace("_", " ")
                              for s in first)
            notify(f"🚨 БИЛЕТЫ В ПРОДАЖЕ! «{name}»\n"
                   f"Синематика, Tashkent City — сеансов: {len(sessions)}\n{lines}\n\nПокупай скорее: {url}")
    STATE.write_text(json.dumps(state))


def main():
    if "--test" in sys.argv:
        notify("✅ Тест: уведомления о «Мстители: Судный день» работают.")
        return
    once = "--once" in sys.argv
    # --duration N: keep checking for N seconds, then exit (used by GitHub Actions)
    deadline = time.time() + int(sys.argv[sys.argv.index("--duration") + 1]) if "--duration" in sys.argv else None
    while True:
        try:
            check()
        except Exception as e:
            print(f"check failed: {e}", file=sys.stderr, flush=True)
        if once or (deadline and time.time() + INTERVAL > deadline):
            return
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
