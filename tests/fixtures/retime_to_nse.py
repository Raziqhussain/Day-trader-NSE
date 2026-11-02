"""Re-time the recorded US Yahoo fixtures onto the NSE clock.

The fixtures are real Yahoo charts recorded on the US market (New York time, 9:30 to
16:00). The pack now runs on NSE hours (India time, UTC+5:30, 9:15 to 15:30), so every
timestamp is moved: the New York wall clock minus 15 minutes, read as India time on the
same date. The 9:30 New York bar becomes the 9:15 IST bar, 10:15 becomes 10:00, and the
last three bars of a US session (15:45 to 15:55 New York) would land after the 15:30
close, so they are removed, which leaves the 75 bars of an NSE session. A
regularMarketTime after the close becomes 15:30. Prices and volumes are untouched.

A file recorded on 2026-10-20 (an NSE holiday, Dussehra) also moves one day later,
to 2026-10-21; pass --days 1 for it.

Run once per original file (it rewrites the file in place):
    python3 retime_to_nse.py FILE [--days N]
"""
import argparse
import datetime
import gzip
import json

EPOCH = datetime.datetime(1970, 1, 1)
IST = datetime.timedelta(hours=5, minutes=30)
SHIFT = datetime.timedelta(minutes=15)   # 9:30 New York -> 9:15 India


def _nth_sunday(year, month, n):
    d = datetime.date(year, month, 1)
    d += datetime.timedelta(days=(6 - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def new_york_offset(utc):
    """-4 in US daylight time, -5 otherwise (second Sunday of March to first Sunday of November)."""
    y = utc.year
    start = datetime.datetime.combine(_nth_sunday(y, 3, 2), datetime.time(7, 0))
    end = datetime.datetime.combine(_nth_sunday(y, 11, 1), datetime.time(6, 0))
    return -4 if start <= utc < end else -5


def retime(ts, days=0):
    utc = EPOCH + datetime.timedelta(seconds=int(ts))
    wall = utc + datetime.timedelta(hours=new_york_offset(utc))
    ist = wall - SHIFT + datetime.timedelta(days=days)
    return int((ist - IST - EPOCH).total_seconds())


def after_close(ts):
    """A bar or stamp at or after 15:30 India time: no NSE bar starts there."""
    local = EPOCH + datetime.timedelta(seconds=ts) + IST
    return (local.hour, local.minute) >= (15, 30)


def retime_result(res, days):
    stamps = [retime(t, days) for t in res.get("timestamp") or []]
    keep = [i for i, t in enumerate(stamps) if not after_close(t)]
    res["timestamp"] = [stamps[i] for i in keep]
    for group in (res.get("indicators") or {}).values():
        for series in group:
            for k, col in series.items():
                if isinstance(col, list) and len(col) == len(stamps):
                    series[k] = [col[i] for i in keep]
    meta = res.get("meta") or {}
    if meta.get("regularMarketTime"):
        t = retime(meta["regularMarketTime"], days)
        if after_close(t):   # the 16:00 New York closing print becomes the 15:30 close
            local = EPOCH + datetime.timedelta(seconds=t) + IST
            t = int((local.replace(hour=15, minute=30, second=0) - IST - EPOCH).total_seconds())
        meta["regularMarketTime"] = t
    if "gmtoffset" in meta:
        meta.update(gmtoffset=19800, timezone="IST", exchangeTimezoneName="Asia/Kolkata")


def results(doc):
    """Every chart result in a v8 chart, a v7 spark or a {SYMBOL: v8 chart} wall."""
    if "chart" in doc:
        return list((doc["chart"] or {}).get("result") or [])
    if "spark" in doc:
        return [r for item in (doc["spark"].get("result") or []) for r in item.get("response") or []]
    return [r for v in doc.values() if isinstance(v, dict) for r in results(v)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file")
    ap.add_argument("--days", type=int, default=0)
    a = ap.parse_args()
    op = gzip.open if a.file.endswith(".gz") else open
    with op(a.file, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    found = results(doc)
    for res in found:
        retime_result(res, a.days)
    with op(a.file, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print("%s: %d chart(s) re-timed" % (a.file, len(found)))


if __name__ == "__main__":
    main()
