import datetime
import os
import re

import pandas as pd
import streamlit as st

import common

LABELS = {"breakout_20d": "20-day closing-high breakout", "bull_flag": "bull flag",
          "reclaim_ma20": "reclaimed the 20-day average", "oversold": "oversold (RSI under 30)",
          "oversold_bounce": "oversold bounce", "orb": "opening-range breakout"}
NSE_UNIVERSE = os.path.join(common.TRADER, "universe-nse.txt")
NSE_CSV = os.path.join(common.TRADER, "EQUITY_L.csv")
NSE_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
CRORE = 1e7

st.title("1. Scanner")
st.caption("Lists the charts that match a rule. A scan is a list of charts that match a rule, not a list of "
           "stocks to buy.")


def load_symbols():
    if os.path.exists(common.SYMBOLS_FILE):
        with open(common.SYMBOLS_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    return "\n".join(common.STARTER_SYMBOLS)


def parse_symbols(text):
    out = []
    for s in re.split(r"[,\s]+", text.upper()):
        s = s.split("|")[0].strip()
        if s and not s.startswith("#") and s not in out:
            out.append(s)
    return out


def universe_info():
    if not os.path.exists(NSE_UNIVERSE):
        return 0, None
    with open(NSE_UNIVERSE, encoding="utf-8") as fh:
        n = sum(1 for ln in fh if ln.strip())
    return n, datetime.date.fromtimestamp(os.path.getmtime(NSE_UNIVERSE))


def build_universe(offline=None):
    args = ["universe", "--exchange", "nse", "--json"] + (["--offline", common.rel(offline)] if offline else [])
    with st.spinner("Building the NSE stock list..."):
        doc, err, _ = common.run_tool("scanner", args, timeout=120)
    if doc:
        st.toast("NSE list ready: %s EQ-series stocks" % "{:,}".format(doc["count"]))
        st.rerun()
    st.session_state["universe_err"] = err


left, right = st.columns([1, 2])
with left:
    source = st.radio("Stocks to scan", ["all", "list"], horizontal=True,
                      format_func=lambda s: {"all": "All NSE stocks", "list": "My list"}[s])
    mode = st.radio("Scan", ["orb", "daily"], horizontal=True,
                    format_func=lambda m: {"orb": "Opening-range breakouts", "daily": "Daily setups"}[m],
                    help="Opening-range breakouts run during the session, from 9:35 IST. Daily setups use "
                         "closes through the last session, so run them before the open.")
    symbols = []
    if source == "all":
        n, updated = universe_info()
        if n:
            st.success("%s EQ-series NSE stocks (list from %s)." % ("{:,}".format(n), updated.isoformat()))
        else:
            st.info("First, the list of every NSE stock. NSE does not send it to scripts, so download it once "
                    "in your browser and drop it here.")
        with st.expander("Update the NSE stock list" if n else "Get the NSE stock list", expanded=not n):
            st.link_button("1. Download EQUITY_L.csv from NSE", NSE_CSV_URL)
            up = st.file_uploader("2. Drop EQUITY_L.csv here", type=["csv"])
            if up is not None and st.session_state.get("nse_upload") != up.file_id:
                st.session_state["nse_upload"] = up.file_id   # once per file: the uploader keeps it across reruns
                os.makedirs(common.TRADER, exist_ok=True)
                with open(NSE_CSV, "wb") as fh:
                    fh.write(up.getvalue())
                build_universe(NSE_CSV)
            if st.button("Or try the download from here"):
                build_universe()
            if st.session_state.get("universe_err"):
                common.show_error(st.session_state["universe_err"])
            st.caption("Only the EQ series is kept: BE and BZ stocks settle trade for trade and cannot be day "
                       "traded.")
    else:
        text = st.text_area("NSE symbols (keep the .NS)", value=load_symbols(), height=220)
        symbols = parse_symbols(text)
        c1, c2 = st.columns(2)
        if c1.button("Save list", use_container_width=True, help="Saved to trader/nse_symbols.txt"):
            os.makedirs(common.TRADER, exist_ok=True)
            with open(common.SYMBOLS_FILE, "w", encoding="utf-8") as fh:
                fh.write("\n".join(symbols) + "\n")
            st.toast("Saved %d symbols to trader/nse_symbols.txt" % len(symbols))
        if c2.button("Reset", use_container_width=True, help="Back to the starter list"):
            if os.path.exists(common.SYMBOLS_FILE):
                os.remove(common.SYMBOLS_FILE)
            st.rerun()
        no_dot = [s for s in symbols if not s.endswith((".NS", ".BO"))]
        if no_dot:
            st.warning("Without .NS Yahoo reads these as US tickers: %s" % ", ".join(no_dot[:8]))

with right:
    f1, f2, f3 = st.columns(3)
    min_price = f1.number_input("Min price (₹)", min_value=0.0, value=50.0 if source == "all" else 5.0,
                                step=5.0, help="Very low-priced stocks move in big ticks and are easy to "
                                               "manipulate; 50 keeps most of them out of an all-NSE scan.")
    min_volume = f2.number_input("Min volume (shares)", min_value=0, step=100000,
                                 value=0 if mode == "orb" else 1000000,
                                 help="orb: the day's volume so far. daily: the last session's volume.")
    if mode == "orb":
        or_minutes = f3.selectbox("Opening range", [15, 30, 5, 10, 20, 45, 60], format_func=lambda m: "%d min" % m)
        g1, g2 = st.columns(2)
        at = g1.text_input("Cut the clock at (HH:MM, optional)", placeholder="e.g. 10:00",
                           help="Replay today up to this time. Leave blank to scan up to now.")
        max_confirm = g2.number_input("Charts to confirm with highs and lows", min_value=0, value=200,
                                      help="The most traded candidates are confirmed first. 0 checks every "
                                           "candidate (slow on all of NSE).")
    save = st.checkbox("Save the hits to trader/watchlist.json (the Entry page reads it)", value=True)
    count = universe_info()[0] if source == "all" else len(symbols)
    if count:
        secs = int(count / 20 * 0.8 + (min(count, 200) * 0.5 if mode == "orb" else 0))
        st.caption("%s stocks: about %s for Yahoo to answer." % ("{:,}".format(count),
                                                               "%d min" % max(1, round(secs / 60)) if secs > 90
                                                               else "%d seconds" % max(5, secs)))
    go = st.button("Run the scan", type="primary", disabled=not count)

if go:
    args = [mode, "--json", "--min-price", min_price, "--min-volume", int(min_volume)] + common.now_args()
    args += ["--universe", common.rel(NSE_UNIVERSE)] if source == "all" else ["--symbols", ",".join(symbols)]
    if mode == "orb":
        args += ["--or-minutes", or_minutes, "--max-confirm", int(max_confirm)]
        if at.strip():
            args += ["--at", at.strip()]
    if not save:
        args.append("--no-write")
    with st.spinner("Reading %s charts from Yahoo..." % "{:,}".format(count)):
        doc, err, code = common.run_tool("scanner", args, timeout=1800)
    st.session_state["scan"] = {"doc": doc, "err": err, "mode": mode}


def shortlist_orb(hits):
    """Breakouts a day trader can act on, by plain rules: liquid now, a stop close by, not run away yet.
    Ranked by rupees traded so far. A rules filter, not a recommendation."""
    st.subheader("Day-trade shortlist")
    st.caption("Ranked by rules, not a recommendation: the breakouts that are liquid now, have a stop close "
               "by (the opening-range midpoint, the Exit page's default) and have not run far past the range "
               "yet, most traded first.")
    r = st.columns(4)
    min_cr = r[0].number_input("Traded so far, at least (₹ crore)", min_value=0.0, value=10.0, step=5.0)
    max_stop = r[1].number_input("Stop no further than (%)", min_value=0.1, value=1.5, step=0.1,
                                 help="From the close to the opening-range midpoint.")
    max_ext = r[2].number_input("No more than this % over the range high", min_value=0.0, value=1.0, step=0.1)
    top = r[3].number_input("Show the top", min_value=1, value=10, step=1)
    rows = []
    for h in hits:
        mid = (h["or_high"] + h["or_low"]) / 2.0
        stop_pct = (h["price"] - mid) / h["price"] * 100.0
        cr = (h.get("turnover") or 0) / CRORE
        if cr < min_cr or stop_pct > max_stop or h["pct_over"] > max_ext:
            continue
        rows.append({"Symbol": h["symbol"], "Close": h["price"], "Broke out at": h["at"],
                     "Traded (₹ cr)": round(cr, 1), "Stop distance %": round(stop_pct, 2),
                     "% over range high": h["pct_over"],
                     "Why": "₹%.0f cr traded, stop %.2f %% away, %.2f %% over the high" % (cr, stop_pct,
                                                                                            h["pct_over"])})
    rows.sort(key=lambda x: -x["Traded (₹ cr)"])
    rows = rows[:int(top)]
    if not rows:
        st.info("No breakout passes these rules. Loosen them, or wait for the next bar.")
        return []
    df = pd.DataFrame(rows)
    df.insert(0, "Rank", range(1, len(df) + 1))
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Close": st.column_config.NumberColumn(format="₹%.2f"),
                                "Stop distance %": st.column_config.NumberColumn(format="%.2f %%"),
                                "% over range high": st.column_config.NumberColumn(format="%.2f %%")})
    st.caption("A breakout from earlier in the morning may have moved on: check it on the Entry page before "
               "anything else. Most people who day trade lose money.")
    return [x["Symbol"] for x in rows]


