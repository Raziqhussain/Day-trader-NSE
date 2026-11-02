import datetime

import streamlit as st

import common

st.title("2. Entry")
st.caption("Watches one setup bar by bar. A trigger is the first completed bar that CLOSES above the level. "
           "Long side only. Nothing is placed.")

wl = common.read_json("watchlist.json") or {}
hits = [h["symbol"] for h in wl.get("hits", []) if h.get("symbol")]
default = st.session_state.get("entry_symbol") or (hits[0] if hits else "RELIANCE.NS")

c = st.columns([2, 1, 1, 1, 1])
if hits:
    options = hits + ([default] if default not in hits else [])
    sym = c[0].selectbox("Symbol (from the last scan)", options, index=options.index(default),
                         accept_new_options=True)
else:
    sym = c[0].text_input("Symbol", value=default)
sym = (sym or "").strip().upper()
setup = c[1].selectbox("Setup", ["orb", "level"],
                       format_func=lambda s: {"orb": "Opening-range breakout", "level": "Close above a level"}[s])
interval = c[2].selectbox("Bars", ["5m", "1m"], format_func=lambda i: {"5m": "5-minute", "1m": "1-minute"}[i])
or_minutes = c[3].selectbox("Opening range", [15, 30, 5, 10, 20, 45, 60], format_func=lambda m: "%d min" % m,
                            disabled=setup != "orb")
vol_x = c[4].number_input("Volume x (optional)", min_value=0.0, value=0.0, step=0.5,
                          help="Also need the trigger bar's volume at this multiple of the range bars' average. "
                               "0 = off.")
level = None
if setup == "level":
    level = st.number_input("Close above (₹)", min_value=0.0, value=0.0, step=1.0)
save = st.checkbox("Save to trader/entry.json (the Exit page reads it)", value=True)

if st.button("Check now", type="primary", disabled=not sym or (setup == "level" and not level)):
    args = ["check", sym, "--json", "--setup", setup, "--interval", interval,
            "--or-minutes", or_minutes] + common.now_args()
    if level:
        args += ["--level", level]
    if vol_x:
        args += ["--min-volume-x", vol_x]
    if save:
        args += ["--write", "trader/entry.json"]
    with st.spinner("Reading %s bars for %s..." % (interval, sym)):
        doc, err, _ = common.run_tool("entry", args)
    st.session_state["entry"] = {"doc": doc, "err": err, "symbol": sym, "interval": interval, "saved": save}

res = st.session_state.get("entry")
if res:
    st.divider()
    doc = res["doc"]
    if not doc:
        common.show_error(res["err"])
        st.stop()
    status = doc["status"]
    text = "**%s %s** on %s: %s" % (doc["symbol"], status.upper(), doc["date"], common.rupees(doc.get("reason")))
    {"triggered": st.success, "waiting": st.info, "expired": st.warning}.get(status, st.error)(text)
    if doc.get("lag_note"):
        st.caption(doc["lag_note"])

    orng, trig, last = doc.get("opening_range") or {}, doc.get("trigger"), doc.get("last") or {}
    m = st.columns(5)
    if doc["setup"] == "orb":
        m[0].metric("Range high", common.inr(orng.get("high")))
        m[1].metric("Range low", common.inr(orng.get("low")))
    else:
        m[0].metric("Level", common.inr(doc.get("level")))
    if trig:
        m[2].metric("Trigger", common.inr(trig["price"]), "%+.2f %% over" % trig["pct_over"])
        m[3].metric("Triggered at (bar %d)" % trig["bar_index"], trig["time"])
    elif last:
        m[2].metric("Last close", common.inr(last.get("close")), "%+.2f %% vs level" % (last.get("vs_level_pct") or 0))
    m[4].metric("Previous close", common.inr(doc.get("prev_close")))
    st.caption("Entries allowed %s to %s IST; session %s to %s. Data as of %s IST (Yahoo, can lag)."
               % (doc.get("no_entries_before"), doc.get("no_entries_after"), doc.get("opens"), doc.get("closes"),
                  doc.get("data_time") or doc.get("now")))

    try:
        day = datetime.date.fromisoformat(doc["date"])
        df = common.session_bars(doc["symbol"], res["interval"], day)
    except Exception as e:  # the chart is a picture; the status above is the answer
        st.caption("No chart: %s" % e)
    else:
        lines = []
        if doc["setup"] == "orb" and orng.get("high"):
            lines = [(orng["high"], "range high", "#2563eb"), (orng["low"], "range low", "#64748b")]
        elif doc.get("level"):
            lines = [(doc["level"], "level", "#2563eb")]
        marks = []
        if trig:
            t = datetime.datetime.combine(day, datetime.time.fromisoformat(trig["bar_start"]))
            marks = [(t, trig["price"], "trigger %s at %s" % (common.inr(trig["price"]), trig["time"]))]
        common.candles(df, lines, marks)

    if status == "triggered" and res["saved"]:
        st.write("Saved to `trader/entry.json`. Next, set the stop and the target before you get in.")
        if st.button("Plan the exit", type="primary"):
            st.switch_page("views/exit.py")
    elif status == "waiting":
        st.caption("Check again after the next bar closes. A bar counts only once it is complete.")
