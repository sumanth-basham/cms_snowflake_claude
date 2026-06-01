"""
streamlit_app/app.py – Main Streamlit entry point.

Provides a multi-page interface for:
  • Asking natural-language CMS questions via the Cortex Agent API.
  • Generating and running Streamlit dashboard code produced by Claude.
  • Browsing pre-built dashboards (see pages/).
"""

from __future__ import annotations

import os

import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CMS Snowflake + Claude Analytics",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar: API endpoint configuration ─────────────────────────────────────
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/f/ff/Snowflake_Logo.svg", width=140)
    st.markdown("## ⚙️ Configuration")
    api_base = st.text_input(
        "Cortex Agent API URL",
        value=os.getenv("CMS_API_URL", "http://localhost:8000"),
        help="Base URL of the FastAPI backend (api/main.py).",
    )
    st.session_state["api_base"] = api_base
    st.divider()
    st.caption("CMS Snowflake + Claude  •  v1.0")

# ── Home page ────────────────────────────────────────────────────────────────
st.title("🏥 CMS Snowflake + Claude Analytics")
st.markdown(
    """
Welcome to the **CMS Medicare Analytics** portal powered by
**Snowflake Cortex Analyst** and **Claude AI**.

### How it works
1. **Ask a question** in plain English → Cortex Analyst translates it to SQL
   using the CMS semantic model.
2. **Results are returned** with an optional Claude-generated executive summary.
3. **Generate dashboards** → Claude writes Streamlit / Plotly code on the fly.

### Pages
| Page | Description |
|------|-------------|
| 🔍 Ask CMS | Natural-language Q&A with Cortex Analyst |
| 📊 Dashboard Builder | Generate & run Streamlit dashboards with Claude |
| 💊 Drug Utilization | Pre-built Part-D drug spend dashboard |
| 🏆 Quality Measures | Pre-built provider star-rating dashboard |
| 💡 Claims Analysis | Pre-built fee-for-service claims dashboard |

Use the **sidebar navigation** (↑ above) to explore.
"""
)

st.info(
    "👈 Select a page from the sidebar to get started, "
    "or configure the API URL if you're running the backend locally.",
    icon="ℹ️",
)
