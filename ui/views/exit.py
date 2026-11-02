import datetime

import streamlit as st

import common

st.title("3. Exit plan")
st.caption("Sets the stop and the target before you get in, so you know when to get out. Out by the flat-by "
           "time (15:15 IST) win or lose: no overnight hold.")

saved = common.read_json("entry.json")
sources = ["entry", "manual"] if saved else ["manual"]
source = st.radio("Plan from", sources, horizontal=True,
                  format_func=lambda s: {"entry": "The saved entry (trader/entry.json)", "manual": "Numbers I type"}[s])
args = ["plan", "--json"] + common.now_args()
if source == "entry":
    st.caption("%s %s %s, %s at %s" % (saved.get("symbol"), saved.get("status", ""), saved.get("date", ""),
                                       common.inr(saved.get("price")), saved.get("time") or "-"))
    args += ["--from", "trader/entry.json"]
    stop_choices = ["or-mid", "or-low", "pct", "atr", "price"]
else:
    c = st.columns(4)
    sym = c[0].text_input("Symbol", value=st.session_state.get("entry_symbol") or "RELIANCE.NS").strip().upper()
    entry = c[1].number_input("Entry (₹)", min_value=0.0, value=0.0, step=1.0)
    or_high = c[2].number_input("Range high (₹, optional)", min_value=0.0, value=0.0, step=1.0)
    or_low = c[3].number_input("Range low (₹, optional)", min_value=0.0, value=0.0, step=1.0)
    d = st.columns(3)
    day = d[0].date_input("Session date", value=common.ist_now().date())
    at = d[1].text_input("Entry time (optional)", placeholder="10:00 AM")
    bar = d[2].number_input("Entry bar (optional, 0 = first)", min_value=-1, value=-1, step=1,
                            help="-1 leaves it out.")
    args += ["--symbol", sym, "--entry", entry, "--date", day.isoformat()]
    if or_high and or_low:
        args += ["--or-high", or_high, "--or-low", or_low]
    if at.strip():
        args += ["--time", at.strip()]
    if bar >= 0:
        args += ["--entry-bar", int(bar)]
    stop_choices = (["or-mid", "or-low"] if (or_high and or_low) else []) + ["pct", "atr", "price"]

labels = {"or-mid": "Opening-range midpoint", "or-low": "Opening-range low", "pct": "A percent under the entry",
          "atr": "A multiple of the ATR", "price": "A price I choose"}
s = st.columns(4)
stop = s[0].selectbox("Stop", stop_choices, format_func=labels.get)
stop_arg = stop
if stop == "pct":
    stop_arg = "pct:%s" % s[1].number_input("Percent", min_value=0.1, value=1.0, step=0.1)
elif stop == "atr":
    stop_arg = "atr:%s" % s[1].number_input("ATR multiple", min_value=0.5, value=1.5, step=0.5)
elif stop == "price":
    stop_arg = "price:%s" % s[1].number_input("Stop price (₹)", min_value=0.0, value=0.0, step=1.0)
target = s[2].selectbox("Target", ["2R", "1R", "1.5R", "3R", "price"],
                        format_func=lambda t: "A price I choose" if t == "price" else "%s (%s times the risk)" % (t, t[:-1]))
target_arg = target
if target == "price":
    target_arg = "price:%s" % s[3].number_input("Target price (₹)", min_value=0.0, value=0.0, step=1.0)
f = st.columns(2)
flat_by = f[0].text_input("Flat by (IST)", value="15:15")
save = f[1].checkbox("Save to trader/plan.json (the Time machine reads it)", value=True)
args += ["--stop", stop_arg, "--target", target_arg, "--flat-by", flat_by.strip() or "15:15"]
if save:
    args += ["--write", "trader/plan.json"]

if st.button("Make the plan", type="primary"):
    with st.spinner("Working out the stop and the target..."):
        doc, err, _ = common.run_tool("exit", args)
    st.session_state["plan"] = {"doc": doc, "err": err, "saved": save}

res = st.session_state.get("plan")
if res:
    st.divider()
    doc = res["doc"]
    if not doc:
        common.show_error(res["err"])
        st.stop()
    m = st.columns(6)
    m[0].metric("Entry", common.inr(doc["entry"]))
    m[1].metric("Stop", common.inr(doc["stop"]))
    m[2].metric("Target", common.inr(doc["target"]))
    m[3].metric("Risk a share", common.inr(doc["risk_per_share"]))
    m[4].metric("Reward:risk", doc["reward_risk"])
    m[5].metric("Flat by", "%s IST" % doc["flat_by"])
    st.caption("Entry %s. Stop at the %s: %s. Target %s. The risk is %.2f %% of the entry."
               % (doc.get("entry_time") or "planned ahead", doc.get("stop_label"),
                  common.rupees(doc.get("stop_detail")), doc.get("target_label"),
                  100.0 * doc["risk_per_share"] / doc["entry"]))
    for w in doc.get("warnings") or []:
        st.warning(common.rupees(w))
    try:
        df = common.session_bars(doc["symbol"], doc.get("interval") or "5m", datetime.date.fromisoformat(doc["date"]))
        common.candles(df, [(doc["target"], "target", "#16a34a"), (doc["entry"], "entry", "#2563eb"),
                            (doc["stop"], "stop", "#dc2626")])
    except Exception as e:
        st.caption("No chart: %s" % e)
    st.caption(doc.get("note", ""))
    if res["saved"]:
        st.write("Saved to `trader/plan.json`.")
        if st.button("Replay it in the time machine", type="primary"):
            st.switch_page("views/timemachine.py")
