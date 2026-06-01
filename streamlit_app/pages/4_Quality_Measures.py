"""
pages/4_Quality_Measures.py – Pre-built quality star-ratings dashboard.
"""

from __future__ import annotations

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Quality Measures", page_icon="🏆", layout="wide")
st.title("🏆 CMS Quality Measures & Star Ratings")
st.markdown("Provider performance rates vs national averages, and CMS star ratings.")

API_BASE = st.session_state.get("api_base", "http://localhost:8000")


@st.cache_data(ttl=300, show_spinner="Loading quality data…")
def load_quality_data(api_base: str) -> pd.DataFrame:
    resp = httpx.post(
        f"{api_base}/api/sql",
        json={
            "sql": """
                SELECT
                    p.PROVIDER_NAME,
                    p.STATE,
                    p.SPECIALTY,
                    qm.MEASURE_NAME,
                    qm.MEASURE_DOMAIN,
                    qm.PERFORMANCE_RATE,
                    qm.NATIONAL_AVERAGE,
                    qm.STAR_RATING,
                    qm.REPORTING_YEAR,
                    (qm.PERFORMANCE_RATE - qm.NATIONAL_AVERAGE) AS DELTA_VS_NATIONAL
                FROM CMS_DB.ANALYTICS.QUALITY_MEASURES qm
                JOIN CMS_DB.ANALYTICS.PROVIDERS p ON qm.PROVIDER_ID = p.PROVIDER_ID
                ORDER BY DELTA_VS_NATIONAL DESC
            """
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    return pd.DataFrame(result["data"], columns=result["columns"])


try:
    df = load_quality_data(API_BASE)
except Exception as exc:
    st.error(f"Failed to load data from API ({API_BASE}): {exc}")
    st.info("Make sure the FastAPI backend is running: `uvicorn api.main:app --reload`")
    st.stop()

# Numeric coercion
for col in ("PERFORMANCE_RATE", "NATIONAL_AVERAGE", "DELTA_VS_NATIONAL", "STAR_RATING"):
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    domains = sorted(df["MEASURE_DOMAIN"].dropna().unique().tolist())
    selected_domain = st.multiselect("Care Domain", domains, default=domains)
    if selected_domain:
        df = df[df["MEASURE_DOMAIN"].isin(selected_domain)]
    min_stars = st.slider("Minimum Star Rating", 1, 5, 1)
    df = df[df["STAR_RATING"] >= min_stars]

# ── KPIs ──────────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Avg Performance Rate", f"{df['PERFORMANCE_RATE'].mean():.1f}%")
c2.metric("Avg National Average", f"{df['NATIONAL_AVERAGE'].mean():.1f}%")
c3.metric("Above National Avg", f"{(df['DELTA_VS_NATIONAL'] > 0).sum()} measures")

st.divider()

# ── Grouped bar: performance vs national average ──────────────────────────────
fig_bar = px.bar(
    df,
    x="PROVIDER_NAME",
    y=["PERFORMANCE_RATE", "NATIONAL_AVERAGE"],
    barmode="group",
    color_discrete_map={"PERFORMANCE_RATE": "#1f77b4", "NATIONAL_AVERAGE": "#ff7f0e"},
    title="Provider Performance Rate vs National Average",
    labels={"value": "Rate (%)", "variable": "Metric"},
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Star rating distribution ──────────────────────────────────────────────────
fig_hist = px.histogram(
    df,
    x="STAR_RATING",
    nbins=5,
    title="Distribution of Star Ratings",
    labels={"STAR_RATING": "Star Rating", "count": "Number of Measures"},
    color_discrete_sequence=["#f5c518"],
)
st.plotly_chart(fig_hist, use_container_width=True)

# ── Table ──────────────────────────────────────────────────────────────────────
st.markdown("### Provider Quality Detail")
st.dataframe(
    df[["PROVIDER_NAME", "STATE", "MEASURE_NAME", "PERFORMANCE_RATE", "NATIONAL_AVERAGE",
        "DELTA_VS_NATIONAL", "STAR_RATING"]].sort_values("DELTA_VS_NATIONAL", ascending=False),
    use_container_width=True,
)
