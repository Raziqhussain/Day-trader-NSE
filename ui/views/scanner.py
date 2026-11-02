import os
import re

import pandas as pd
import streamlit as st

import common

LABELS = {"breakout_20d": "20-day closing-high breakout", "bull_flag": "bull flag",
          "reclaim_ma20": "reclaimed the 20-day average", "oversold": "oversold (RSI under 30)",
          "oversold_bounce": "oversold bounce", "orb": "opening-range breakout"}

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


left, right = st.columns([1, 2])
with left:
    mode = st.radio("Scan", ["orb", "daily"], horizontal=True,
                    format_func=lambda m: {"orb": "Opening-range breakouts", "daily": "Daily setups"}[m],
                    help="Opening-range breakouts run during the session, from 9:35 IST. Daily setups use "
                         "closes through the last session, so run them before the open.")
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
    min_price = f1.number_input("Min price (₹)", min_value=0.0, value=5.0, step=5.0)
    min_volume = f2.number_input("Min volume (shares)", min_value=0, step=100000,
                                 value=0 if mode == "orb" else 1000000,
                                 help="orb: the day's volume so far. daily: the last session's volume.")
    if mode == "orb":
        or_minutes = f3.selectbox("Opening range", [15, 30, 5, 10, 20, 45, 60], format_func=lambda m: "%d min" % m)
        g1, g2 = st.columns(2)
        at = g1.text_input("Cut the clock at (HH:MM, optional)", placeholder="e.g. 10:00",
                           help="Replay today up to this time. Leave blank to scan up to now.")
        max_confirm = g2.number_input("Charts to confirm with highs and lows", min_value=0, value=200,
                                      help="0 checks every candidate (slower on a big list).")
    save = st.checkbox("Save the hits to trader/watchlist.json (the Entry page reads it)", value=True)
    go = st.button("Run the scan", type="primary", disabled=not symbols)

if go:
    args = [mode, "--symbols", ",".join(symbols), "--json", "--min-price", min_price,
            "--min-volume", int(min_volume)] + common.now_args()
    if mode == "orb":
        args += ["--or-minutes", or_minutes, "--max-confirm", int(max_confirm)]
        if at.strip():
            args += ["--at", at.strip()]
    if not save:
        args.append("--no-write")
    with st.spinner("Reading %d charts from Yahoo..." % len(symbols)):
        doc, err, code = common.run_tool("scanner", args)
    st.session_state["scan"] = {"doc": doc, "err": err, "mode": mode}

res = st.session_state.get("scan")
if res:
    st.divider()
    doc = res["doc"]
    if not doc:
        common.show_error(res["err"])
    else:
        counts = doc.get("counts", {})
        m = st.columns(5)
        m[0].metric("Symbols", doc["universe"])
        m[1].metric("Charts fetched", counts.get("fetched", 0))
        m[2].metric("Usable" if doc["mode"] == "orb" else "Scanned", doc["scanned"])
        m[3].metric("Matched a rule", len(doc["hits"]))
        as_of = (doc.get("as_of") or "-").split(" ", 1)
        m[4].metric("As of %s" % as_of[0] if len(as_of) > 1 else "As of", as_of[-1])
        if doc.get("failed"):
            st.caption("%d symbol(s) failed or had no data from Yahoo." % doc["failed"])
        if doc.get("unconfirmed"):
            st.warning("PARTIAL: %d more candidates were not checked with real highs and lows." % doc["unconfirmed"])
        hits = doc["hits"]
        if not hits:
            st.info("No chart matched. On a quiet morning that is a normal answer.")
        else:
            if doc["mode"] == "orb":
                df = pd.DataFrame([{"Broke out at": h["at"], "Symbol": h["symbol"], "Close": h["price"],
                                    "Range low": h["or_low"], "Range high": h["or_high"],
                                    "% over the high": h["pct_over"]} for h in hits])
            else:
                df = pd.DataFrame([{"Symbol": h["symbol"], "Setups": ", ".join(LABELS.get(t, t) for t in h["setups"]),
                                    "Close": h["price"], "RSI 14": h["rsi"], "Volume": h["volume"],
                                    "Close date": h["close_date"]} for h in hits])
            st.dataframe(df, hide_index=True, use_container_width=True,
                         column_config={"Close": st.column_config.NumberColumn(format="₹%.2f"),
                                        "Range low": st.column_config.NumberColumn(format="₹%.2f"),
                                        "Range high": st.column_config.NumberColumn(format="₹%.2f"),
                                        "% over the high": st.column_config.NumberColumn(format="%.2f %%")})
            pick = st.selectbox("Pick one chart to check its entry", [h["symbol"] for h in hits])
            if st.button("Check the entry for %s" % pick):
                st.session_state["entry_symbol"] = pick
                st.switch_page("views/entry.py")
        st.caption(doc.get("note", ""))
