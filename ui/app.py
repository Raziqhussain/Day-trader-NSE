"""Day Trader NSE: a local web UI over the skill tools.

    cd ~/Daytrader && .venv-ui/bin/streamlit run day-trader-skill/ui/app.py

The workspace is the folder you start it from (or TRADER_HOME); the tools keep their files in its trader/.
"""
import os

import streamlit as st

import common

st.set_page_config(page_title="Day Trader NSE", page_icon=":chart_with_upwards_trend:", layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
pages = [
    st.Page(os.path.join(HERE, "views", "home.py"), title="Home", icon=":material/home:", default=True),
    st.Page(os.path.join(HERE, "views", "scanner.py"), title="1. Scanner", icon=":material/search:"),
    st.Page(os.path.join(HERE, "views", "entry.py"), title="2. Entry", icon=":material/login:"),
    st.Page(os.path.join(HERE, "views", "exit.py"), title="3. Exit plan", icon=":material/logout:"),
    st.Page(os.path.join(HERE, "views", "timemachine.py"), title="4. Time machine", icon=":material/history:"),
]
nav = st.navigation(pages)
common.sidebar()
nav.run()