def shortlist_daily(hits):
    st.subheader("Shortlist for tomorrow's watchlist")
    st.caption("Ranked by rules, not a recommendation: the setups with the most rupees traded in the last "
               "session (liquid enough to day trade), top first.")
    r = st.columns(2)
    min_cr = r[0].number_input("Traded last session, at least (₹ crore)", min_value=0.0, value=20.0, step=5.0)
    top = r[1].number_input("Show the top", min_value=1, value=10, step=1)
    rows = []
    for h in hits:
        cr = h["price"] * h["volume"] / CRORE
        if cr >= min_cr:
            rows.append({"Symbol": h["symbol"], "Setups": ", ".join(LABELS.get(t, t) for t in h["setups"]),
                         "Close": h["price"], "RSI 14": h["rsi"], "Traded (₹ cr)": round(cr, 1)})
    rows.sort(key=lambda x: -x["Traded (₹ cr)"])
    rows = rows[:int(top)]
    if not rows:
        st.info("No setup passes the turnover floor.")
        return []
    df = pd.DataFrame(rows)
    df.insert(0, "Rank", range(1, len(df) + 1))
    st.dataframe(df, hide_index=True, use_container_width=True,
                 column_config={"Close": st.column_config.NumberColumn(format="₹%.2f")})
    st.caption("Watch these after the open: the Entry page tells you if and when a setup triggers.")
    return [x["Symbol"] for x in rows]


