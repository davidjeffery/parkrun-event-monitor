#!/usr/bin/env python3
"""Track new parkrun IDs, alert by email, and save a successful snapshot."""
import json
import argparse
import os
import smtplib
import sys
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

URL = "https://images.parkrun.com/events.json"
STATE = Path("data/events_snapshot.json")
ZONE = ZoneInfo("Europe/London")


def due(now):
    """8am daily and Friday 18:00 to Saturday 08:00, hourly UK time."""
    if now.hour == 8:
        return True
    return (now.weekday() == 4 and now.hour >= 18) or (now.weekday() == 5 and now.hour <= 7)


def fetch():
    request = urllib.request.Request(URL, headers={"User-Agent": "parkrun-event-monitor/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.load(response)


def extract(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), dict):
        raise ValueError("Unrecognised parkrun JSON: no events object")
    features = payload["events"].get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Unrecognised/empty parkrun events.features")
    countries = payload.get("countries", {})
    out = {}
    for f in features:
        if not isinstance(f, dict):
            continue
        p = f.get("properties") or {}
        ident = f.get("id", p.get("eventid", p.get("EventId")))
        if ident is None:
            continue
        ident = str(ident)
        coord = (f.get("geometry") or {}).get("coordinates")
        lon, lat = (coord[:2] if isinstance(coord, list) and len(coord) >= 2 else (None, None))
        cc = str(p.get("countrycode", ""))
        c = countries.get(cc, {}) if isinstance(countries, dict) else {}
        if not isinstance(c, dict):
            c = {}
        name = p.get("EventLongName") or p.get("LocalisedEventLongName") or p.get("EventShortName") or p.get("eventname") or f"Event {ident}"
        area = p.get("EventLocation") or p.get("eventlocation") or "Location not supplied"
        site = c.get("url") or "www.parkrun.com"
        domain = str(site).strip().replace("https://", "").replace("http://", "").strip("/")
        slug = str(p.get("eventname") or "").strip("/")
        link = f"https://{domain}/{slug}/" if slug else "Not supplied"
        out[ident] = {"name":str(name),"area":str(area),"country":str(c.get("name") or cc or "Unknown"),"lat":lat,"lon":lon,"url":link}
    if len(out) < 100:  # guard against partial/truncated responses wiping history
        raise ValueError(f"Only {len(out)} unique events: refusing to save incomplete feed")
    return out


def email_alert(new):
    sender = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL", "djeffery92@gmail.com")
    if not sender or not password:
        raise RuntimeError("Email not configured: set SMTP_USER and SMTP_APP_PASSWORD secrets. Snapshot not advanced.")
    lines = [f"{len(new)} new parkrun event(s) listed in events.json:", ""]
    for ident, p in sorted(new.items(), key=lambda x: x[1]["name"]):
        loc = f'{p["area"]}, {p["country"]}'
        coords = f'{p["lat"]}, {p["lon"]}' if p["lat"] is not None and p["lon"] is not None else "Not supplied"
        lines.extend([p["name"], f"Location: {loc}", f"Coordinates (lat, lon): {coords}", f"Event ID: {ident}", f'Link: {p["url"]}', ""])
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"New parkrun events: {len(new)} added"
    msg.set_content("\n".join(lines))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=35) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)


def verify_smtp():
    """Check credentials without sending a test/historical-event email."""
    sender = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_APP_PASSWORD")
    if not sender or not password:
        raise RuntimeError("Set SMTP_USER and SMTP_APP_PASSWORD repository secrets")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=35) as smtp:
        smtp.login(sender, password)
    print("SMTP authentication succeeded (no test email sent)")


def check(now, initialize=False):
    """Keep an all-time ID history; never silently reset a missing baseline."""
    old = None
    if STATE.exists():
        old = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(old, dict) or not isinstance(old.get("events"), dict) or not old["events"]:
            raise ValueError("Old snapshot invalid; refusing to replace")
        if not all(isinstance(k, str) and isinstance(v, dict) for k, v in old["events"].items()):
            raise ValueError("Old snapshot has invalid event entries")
    elif not initialize:
        raise RuntimeError("Snapshot missing: explicitly initialize once using Run workflow")
    current = extract(fetch())
    if old is None:
        print(f"First successful check: saving {len(current)} events without sending an alert")
        history = current
    else:
        new_ids = set(current) - set(old["events"])
        if new_ids:
            added = {i: current[i] for i in new_ids}
            email_alert(added)
            print(f"Sent alert for {len(added)} events")
        else:
            print("No new IDs")
        history = {**old["events"], **current}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"checked_at":now.isoformat(), "current_event_count":len(current), "events":history}, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    temporary.replace(STATE)
    print(f"Snapshot ready: {len(current)} current, {len(history)} all-time event IDs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true", help="Allow the first baseline only; never resets existing history")
    parser.add_argument("--verify-smtp", action="store_true", help="Authenticate to Gmail without sending mail")
    args = parser.parse_args()
    now = datetime.now(ZONE)
    if os.environ.get("FORCE_CHECK") != "1" and not due(now):
        print("Not a UK monitoring hour:", now.isoformat())
        return
    if args.verify_smtp:
        verify_smtp()
    check(now, initialize=args.initialize)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Monitor failed: {exc}", file=sys.stderr)
        sys.exit(1)
