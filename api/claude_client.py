"""
claude_client.py – Wrapper around the Anthropic Claude API.

Used to:
  1. Generate dashboard code (Streamlit / Python / Plotly) from query results.
  2. Summarise / narrate CMS data in natural language.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from .config import Settings

logger = logging.getLogger(__name__)

_DASHBOARD_SYSTEM_PROMPT = """\
You are an expert data engineer and Python developer specialising in
healthcare analytics and Streamlit dashboards.

When given a dataset (columns + rows) and a user question, you produce
clean, self-contained Streamlit Python code that:
  • Uses st.title / st.header for clear titles.
  • Uses Plotly Express or Altair for visualisations.
  • Displays the raw data in an st.dataframe expander.
  • Is safe to run with `streamlit run` without modification.
  • Does NOT include any import of secret keys or credentials.

Wrap the complete code in a single ```python ... ``` fenced block.
"""

_SUMMARY_SYSTEM_PROMPT = """\
You are a healthcare data analyst specialising in CMS Medicare data.
Provide concise, insightful summaries of query results. Highlight key
findings, trends, outliers, and actionable recommendations.
Respond in plain English suitable for a healthcare executive audience.
"""


class ClaudeClient:
    """Thin wrapper around anthropic.Anthropic for CMS dashboard use-cases."""

    def __init__(self, settings: Settings) -> None:
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    # ── Generate Streamlit dashboard code ──────────────────────────────
    def generate_dashboard_code(
        self,
        question: str,
        columns: list[str],
        data: list[list[Any]],
        interpretation: str = "",
    ) -> str:
        """
        Ask Claude to generate Streamlit dashboard code for the given
        query result.

        Returns the Python source code as a string (fences stripped).
        """
        rows_preview = data[:50]  # send at most 50 rows to keep token usage reasonable
        data_description = (
            f"Columns: {columns}\n"
            f"Sample data ({len(rows_preview)} of {len(data)} rows):\n"
            + "\n".join(str(row) for row in rows_preview)
        )

        user_message = (
            f"Question: {question}\n\n"
            f"Cortex Analyst interpretation: {interpretation}\n\n"
            f"{data_description}\n\n"
            "Please generate a complete Streamlit dashboard for this data."
        )

        logger.debug("Asking Claude to generate dashboard code for: %s", question)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=_DASHBOARD_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw = message.content[0].text
        return _extract_code_block(raw)

    # ── Summarise query results ─────────────────────────────────────────
    def summarise_results(
        self,
        question: str,
        columns: list[str],
        data: list[list[Any]],
        interpretation: str = "",
    ) -> str:
        """Return a natural-language summary of the query results."""
        rows_preview = data[:100]
        data_description = (
            f"Columns: {columns}\n"
            f"Rows ({len(rows_preview)} shown):\n"
            + "\n".join(str(row) for row in rows_preview)
        )

        user_message = (
            f"Question: {question}\n\n"
            f"Cortex Analyst interpretation: {interpretation}\n\n"
            f"{data_description}\n\n"
            "Please provide a concise executive summary of these findings."
        )

        message = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=_SUMMARY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return message.content[0].text

    # ── Multi-turn conversation ─────────────────────────────────────────
    def chat(
        self,
        messages: list[dict[str, str]],
        system: str = _DASHBOARD_SYSTEM_PROMPT,
        max_tokens: int = 4096,
    ) -> str:
        """Generic multi-turn chat with Claude."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        return response.content[0].text


# ── Utility ─────────────────────────────────────────────────────────────────
def _extract_code_block(text: str) -> str:
    """Extract the first ```python ... ``` fenced block, or return text as-is."""
    import re

    pattern = r"```python\s*(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: strip generic fences
    text = re.sub(r"^```[a-z]*\n?", "", text.strip())
    text = re.sub(r"```$", "", text.strip())
    return text.strip()