res = st.session_state.get("scan")
if res:
    st.divider()
    doc = res["doc"]
    if not doc:
        common.show_error(res["err"])
    else:
        counts = doc.get("counts", {})
        m = st.columns(5)
        m[0].metric("Stocks", "{:,}".format(doc["universe"]))
        m[1].metric("Charts fetched", "{:,}".format(counts.get("fetched", 0)))
        m[2].metric("Usable" if doc["mode"] == "orb" else "Scanned", "{:,}".format(doc["scanned"]))
        m[3].metric("Matched a rule", len(doc["hits"]))
        as_of = (doc.get("as_of") or "-").split(" ", 1)
        m[4].metric("As of %s" % as_of[0] if len(as_of) > 1 else "As of", as_of[-1])
        if doc.get("failed"):
            st.caption("%s stock(s) failed or had no data from Yahoo." % "{:,}".format(doc["failed"]))
        if doc.get("unconfirmed"):
            st.warning("PARTIAL: %s more candidates were not checked with real highs and lows (the most traded "
                       "were)." % "{:,}".format(doc["unconfirmed"]))
        hits = doc["hits"]
        if not hits:
            st.info("No chart matched. On a quiet morning that is a normal answer.")
        else:
            short = shortlist_orb(hits) if doc["mode"] == "orb" else shortlist_daily(hits)
            with st.expander("Every chart that matched (%d)" % len(hits), expanded=not short):
                if doc["mode"] == "orb":
                    df = pd.DataFrame([{"Broke out at": h["at"], "Symbol": h["symbol"], "Close": h["price"],
                                        "Range low": h["or_low"], "Range high": h["or_high"],
                                        "% over the high": h["pct_over"],
                                        "Traded (₹ cr)": round((h.get("turnover") or 0) / CRORE, 1)}
                                       for h in hits])
                else:
                    df = pd.DataFrame([{"Symbol": h["symbol"],
                                        "Setups": ", ".join(LABELS.get(t, t) for t in h["setups"]),
                                        "Close": h["price"], "RSI 14": h["rsi"], "Volume": h["volume"],
                                        "Close date": h["close_date"]} for h in hits])
                st.dataframe(df, hide_index=True, use_container_width=True,
                             column_config={"Close": st.column_config.NumberColumn(format="₹%.2f"),
                                            "Range low": st.column_config.NumberColumn(format="₹%.2f"),
                                            "Range high": st.column_config.NumberColumn(format="₹%.2f"),
                                            "% over the high": st.column_config.NumberColumn(format="%.2f %%")})
            options = short + [h["symbol"] for h in hits if h["symbol"] not in short]
            pick = st.selectbox("Pick one chart to check its entry", options)
            if st.button("Check the entry for %s" % pick):
                st.session_state["entry_symbol"] = pick
                st.switch_page("views/entry.py")
        st.caption(doc.get("note", ""))
