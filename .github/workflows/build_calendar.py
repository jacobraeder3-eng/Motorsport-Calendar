#!/usr/bin/env python3
import json
import uuid
from datetime import datetime, date

def esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

def vevent_all_day(summary: str, start_d: date, end_excl: date, location="", description="") -> str:
    uid = str(uuid.uuid4())
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;VALUE=DATE:{start_d.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end_excl.strftime('%Y%m%d')}",
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
        "X-WR-CALNAME:Motorsport 2026 (Low Noise)",
    ]
    cal.append("\r\n".join(events))
    cal.append("END:VCALENDAR")
    return "\r\n".join(cal) + "\r\n"

def parse_date(d: str) -> date:
    y, m, day = d.split("-")
    return date(int(y), int(m), int(day))

def main():
    with open("events_2026.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    events_out = []
    for e in data["events"]:
        start = parse_date(e["start"])
        end_excl = parse_date(e["end_exclusive"])
        events_out.append(
            vevent_all_day(
                summary=e["title"],
                start_d=start,
                end_excl=end_excl,
                location=e.get("location", ""),
                description=e.get("description", "")
            )
        )

    ics = ics_calendar(events_out)
    with open("motorsport_feed.ics", "w", encoding="utf-8") as f:
        f.write(ics)

    print(f"Wrote motorsport_feed.ics with {len(events_out)} events")

if __name__ == "__main__":
    main()
