#!/usr/bin/env python3
import re
import uuid
from datetime import datetime, date, timedelta
from dateutil import parser as dtparser

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "motorsport-calendar-bot/1.0"}

# ---------- ICS helpers ----------
def esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def vevent_all_day(summary: str, start_d: date, end_excl_d: date, location: str = "", description: str = "") -> str:
    uid = str(uuid.uuid4())
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{start_d.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end_excl_d.strftime('%Y%m%d')}",
        f"SUMMARY:{esc(summary)}",
    ]
    if location:
        lines.append(f"LOCATION:{esc(location)}")
    if description:
        lines.append(f"DESCRIPTION:{esc(description)}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)

def ics_calendar(events: list[str]) -> str:
    cal = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Motorsport Feed//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Motorsport (Low Noise)",
    ]
    cal.extend(events)
    cal.append("END:VCALENDAR")
    return "\r\n".join(cal) + "\r\n"

# ---------- Pullers ----------
def pull_imsa_weekends() -> list[tuple[str, date, date, str]]:
    """
    Scrape IMSA WeatherTech schedule (event name + date range).
    Produces all-day weekend blocks.
    """
    url = "https://www.imsa.com/weathertech/weathertech-2026-schedule/"
    html = requests.get(url, headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    out = []
    # The page includes repeated blocks with headings + a line like "Jul 30 - Aug 2"
    # We'll find patterns in the full text near each event heading.
    text = soup.get_text("\n", strip=True)

    # Example pattern: "Motul SportsCar Endurance Grand Prix\nJul 30 - Aug 2\nRoad America"
    pat = re.compile(r"\n([A-Za-z0-9’'().: \-]+)\n([A-Za-z]{3} \d{1,2})\s*-\s*([A-Za-z]{3} \d{1,2})\n([A-Za-z0-9’'().: \-]+)\n")
    for m in pat.finditer("\n" + text + "\n"):
        name = m.group(1).strip()
        start_md = m.group(2).strip()
        end_md = m.group(3).strip()
        venue = m.group(4).strip()

        # Infer year 2026
        start_dt = dtparser.parse(f"{start_md} 2026")
        end_dt = dtparser.parse(f"{end_md} 2026")
        # If end month/day appears earlier than start (year boundary), bump year (rare)
        if end_dt.date() < start_dt.date():
            end_dt = end_dt.replace(year=2027)

        title = f"IMSA — {name}"
        out.append((title, start_dt.date(), end_dt.date() + timedelta(days=1), venue))

    # Deduplicate (page text can contain repeated blocks)
    uniq = {}
    for title, s, e, loc in out:
        key = (title, s, e, loc)
        uniq[key] = (title, s, e, loc)
    return list(uniq.values())

def pull_wec_weekends() -> list[tuple[str, date, date, str]]:
    """
    Parse WEC 2026 dates from the WEC news post.
    """
    url = "https://www.fiawec.com/en/news/2026-fia-wec-calendar-builds-on-stability-of-recent-seasons/8356"
    html = requests.get(url, headers=UA, timeout=30).text
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    # Lines include: "Round 1 Qatar 1812 Km (QAT)26-28 March"
    # We'll pull (name) and date ranges.
    out = []
    month_map = {
        "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
        "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12
    }

    pat = re.compile(r"(Round\s+\d+)\s*([A-Za-z0-9’'(). \-]+?)\s*\([A-Z]{3}\)\s*(\d{1,2})-(\d{1,2})\s*(January|February|March|April|May|June|July|August|September|October|November|December)")
    for m in pat.finditer(text):
        name = m.group(2).strip()
        d1 = int(m.group(3))
        d2 = int(m.group(4))
        mon = month_map[m.group(5)]
        start = date(2026, mon, d1)
        end_excl = date(2026, mon, d2) + timedelta(days=1)
        out.append((f"WEC — {name}", start, end_excl, ""))

    # Also include Le Mans line if formatted differently (often "24 Hours of Le Mans" is still caught above).
    uniq = {}
    for item in out:
        uniq[item] = item
    return list(uniq.values())

def pull_road_america_race_weekends() -> list[tuple[str, date, date, str]]:
    """
    Scrape Road America calendar and keep only higher-signal race weekends.
    """
    url = "https://www.roadamerica.com/calendar"
    html = requests.get(url, headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    # Each event appears as link text like:
    # "2026-07-30T07:00 2026-08-02T17:00 Motul SportsCar Endurance Grand Prix Featuring IMSA ..."
    links = soup.find_all("a")
    keep_keywords = [
        "IndyCar", "IMSA", "MotoAmerica", "June Sprints", "Vintage Weekend",
        "Trans Am", "SpeedTour", "GT World Challenge", "Runoffs", "SVRA"
    ]

    out = []
    for a in links:
        t = a.get_text(" ", strip=True)
        if not t.startswith("2026-"):
            continue

        # quick keyword filter
        if not any(k.lower() in t.lower() for k in keep_keywords):
            continue

        # parse two ISO datetimes at the front
        m = re.match(r"^(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2})\s+(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2})\s+(.*)$", t)
        if not m:
            continue

        start_dt = dtparser.parse(m.group(1))
        end_dt = dtparser.parse(m.group(2))
        name = m.group(3).strip()

        # clean title a bit
        title = f"Road America — {name}"
        out.append((title, start_dt.date(), end_dt.date() + timedelta(days=1), "Road America, Elkhart Lake, WI"))

    # Dedup
    uniq = {}
    for item in out:
        uniq[item] = item
    return list(uniq.values())

def pull_f2_weekends() -> list[tuple[str, date, date, str]]:
    """
    Scrape FIA F2 calendar page for round date ranges (weekend blocks).
    """
    url = "https://www.fiaformula2.com/Calendar"
    html = requests.get(url, headers=UA, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    # Find patterns like: "Round 1 06 - 08 March Melbourne"
    # The page text can vary; we match "Round X" then "DD - DD Month" then location word(s).
    pat = re.compile(r"Round\s+\d+\s+(\d{1,2})\s*-\s*(\d{1,2})\s+([A-Za-z]+)\s+([A-Za-z][A-Za-z \-']+)")
    month_map = {
        "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
        "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
    }

    out = []
    for m in pat.finditer(text):
        d1 = int(m.group(1))
        d2 = int(m.group(2))
        mon_name = m.group(3)
        loc = m.group(4).strip()

        if mon_name not in month_map:
            continue

        start = date(2026, month_map[mon_name], d1)
        end_excl = date(2026, month_map[mon_name], d2) + timedelta(days=1)
        out.append((f"F2 — {loc} (Race Weekend)", start, end_excl, loc))

    uniq = {}
    for item in out:
        uniq[item] = item
    return list(uniq.values())

def pull_f1_race_days_if_available() -> list[tuple[str, date, date, str]]:
    """
    Try to fetch the official F1 calendar sync link and keep only Race events.
    If the endpoint doesn't return ICS directly, we just skip (no failure).
    """
    # Formula1.com points to calendar.formula1.com for syncing.  [oai_citation:5‡Formula 1® - The Official F1® Website](https://www.formula1.com/en/latest/article/download-or-sync-the-f1-race-calendar-to-your-device.7mpETY062kafAl55qVnemu)
    url = "https://calendar.formula1.com/"
    try:
        r = requests.get(url, headers=UA, timeout=30, allow_redirects=True)
        body = r.text
        if "BEGIN:VCALENDAR" not in body:
            return []
    except Exception:
        return []

    # crude ICS parsing: pull VEVENT blocks and keep SUMMARY containing "Race"
    out = []
    for block in body.split("BEGIN:VEVENT"):
        if "END:VEVENT" not in block:
            continue
        ve = "BEGIN:VEVENT" + block.split("END:VEVENT")[0] + "END:VEVENT"
        lines = ve.splitlines()
        summary = ""
        dtstart = ""
        location = ""
        for ln in lines:
            if ln.startswith("SUMMARY:"):
                summary = ln[len("SUMMARY:"):].strip()
            if ln.startswith("DTSTART"):
                dtstart = ln.split(":", 1)[-1].strip()
            if ln.startswith("LOCATION:"):
                location = ln[len("LOCATION:"):].strip()
        if "Race" not in summary:
            continue

        # DTSTART might be UTC or local; we just take the date portion
        # Examples: 20260308T040000Z or 20260308
        d = dtstart[:8]
        start = date(int(d[0:4]), int(d[4:6]), int(d[6:8]))
        out.append((f"F1 — {summary}", start, start + timedelta(days=1), location))
    return out

# ---------- main ----------
def main():
    pulled = []

    pulled += pull_f2_weekends()
    pulled += pull_imsa_weekends()
    pulled += pull_wec_weekends()
    pulled += pull_road_america_race_weekends()
    pulled += pull_f1_race_days_if_available()

    # Build ICS events
    events = []
    seen = set()
    for title, start, end_excl, loc in pulled:
        key = (title, start, end_excl, loc)
        if key in seen:
            continue
        seen.add(key)
        events.append(vevent_all_day(title, start, end_excl, location=loc))

    ics = ics_calendar(events)
    with open("motorsport_feed.ics", "w", encoding="utf-8") as f:
        f.write(ics)

    print(f"Wrote motorsport_feed.ics with {len(events)} events")

if __name__ == "__main__":
    main()