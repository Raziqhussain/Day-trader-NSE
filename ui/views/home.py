import streamlit as st

import common

st.title("Day Trader NSE")
st.write("A local workbench over the Day Trader skills, on NSE hours (9:15 to 15:30 IST, flat by 15:15). "
         "Each page runs the skill's own tool, so the rules are the same ones the skills use.")

steps = [
    ("1. Scanner", "Lists the charts that match a rule: opening-range breakouts during the session, "
                   "or daily setups before the open.", "watchlist.json"),
    ("2. Entry", "Watches one setup bar by bar and says waiting, triggered or expired.", "entry.json"),
    ("3. Exit plan", "Sets the stop and the target before you get in.", "plan.json"),
    ("4. Time machine", "Replays the rest of the session 10,000 times, plus every past day the setup fired.",
     "timemachine.json"),
]
cols = st.columns(4)
for col, (name, what, out) in zip(cols, steps):
    with col:
        st.subheader(name)
        st.write(what)
        doc = common.read_json(out)
        if doc:
            st.caption("Last saved: `trader/%s`" % out)
        else:
            st.caption("Writes `trader/%s`" % out)

st.divider()
st.markdown(
    "- **Data:** free Yahoo Finance 5-minute bars. They are unofficial, can lag and are never tick by tick.\n"
    "- **Replay a past day:** type a time in the sidebar, like `2026-10-30 10:00`. Yahoo keeps about 60 days "
    "of 5-minute bars.\n"
    "- **Orders:** this UI cannot place one. Sizing, the risk check and the broker stay in the skills.\n"
    "- A scan is a list of charts that match a rule, not a list of stocks to buy. Most people who day trade "
    "lose money.")
st.caption(common.NOTE)
