"""Shared helpers for the Streamlit pages: paths, running the skill tools, the sidebar, charts.

The pages never re-implement a trading rule. Each one runs the skill's own tool with --json
(the same command you would type in a terminal) and draws what comes back, so the UI and the
skills always agree. The tools read and write trader/*.json under the workspace folder.
"""
import datetime
import importlib.util
import json
import os
import subprocess
import sys

import altair as alt
import pandas as pd
import streamlit as st

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the folder whose trader/ subfolder holds watchlist.json, entry.json, plan.json and config.json
WORKSPACE = os.path.abspath(os.environ.get("TRADER_HOME") or os.getcwd())
TRADER = os.path.join(WORKSPACE, "trader")
TOOLS = {
    "scanner": ("trader-scanner", "scan.py"),
    "entry": ("trader-entry", "entry.py"),
    "exit": ("trader-exit", "exit.py"),
    "timemachine": ("trader-timemachine", "timemachine.py"),
    "alerts": ("trader-alerts", "alerts.py"),
}
NOTE = "Education and tooling, not financial advice. Nothing here places an order."

# a starter list of large, liquid NSE stocks; edit it on the scanner page (it is saved to trader/nse_symbols.txt)
STARTER_SYMBOLS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS",
    "LT.NS", "HINDUNILVR.NS", "KOTAKBANK.NS", "AXISBANK.NS", "BAJFINANCE.NS", "MARUTI.NS", "M&M.NS",
    "SUNPHARMA.NS", "TATASTEEL.NS", "NTPC.NS", "POWERGRID.NS", "ONGC.NS", "COALINDIA.NS",
    "ULTRACEMCO.NS", "ASIANPAINT.NS", "TITAN.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "ADANIENT.NS",
    "ADANIPORTS.NS", "JSWSTEEL.NS", "HINDALCO.NS", "NESTLEIND.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS",
    "HEROMOTOCO.NS", "DRREDDY.NS", "CIPLA.NS", "GRASIM.NS", "INDUSINDBK.NS",
]
SYMBOLS_FILE = os.path.join(TRADER, "nse_symbols.txt")


# ---------------------------------------------------------------- the tools

def tool_path(name):
    folder, script = TOOLS[name]
    return os.path.join(REPO, folder, script)


