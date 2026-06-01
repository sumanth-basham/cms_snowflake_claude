"""
pages/3_Drug_Utilization.py – Pre-built Part-D drug utilization dashboard.
"""

from __future__ import annotations

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Drug Utilization", page_icon="💊", layout="wide")
st.title("💊 Part-D Drug Utilization")
st.markdown("Medicare Part-D prescription drug spending and utilization by provider.")

API_BASE = st.session_state.get("api_base", "http://localhost:8000")


@st.cache_data(ttl=300, show_spinner="Loading drug utilization data…")
def load_drug_data(api_base: str) -> pd.DataFrame:
    resp = httpx.post(
        f"{api_base}/api/sql",
        json={
            "sql": """
                SELECT
                    p.PROVIDER_NAME,
                    p.STATE,
                    p.SPECIALTY,
                    du.DRUG_NAME,
                    du.GENERIC_NAME,
                    du.CLAIM_YEAR,
                    du.CLAIM_COUNT,
                    du.BENEFICIARY_COUNT,
                    du.TOTAL_DRUG_COST,
                    ROUND(DIV0(du.TOTAL_DRUG_COST, du.CLAIM_COUNT), 2) AS COST_PER_CLAIM
                FROM CMS_DB.ANALYTICS.DRUG_UTILIZATION du
                JOIN CMS_DB.ANALYTICS.PROVIDERS p ON du.PROVIDER_ID = p.PROVIDER_ID
                ORDER BY du.TOTAL_DRUG_COST DESC
            """
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    return pd.DataFrame(result["data"], columns=result["columns"])


try:
    df = load_drug_data(API_BASE)
except Exception as exc:
    st.error(f"Failed to load data from API ({API_BASE}): {exc}")
    st.info("Make sure the FastAPI backend is running: `uvicorn api.main:app --reload`")
    st.stop()

# ── Filters ──────────────────────────────────────────────────────────────────
with st.sidebar:
    years = sorted(df["CLAIM_YEAR"].dropna().unique().tolist())
    selected_year = st.selectbox("Year", options=["All"] + years, index=0)
    if selected_year != "All":
        df = df[df["CLAIM_YEAR"] == selected_year]

    drugs = sorted(df["DRUG_NAME"].dropna().unique().tolist())
    selected_drug = st.multiselect("Drug", options=drugs, default=drugs[:5] if len(drugs) > 5 else drugs)
    if selected_drug:
        df = df[df["DRUG_NAME"].isin(selected_drug)]

# ── KPIs ─────────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric("Total Drug Spend", f"${df['TOTAL_DRUG_COST'].sum():,.0f}")
c2.metric("Total Claims", f"{df['CLAIM_COUNT'].sum():,.0f}")
c3.metric("Unique Beneficiaries", f"{df['BENEFICIARY_COUNT'].sum():,.0f}")

st.divider()

# ── Bar chart: spend by drug ──────────────────────────────────────────────────
drug_agg = df.groupby("DRUG_NAME", as_index=False)["TOTAL_DRUG_COST"].sum().sort_values(
    "TOTAL_DRUG_COST", ascending=False
)
fig_bar = px.bar(
    drug_agg,
    x="DRUG_NAME",
    y="TOTAL_DRUG_COST",
    title="Total Drug Cost by Drug",
    labels={"DRUG_NAME": "Drug", "TOTAL_DRUG_COST": "Total Cost ($)"},
    color="TOTAL_DRUG_COST",
    color_continuous_scale="Blues",
)
st.plotly_chart(fig_bar, use_container_width=True)

# ── Scatter: cost per claim vs claim count ────────────────────────────────────
fig_scatter = px.scatter(
    df,
    x="CLAIM_COUNT",
    y="COST_PER_CLAIM",
    color="DRUG_NAME",
    size="TOTAL_DRUG_COST",
    hover_data=["PROVIDER_NAME", "STATE"],
    title="Cost per Claim vs Claim Volume",
    labels={"CLAIM_COUNT": "Claim Count", "COST_PER_CLAIM": "Cost per Claim ($)"},
)
st.plotly_chart(fig_scatter, use_container_width=True)

# ── Raw data ─────────────────────────────────────────────────────────────────
with st.expander("📋 Raw data"):
    st.dataframe(df, use_container_width=True)
