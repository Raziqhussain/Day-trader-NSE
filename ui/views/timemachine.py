import datetime

import altair as alt
import pandas as pd
import streamlit as st

import common

st.title("4. Time machine")
st.caption("Replays the rest of the session 10,000 times from the stock's own 5-minute bars over the last 60 "
           "days, plus every past day the same setup fired. A simulation, not a prediction.")

plan = common.read_json("plan.json")
sources = ["plan", "manual"] if plan else ["manual"]
source = st.radio("Replay", sources, horizontal=True,
                  format_func=lambda s: {"plan": "The saved plan (trader/plan.json)", "manual": "Numbers I type"}[s])
args = ["run", "--json"] + common.now_args()
if source == "plan":
    st.caption("%s %s %s: entry %s at %s, stop %s, target %s, flat by %s" % (
        plan.get("symbol"), plan.get("side"), plan.get("date"), common.inr(plan.get("entry")),
        plan.get("entry_time") or "-", common.inr(plan.get("stop")), common.inr(plan.get("target")),
        plan.get("flat_by")))
    args += ["--plan", "trader/plan.json"]
    flat_by = plan.get("flat_by") or "15:15"
else:
    c = st.columns(3)
    sym = c[0].text_input("Symbol", value=st.session_state.get("entry_symbol") or "RELIANCE.NS").strip().upper()
    day = c[1].date_input("Session date", value=common.ist_now().date())
    at = c[2].text_input("Entry bar's close", value="10:00 AM", help="On the 5-minute grid, e.g. 10:00 AM.")
    p = st.columns(3)
    entry = p[0].number_input("Entry (₹)", min_value=0.0, value=0.0, step=1.0)
    stop = p[1].number_input("Stop (₹)", min_value=0.0, value=0.0, step=1.0)
    target = p[2].number_input("Target (₹)", min_value=0.0, value=0.0, step=1.0)
    args += ["--plan", "trader/none.json", "--symbol", sym, "--date", day.isoformat(), "--entry", entry,
             "--stop", stop, "--target", target, "--entry-time", at.strip()]
    flat_by = "15:15"

o = st.columns(4)
replays = o[0].select_slider("Replays", [1000, 2000, 5000, 10000], value=10000)
seed = o[1].number_input("Seed", min_value=0, value=19, step=1, help="Same seed, same numbers.")
end = o[2].radio("End each replay at", ["flat", "close"], horizontal=True,
                 format_func=lambda e: {"flat": "flat-by %s" % flat_by, "close": "the 15:30 close"}[e])
save = o[3].checkbox("Save to trader/timemachine.json", value=True)
args += ["--replays", replays, "--seed", int(seed)]
if end == "flat":
    args += ["--until", flat_by]
if save:
    args += ["--write", "trader/timemachine.json"]

if st.button("Run the time machine", type="primary"):
    with st.spinner("Fetching 60 days of 5-minute bars and replaying %s sessions..." % "{:,}".format(replays)):
        doc, err, _ = common.run_tool("timemachine", args)
    st.session_state["tm"] = {"doc": doc, "err": err}

res = st.session_state.get("tm")
if res:
    st.divider()
    doc = res["doc"]
    if not doc:
        common.show_error(res["err"])
        st.stop()
    p, mc, hist = doc["plan"], doc["mc"], doc["history"]
    st.info("**%s**" % common.rupees(doc["verdict"]))
    for n in doc.get("verdict_notes") or []:
        st.caption(common.rupees(n))
    for w in doc.get("warnings") or []:
        st.warning(common.rupees(w))

    m = st.columns(5)
    m[0].metric("Target first", common.pct(mc["p_target"]))
    m[1].metric("Stop first", common.pct(mc["p_stop"]))
    m[2].metric("Neither by %s" % mc["until"], common.pct(mc["p_neither"]))
    m[3].metric("Green at the end", common.pct(mc["p_green"]))
    m[4].metric("Average R", "%+.3f" % mc["avg_R"])
    st.caption("%s replays of %d five-minute bars from %s to %s, drawn from %d full sessions (%s to %s), seed %d. "
               "Price at %s: median %s, 90 %% of replays between %s and %s."
               % ("{:,}".format(mc["replays"]), mc["bars_left"], p["entry_time"], mc["until"], mc["pool_sessions"],
                  mc["pool_from"], mc["pool_to"], mc["seed"], mc["until"], common.inr(mc["median_close"]),
                  common.inr(mc["p5_close"]), common.inr(mc["p95_close"])))

    # the fan: where the replays sat at each bar, 5th to 95th and 25th to 75th percentiles
    day = datetime.date.fromisoformat(p["date"])
    bands = pd.DataFrame(mc["bands"], columns=["p5", "p25", "p50", "p75", "p95"])
    bands["time"] = [datetime.datetime.combine(day, datetime.time.fromisoformat(t)) for t in mc["band_times"]]
    lo = min(bands["p5"].min(), p["stop"])
    hi = max(bands["p95"].max(), p["target"])
    pad = (hi - lo) * 0.05 or 1
    y = alt.Scale(domain=[lo - pad, hi + pad], zero=False)
    x = alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M"))
    fan = [
        alt.Chart(bands).mark_area(opacity=0.18, color="#2563eb").encode(x=x, y=alt.Y("p5:Q", scale=y, title="price"),
                                                                          y2="p95:Q"),
        alt.Chart(bands).mark_area(opacity=0.32, color="#2563eb").encode(x=x, y=alt.Y("p25:Q", scale=y), y2="p75:Q"),
        alt.Chart(bands).mark_line(color="#f59e0b", strokeWidth=2).encode(
            x=x, y=alt.Y("p50:Q", scale=y),
            tooltip=[alt.Tooltip("time:T", format="%H:%M"), "p5:Q", "p25:Q", "p50:Q", "p75:Q", "p95:Q"]),
    ]
    for price, label, color in ((p["target"], "target", "#16a34a"), (p["entry"], "entry", "#64748b"),
                                (p["stop"], "stop", "#dc2626")):
        ldf = pd.DataFrame({"y": [price], "label": ["%s %s" % (label, common.inr(price))]})
        fan.append(alt.Chart(ldf).mark_rule(strokeDash=[4, 3], color=color).encode(y=alt.Y("y:Q", scale=y)))
        fan.append(alt.Chart(ldf).mark_text(align="left", dx=4, dy=-6, color=color).encode(
            y=alt.Y("y:Q", scale=y), text="label:N", x=alt.value(0)))
    st.subheader("Where the replays went")
    st.altair_chart(alt.layer(*fan).properties(height=380), use_container_width=True)
    st.caption("Dark band: the middle half of the replays. Light band: 90 % of them. Line: the median.")

    st.subheader("History: the same rule on past sessions")
    if hist.get("rule"):
        h = st.columns(5)
        h[0].metric("Sessions", hist["sessions"])
        h[1].metric("Setup fired", hist["triggered"])
        h[2].metric("Target / stop / neither", "%d / %d / %d" % (hist["target"], hist["stop"], hist["close"]))
        h[3].metric("Green", hist["green"])
        h[4].metric("Average R", "%+.3f" % hist["avg_R"])
        if hist["trades"]:
            st.dataframe(pd.DataFrame(hist["trades"]).rename(columns=str.capitalize), hide_index=True,
                         use_container_width=True)
    else:
        st.caption(hist.get("note", "No history for this setup."))
    st.caption(doc.get("note", ""))
