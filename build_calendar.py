#!/usr/bin/env python3
import re
import requests
from datetime import datetime

UA = {"User-Agent": "motorsport-calendar-bot/1.0"}

# These pages either:
#  - return an .ics directly, OR
#  - contain an .ics link we can follow.
SOURCES = {
    "F1": "https://calendar.formula1.com/",
    "F2": "https://calendar.fiaformula2.com/",
    # IMSA + WEC: see below (need a stable ICS feed link)
    # "IMSA": "https://<your-imsa-ics-feed>.ics",
    # "WEC":  "https://<your-wec-ics-feed>.ics",
}

def find_ics_urls(html: str) -> list[str]:
    urls = set()
    for m in re.finditer(r'https?://[^\s"<>]+\.ics(\?[^\s"<>]+)?', html, flags=re.IGNORECASE):
        urls.add(m.group(0))
    return sorted(urls)

def download_text(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
    r.raise_for_status()
    return r.text

def get_ics(name: str, url: str) -> str | None:
    text = download_text(url)

    # If the URL returns an ICS directly
    if "BEGIN:VCALENDAR" in text:
        return text

    # Otherwise, find .ics link(s) in the HTML and try them
    for ics_url in find_ics_urls(text):
        try:
            ics = download_text(ics_url)
            if "BEGIN:VCALENDAR" in ics:
                return ics
        except Exception:
            pass

    print(f"[WARN] No ICS found for {name} from {url}")
    return None

def extract_vevents(ics: str) -> list[str]:
    blocks = []
    parts = ics.split("BEGIN:VEVENT")
    for p in parts[1:]:
        if "END:VEVENT" not in p:
            continue
        blocks.append(("BEGIN:VEVENT" + p.split("END:VEVENT", 1)[0] + "END:VEVENT").strip())
    return blocks

def main():
    all_events = []
    seen = set()

    for name, url in SOURCES.items():
        ics = get_ics(name, url)
        if not ics:
            continue

        for ve in extract_vevents(ics):
            # de-dupe by UID when present
            m = re.search(r"\nUID:(.+)\n", "\n" + ve + "\n")
            key = (name, m.group(1).strip()) if m else (name, ve)
            if key in seen:
                continue
            seen.add(key)
            all_events.append(ve)

    out = []
    out.append("BEGIN:VCALENDAR")
    out.append("VERSION:2.0")
    out.append("PRODID:-//Motorsport Feed (Merged)//EN")
    out.append("CALSCALE:GREGORIAN")
    out.append("METHOD:PUBLISH")
    out.append("X-WR-CALNAME:Motorsport (All Sessions)")
    out.append(f"X-WR-CALDESC:Auto-generated {datetime.utcnow().strftime('%Y-%m-%d %H:%MZ')}")
    out.extend(all_events)
    out.append("END:VCALENDAR")

    with open("motorsport_feed.ics", "w", encoding="utf-8") as f:
        f.write("\r\n".join(out) + "\r\n")

    print(f"Wrote motorsport_feed.ics with {len(all_events)} events")

if __name__ == "__main__":
    main()