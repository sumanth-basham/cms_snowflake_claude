"""
pages/5_Claims_Analysis.py – Pre-built fee-for-service claims dashboard.
"""

from __future__ import annotations

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Claims Analysis", page_icon="💡", layout="wide")
st.title("💡 CMS Fee-for-Service Claims Analysis")
st.markdown("Explore Medicare claim volumes, billed/allowed/paid amounts, and trends.")

API_BASE = st.session_state.get("api_base", "http://localhost:8000")


@st.cache_data(ttl=300, show_spinner="Loading claims data…")
def load_claims_data(api_base: str) -> pd.DataFrame:
    resp = httpx.post(
        f"{api_base}/api/sql",
        json={
            "sql": """
                SELECT
                    c.CLAIM_ID,
                    p.PROVIDER_NAME,
                    p.STATE        AS PROVIDER_STATE,
                    p.SPECIALTY,
                    c.CLAIM_DATE,
                    c.CLAIM_TYPE,
                    c.DIAGNOSIS_CODE,
                    c.PROCEDURE_CODE,
                    c.BILLED_AMOUNT,
                    c.ALLOWED_AMOUNT,
                    c.PAID_AMOUNT,
                    c.PATIENT_AGE_GROUP,
                    c.PATIENT_STATE,
                    YEAR(c.CLAIM_DATE)  AS CLAIM_YEAR,
                    MONTH(c.CLAIM_DATE) AS CLAIM_MONTH
                FROM CMS_DB.ANALYTICS.CLAIMS c
                JOIN CMS_DB.ANALYTICS.PROVIDERS p ON c.PROVIDER_ID = p.PROVIDER_ID
                ORDER BY c.CLAIM_DATE
            """
        },
        timeout=60,
    )
    resp.raise_for_status()
    result = resp.json()
    df = pd.DataFrame(result["data"], columns=result["columns"])
    for col in ("BILLED_AMOUNT", "ALLOWED_AMOUNT", "PAID_AMOUNT"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["CLAIM_DATE"] = pd.to_datetime(df["CLAIM_DATE"], errors="coerce")
    return df


try:
    df = load_claims_data(API_BASE)
except Exception as exc:
    st.error(f"Failed to load data from API ({API_BASE}): {exc}")
    st.info("Make sure the FastAPI backend is running: `uvicorn api.main:app --reload`")
    st.stop()

# ── Filters ───────────────────────────────────────────────────────────────────
with st.sidebar:
    claim_types = sorted(df["CLAIM_TYPE"].dropna().unique().tolist())
    selected_types = st.multiselect("Claim Type", claim_types, default=claim_types)
    if selected_types:
        df = df[df["CLAIM_TYPE"].isin(selected_types)]

    states = sorted(df["PATIENT_STATE"].dropna().unique().tolist())
    selected_states = st.multiselect("Patient State", states, default=states)
    if selected_states:
        df = df[df["PATIENT_STATE"].isin(selected_states)]

# ── KPIs ──────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Claims", f"{len(df):,}")
c2.metric("Total Billed", f"${df['BILLED_AMOUNT'].sum():,.0f}")
c3.metric("Total Allowed", f"${df['ALLOWED_AMOUNT'].sum():,.0f}")
c4.metric("Total Paid", f"${df['PAID_AMOUNT'].sum():,.0f}")

st.divider()

# ── Paid amount over time ─────────────────────────────────────────────────────
monthly = (
    df.groupby(df["CLAIM_DATE"].dt.to_period("M").astype(str))["PAID_AMOUNT"]
    .sum()
    .reset_index()
    .rename(columns={"CLAIM_DATE": "Month", "PAID_AMOUNT": "Paid Amount"})
)
fig_line = px.line(
    monthly,
    x="Month",
    y="Paid Amount",
    title="Medicare Paid Amount Over Time",
    markers=True,
)
st.plotly_chart(fig_line, use_container_width=True)

# ── Billed vs Paid by claim type ─────────────────────────────────────────────
type_agg = df.groupby("CLAIM_TYPE", as_index=False)[["BILLED_AMOUNT", "PAID_AMOUNT"]].sum()
fig_type = px.bar(
    type_agg,
    x="CLAIM_TYPE",
    y=["BILLED_AMOUNT", "PAID_AMOUNT"],
    barmode="group",
    title="Billed vs Paid by Claim Type",
    labels={"value": "Amount ($)", "variable": "Amount Type"},
    color_discrete_map={"BILLED_AMOUNT": "#636EFA", "PAID_AMOUNT": "#00CC96"},
)
st.plotly_chart(fig_type, use_container_width=True)

# ── Age group breakdown ───────────────────────────────────────────────────────
age_agg = df.groupby("PATIENT_AGE_GROUP", as_index=False)["PAID_AMOUNT"].sum().sort_values("PAID_AMOUNT", ascending=False)
fig_age = px.pie(
    age_agg,
    names="PATIENT_AGE_GROUP",
    values="PAID_AMOUNT",
    title="Total Paid Amount by Patient Age Group",
    hole=0.4,
)
col1, col2 = st.columns(2)
col1.plotly_chart(fig_age, use_container_width=True)

# ── Top providers ─────────────────────────────────────────────────────────────
top_prov = (
    df.groupby("PROVIDER_NAME", as_index=False)["PAID_AMOUNT"]
    .sum()
    .sort_values("PAID_AMOUNT", ascending=True)
    .tail(10)
)
fig_prov = px.bar(
    top_prov,
    x="PAID_AMOUNT",
    y="PROVIDER_NAME",
    orientation="h",
    title="Top 10 Providers by Total Paid",
    labels={"PAID_AMOUNT": "Paid Amount ($)", "PROVIDER_NAME": "Provider"},
)
col2.plotly_chart(fig_prov, use_container_width=True)

# ── Raw data ──────────────────────────────────────────────────────────────────
with st.expander("📋 Raw claims data"):
    st.dataframe(df, use_container_width=True)
