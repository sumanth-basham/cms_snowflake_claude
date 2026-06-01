"""
pages/1_Ask_CMS.py – Natural-language Q&A page.

Sends user questions to the FastAPI backend which proxies them to
Snowflake Cortex Analyst. Optionally asks Claude to summarise results.
"""

from __future__ import annotations

import json
import traceback

import httpx
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Ask CMS", page_icon="🔍", layout="wide")
st.title("🔍 Ask CMS – Natural Language Query")

API_BASE = st.session_state.get("api_base", "http://localhost:8000")

# ── Conversation state ───────────────────────────────────────────────────────
if "conversation_history" not in st.session_state:
    st.session_state["conversation_history"] = []
if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = []

# ── Sidebar options ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Options")
    include_summary = st.toggle("Claude summary", value=True)
    execute_sql = st.toggle("Execute SQL", value=True)
    if st.button("🗑️ Clear conversation"):
        st.session_state["conversation_history"] = []
        st.session_state["chat_messages"] = []
        st.rerun()

# ── Example questions ────────────────────────────────────────────────────────
st.markdown("#### 💡 Example questions")
example_questions = [
    "Which providers received the highest total Medicare payments?",
    "What is the total drug cost for each drug in 2023?",
    "Show me providers with a star rating above 4.",
    "What are the top diagnosis codes by total paid amount?",
    "Compare inpatient vs outpatient claim counts by state.",
]
cols = st.columns(3)
for i, q in enumerate(example_questions):
    if cols[i % 3].button(q, key=f"ex_{i}", use_container_width=True):
        st.session_state["prefill_question"] = q

# ── Chat input ───────────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill_question", "")
question = st.chat_input("Ask a question about CMS data…", key="chat_input") or prefill

# ── Display conversation history ─────────────────────────────────────────────
for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.write(msg["content"])
        else:
            st.write(msg.get("interpretation", ""))
            if msg.get("sql"):
                with st.expander("🔎 Generated SQL"):
                    st.code(msg["sql"], language="sql")
            if msg.get("data") and msg.get("columns"):
                df = pd.DataFrame(msg["data"], columns=msg["columns"])
                st.dataframe(df, use_container_width=True)
            if msg.get("summary"):
                st.info(msg["summary"])

# ── Handle new question ───────────────────────────────────────────────────────
if question:
    st.session_state["chat_messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Querying Cortex Analyst…"):
            try:
                response = httpx.post(
                    f"{API_BASE}/api/ask",
                    json={
                        "question": question,
                        "conversation_history": st.session_state["conversation_history"],
                        "include_summary": include_summary,
                        "execute_sql": execute_sql,
                    },
                    timeout=120,
                )
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                st.error(f"API error: {exc}\n\n{traceback.format_exc()}")
                st.stop()

        # Display
        st.write(data.get("interpretation", ""))

        if data.get("sql"):
            with st.expander("🔎 Generated SQL"):
                st.code(data["sql"], language="sql")

        if data.get("columns") and data.get("data"):
            df = pd.DataFrame(data["data"], columns=data["columns"])
            st.dataframe(df, use_container_width=True)
            st.caption(f"{len(data['data'])} rows returned.")

        if data.get("summary"):
            st.info(data["summary"])

    # Update conversation history for multi-turn
    analyst_content = []
    if data.get("sql"):
        analyst_content.append({"type": "sql", "statement": data["sql"]})
    if data.get("interpretation"):
        analyst_content.append({"type": "text", "text": data["interpretation"]})

    st.session_state["conversation_history"].extend([
        {"role": "user", "content": [{"type": "text", "text": question}]},
        {"role": "analyst", "content": analyst_content},
    ])
    st.session_state["chat_messages"].append({
        "role": "assistant",
        **{k: data.get(k) for k in ("interpretation", "sql", "columns", "data", "summary")},
    })
