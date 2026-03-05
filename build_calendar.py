#!/usr/bin/env python3
import re
import requests
from datetime import datetime

UA = {"User-Agent": "motorsport-calendar-bot/1.0"}

# Add sources that return an ICS or contain an ICS link in the HTML.
# iOS will display times in America/Chicago automatically.
SOURCES = {
    "F1": "https://calendar.formula1.com/",
    "F2": "https://calendar.fiaformula2.com/",
    # IMSA: you will add your IMSA eCal iCal feed URL here (one-time setup).
    # "IMSA": "https://...your-imsa-ecal-feed...ics",
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

def download_ics_from_source(name: str, url: str) -> str | None:
    text = download_text(url)

    # Direct ICS
    if "BEGIN:VCALENDAR" in text:
        return text

    # HTML containing ICS link(s)
    for ics_url in find_ics_urls(text):
        try:
            ics = download_text(ics_url)
            if "BEGIN:VCALENDAR" in ics:
                return ics
        except Exception:
            pass

    print(f"[WARN] Could not find ICS for {name} from {url}")
    return None

def extract_vevents(ics: str) -> list[str]:
    blocks = []
    parts = ics.split("BEGIN:VEVENT")
    for p in parts[1:]:
        if "END:VEVENT" not in p:
            continue
        ve = "BEGIN:VEVENT" + p.split("END:VEVENT", 1)[0] + "END:VEVENT"
        blocks.append(ve.strip())
    return blocks

def main():
    all_events = []
    seen_uids = set()

    for name, url in SOURCES.items():
        ics = download_ics_from_source(name, url)
        if not ics:
            continue

        for ve in extract_vevents(ics):
            m = re.search(r"\nUID:(.+)\n", "\n" + ve + "\n")
            uid = (name + ":" + m.group(1).strip()) if m else None

            if uid and uid in seen_uids:
                continue
            if uid:
                seen_uids.add(uid)

            all_events.append(ve)

    out = []
    out.append("BEGIN:VCALENDAR")
    out.append("VERSION:2.0")
    out.append("PRODID:-//Motorsport Feed (Merged)//EN")
    out.append("CALSCALE:GREGORIAN")
    out.append("METHOD:PUBLISH")
    out.append("X-WR-CALNAME:Motorsport (All Sessions, Chicago)")
    out.append(f"X-WR-CALDESC:Auto-generated {datetime.utcnow().strftime('%Y-%m-%d %H:%MZ')}")
    out.extend(all_events)
    out.append("END:VCALENDAR")

    with open("motorsport_feed.ics", "w", encoding="utf-8") as f:
        f.write("\r\n".join(out) + "\r\n")

    print(f"Wrote motorsport_feed.ics with {len(all_events)} events")

if __name__ == "__main__":
    main()