def run_tool(name, args, timeout=900):
    """Run one skill tool in the workspace. -> (doc or None, error line or "", exit code).
    With --json a tool prints one JSON document, even when its exit code is 1 (no hits, waiting);
    a real error is one plain line on stderr and no JSON."""
    os.makedirs(TRADER, exist_ok=True)
    try:
        p = subprocess.run([sys.executable, tool_path(name)] + [str(a) for a in args], cwd=WORKSPACE,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "%s took longer than %d seconds" % (TOOLS[name][1], timeout), 1
    doc = None
    out = p.stdout.strip()
    if out[:1] in ("{", "["):
        try:
            doc = json.loads(out)
        except ValueError:
            doc = None
    err = ""
    if doc is None:
        lines = [ln for ln in (p.stderr or p.stdout).strip().splitlines() if ln.strip()]
        err = lines[-1] if lines else "%s exited with code %d" % (TOOLS[name][1], p.returncode)
        prefix = TOOLS[name][1] + ": "
        if err.startswith(prefix):
            err = err[len(prefix):]
    return doc, err, p.returncode


@st.cache_resource
def module(name):
    """Import a tool as a module, for its clock and chart parsing only (never to place anything)."""
    spec = importlib.util.spec_from_file_location("ui_" + name, tool_path(name))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_json(name):
    path = os.path.join(TRADER, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def rel(path):
    return os.path.relpath(path, WORKSPACE)


# ---------------------------------------------------------------- the clock

def now_args():
    """--now for the tools when the sidebar pins a replay time, else nothing (the live clock)."""
    text = (st.session_state.get("replay") or "").strip()
    return ["--now", text] if text else []


def now_utc():
    alerts = module("alerts")
    text = (st.session_state.get("replay") or "").strip()
    try:
        return alerts.parse_now(text or None)
    except Exception:
        return alerts.parse_now(None)


def ist_now():
    return module("alerts").to_eastern(now_utc())


def sidebar():
    """The market clock and the replay time, on every page."""
    alerts = module("alerts")
    with st.sidebar:
        st.text_input("Replay time (IST)", key="replay", placeholder="blank = live, or 2026-10-19 10:00",
                      help="Pin the clock for every tool, to replay a past session. Leave blank for live data.")
        text = (st.session_state.get("replay") or "").strip()
        if text:
            try:
                alerts.parse_now(text)
            except Exception:
                st.error("Use a time like 2026-10-19 10:00")
        stt = alerts.market_status(now_utc())
        badge = ":green[OPEN]" if stt["open"] else ":red[CLOSED]"
        st.markdown("**NSE %s**  \n%s %s IST  \n%s" % (badge, stt["weekday"], stt["now_new_york"], stt["reason"]))
        if not stt["open"] and stt.get("next_open"):
            st.caption("Next open: %s IST" % stt["next_open"])
        if not stt["calendar_known"]:
            st.warning("No NSE holiday list for this year yet: holidays are not known.")
        st.caption("Session 9:15 to 15:30 IST, flat by 15:15.")
        st.divider()
        st.caption("Workspace: `%s`" % TRADER)
        st.caption(NOTE)


# ---------------------------------------------------------------- formatting

def inr(x):
    return "" if x is None else "₹{:,.2f}".format(float(x))


def pct(x, digits=1):
    return "" if x is None else "{:.{d}f} %".format(100.0 * float(x), d=digits)


def rupees(text):
    """The tools print prices with $; on NSE they are rupees. Also keeps Streamlit from reading $...$ as maths."""
    return (text or "").replace("$", "₹")


def show_error(err):
    st.error(rupees(err) or "Something went wrong.")


# ---------------------------------------------------------------- charts

def session_bars(sym, interval, day):
    """The day's completed bars up to the clock (live or replay) as a DataFrame in IST, for drawing.
    Uses trader-entry's own Yahoo reader, so a replay never shows a bar from after its time."""
    entry = module("entry")
    now = ist_now()
    chart = entry.get_chart(sym, interval, day, today=now.date())
    step = 300 if interval == "5m" else 60
    rows = []
    for b in chart["bars"]:
        if b["t"] % step:
            continue  # Yahoo's live tick is not a bar
        t = entry.to_eastern(entry.utc_of(b["t"]))
        if t.date() != day or not (datetime.time(9, 15) <= t.time() < datetime.time(15, 30)):
            continue
        if t + datetime.timedelta(seconds=step) > now:
            continue  # still forming at the clock's time
        rows.append({"time": t, "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b["v"]})
    return pd.DataFrame(rows)


def candles(df, lines=None, marks=None, height=380):
    """Candlesticks with horizontal levels: lines = [(price, label, color)], marks = [(time, price, label)]."""
    if df.empty:
        st.info("No bars to draw for this session yet.")
        return
    base = alt.Chart(df).encode(
        x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M", tickCount=10)),
        color=alt.condition("datum.open <= datum.close", alt.value("#16a34a"), alt.value("#dc2626")),
    )
    lo = min(df["low"].min(), *(p for p, _, _ in (lines or []))) if lines else df["low"].min()
    hi = max(df["high"].max(), *(p for p, _, _ in (lines or []))) if lines else df["high"].max()
    pad = (hi - lo) * 0.05 or 1
    scale = alt.Scale(domain=[lo - pad, hi + pad], zero=False)
    tip = [alt.Tooltip("time:T", format="%H:%M"), "open:Q", "high:Q", "low:Q", "close:Q", "volume:Q"]
    wick = base.mark_rule().encode(y=alt.Y("low:Q", scale=scale, title="price"), y2="high:Q", tooltip=tip)
    body = base.mark_bar(size=6).encode(y=alt.Y("open:Q", scale=scale), y2="close:Q", tooltip=tip)
    layers = [wick, body]
    for price, label, color in lines or []:
        ldf = pd.DataFrame({"y": [price], "label": ["%s %s" % (label, inr(price))]})
        layers.append(alt.Chart(ldf).mark_rule(strokeDash=[4, 3], color=color).encode(y=alt.Y("y:Q", scale=scale)))
        layers.append(alt.Chart(ldf).mark_text(align="left", dx=4, dy=-6, color=color).encode(
            y=alt.Y("y:Q", scale=scale), text="label:N", x=alt.value(0)))
    if marks:
        mdf = pd.DataFrame([{"time": t, "y": p, "label": lab} for t, p, lab in marks])
        layers.append(alt.Chart(mdf).mark_point(shape="triangle-up", size=260, filled=True, color="#f59e0b",
                                                opacity=1, yOffset=14)
                      .encode(x="time:T", y=alt.Y("y:Q", scale=scale), tooltip=["label:N"]))
    st.altair_chart(alt.layer(*layers).properties(height=height), use_container_width=True)
