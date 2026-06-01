"""
pages/2_Dashboard_Builder.py – Ask a question; Claude writes the dashboard code.

The page calls POST /api/ask/dashboard, receives Streamlit Python code from
Claude, displays it, and optionally executes it live via exec().
"""

from __future__ import annotations

import traceback

import httpx
import streamlit as st

st.set_page_config(page_title="Dashboard Builder", page_icon="📊", layout="wide")
st.title("📊 Dashboard Builder – Powered by Claude")
st.markdown(
    "Ask a question about CMS data. Claude will write a **Streamlit dashboard** for you. "
    "You can download the code or run it right here."
)

API_BASE = st.session_state.get("api_base", "http://localhost:8000")

# ── Input ────────────────────────────────────────────────────────────────────
question = st.text_area(
    "Your question",
    placeholder="e.g. Show me the top 10 providers by Medicare payments with a bar chart.",
    height=100,
)

col1, col2 = st.columns([1, 4])
generate_btn = col1.button("🚀 Generate Dashboard", type="primary", disabled=not question.strip())

# ── State ────────────────────────────────────────────────────────────────────
if "last_dashboard" not in st.session_state:
    st.session_state["last_dashboard"] = None

# ── Generate ─────────────────────────────────────────────────────────────────
if generate_btn and question.strip():
    with st.spinner("Thinking… Cortex Analyst + Claude are working on it 🤖"):
        try:
            response = httpx.post(
                f"{API_BASE}/api/ask/dashboard",
                json={"question": question},
                timeout=180,
            )
            response.raise_for_status()
            st.session_state["last_dashboard"] = response.json()
        except Exception as exc:
            st.error(f"Error: {exc}\n\n{traceback.format_exc()}")
            st.stop()

# ── Display result ────────────────────────────────────────────────────────────
if st.session_state["last_dashboard"]:
    dash = st.session_state["last_dashboard"]

    st.success("✅ Dashboard generated!")

    with st.expander("🔎 Generated SQL"):
        st.code(dash.get("sql", ""), language="sql")

    with st.expander("💬 Cortex Analyst interpretation"):
        st.write(dash.get("interpretation", ""))

    st.markdown("### 🐍 Generated Python / Streamlit Code")
    code = dash.get("dashboard_code", "")
    st.code(code, language="python")

    # Download button
    st.download_button(
        "⬇️ Download dashboard.py",
        data=code,
        file_name="dashboard.py",
        mime="text/x-python",
    )

    # Live preview (restricted namespace – no builtins access to filesystem/os)
    st.divider()
    st.markdown("### ▶️ Live Preview")
    st.warning(
        "⚠️ Live preview executes the generated code in a restricted namespace. "
        "Review the code above before running.",
        icon="⚠️",
    )
    run_btn = st.button("▶ Run live preview", type="secondary")
    if run_btn:
        # Restrict builtins: allow only safe built-in names; block os/sys/open/etc.
        _SAFE_BUILTINS = {
            name: __builtins__[name]  # type: ignore[index]
            for name in (
                "abs", "all", "any", "bool", "dict", "enumerate", "filter",
                "float", "format", "frozenset", "getattr", "hasattr", "hash",
                "int", "isinstance", "issubclass", "iter", "len", "list",
                "map", "max", "min", "next", "print", "range", "repr",
                "reversed", "round", "set", "slice", "sorted", "str",
                "sum", "tuple", "type", "zip",
            )
            if name in (
                __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)  # type: ignore[arg-type]
            )
        }
        restricted_globals: dict = {
            "__builtins__": _SAFE_BUILTINS,
            "st": st,
        }
        # Inject common data-science imports that the generated code may reference
        try:
            import pandas as _pd
            import plotly.express as _px

            restricted_globals["pd"] = _pd
            restricted_globals["px"] = _px
        except ImportError:
            pass

        try:
            exec(code, restricted_globals)  # noqa: S102
        except Exception as exc:
            st.error(f"Execution error: {exc}\n\n{traceback.format_exc()}")
