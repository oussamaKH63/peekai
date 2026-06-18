"""
CSS and HTML component helpers for the PeekAI Streamlit UI.
"""

from __future__ import annotations

import base64
from pathlib import Path


def _asset_b64(filename: str, mime: str) -> str:
    """Return a base64 data URI for a file in the same directory as this module."""
    path = Path(__file__).parent / filename
    if path.exists():
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode()
        return f"data:{mime};base64,{b64}"
    return ""


ICON_URI = _asset_b64("favicon.svg", "image/svg+xml")

GLOBAL_CSS = """
<style>
/* ── Base ─────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] {
    background: #f8fafc;
}
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] * {
    color: #0f172a !important;
}
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1200px;
}

/* ── Typography ───────────────────────────────────────────────────── */
h1, h2, h3 { color: #0f172a !important; font-weight: 700 !important; }
p, li, span { color: #334155; }
code {
    background: #f1f5f9 !important;
    color: #001f5b !important;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 0.8rem;
}

/* ── KPI Cards ────────────────────────────────────────────────────── */
.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    text-align: center;
}
.kpi-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 0.4rem;
}
.kpi-value {
    font-size: 1.8rem;
    font-weight: 800;
    color: #0f172a;
    line-height: 1;
}
.kpi-sub {
    font-size: 0.72rem;
    color: #94a3b8;
    margin-top: 0.3rem;
}

/* ── Status pills ─────────────────────────────────────────────────── */
.pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.pill-ok      { background: #dcfce7; color: #16a34a; border: 1px solid #bbf7d0; }
.pill-error   { background: #fee2e2; color: #dc2626; border: 1px solid #fecaca; }
.pill-pending { background: #fff7ed; color: #ea580c; border: 1px solid #fed7aa; }

/* ── Trace list cards ─────────────────────────────────────────────── */
.trace-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.6rem;
    transition: border-color 0.15s;
}
.trace-card:hover { border-color: #cbd5e1; }
.trace-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #0f172a;
}
.trace-meta {
    font-size: 0.75rem;
    color: #94a3b8;
    margin-top: 0.2rem;
}

/* ── Span waterfall ───────────────────────────────────────────────── */
.waterfall-container {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.5rem;
}
.bar-track {
    background: #f1f5f9;
    border-radius: 4px;
    height: 8px;
    width: 100%;
    overflow: hidden;
    margin-top: 0.4rem;
}
.bar-fill { height: 100%; border-radius: 4px; min-width: 4px; }
.bar-openai    { background: linear-gradient(90deg, #10b981, #34d399); }
.bar-anthropic { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-litellm   { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
.bar-tool      { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-default   { background: linear-gradient(90deg, #94a3b8, #cbd5e1); }
.bar-error     { background: linear-gradient(90deg, #ef4444, #f87171); }

/* ── Section headers ──────────────────────────────────────────────── */
.section-header {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #94a3b8;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #e2e8f0;
}

/* ── Tabs ─────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button {
    font-size: 0.8rem !important;
    color: #94a3b8 !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #ff6600 !important;
    border-bottom-color: #ff6600 !important;
}

/* ── Dataframe ────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
}

/* ── Divider ──────────────────────────────────────────────────────── */
hr { border-color: #e2e8f0 !important; }

/* ── Buttons ──────────────────────────────────────────────────────── */
[data-testid="stButton"] button {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}
[data-testid="stButton"] button:hover {
    border-color: #ff6600 !important;
    color: #ff6600 !important;
}

/* ── Input ────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    color: #0f172a !important;
    border-radius: 8px !important;
}

/* ── Expander ─────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    color: #64748b !important;
    font-size: 0.82rem !important;
}

/* ── Metric ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 0.75rem 1rem;
}
[data-testid="stMetricLabel"] { color: #94a3b8 !important; font-size: 0.72rem !important; }
[data-testid="stMetricValue"] { color: #0f172a !important; }

/* ── Chat messages ────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: #f8fafc !important;
    border-radius: 8px !important;
    border: 1px solid #e2e8f0 !important;
}
</style>
"""


def pill(status: str) -> str:
    styles = {
        "ok":      "background:#dcfce7;color:#16a34a;border:1px solid #bbf7d0",
        "error":   "background:#fee2e2;color:#dc2626;border:1px solid #fecaca",
        "pending": "background:#fff7ed;color:#ea580c;border:1px solid #fed7aa",
    }
    icons = {"ok": "✓", "error": "✗", "pending": "⏳"}
    style = styles.get(status, "background:#f1f5f9;color:#64748b;border:1px solid #e2e8f0")
    icon = icons.get(status, "")
    return (
        f'<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f'font-size:0.72rem;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;{style}">'
        f'{icon} {status}</span>'
    )


def kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div style="font-size:0.72rem;color:#94a3b8;margin-top:0.3rem">{sub}</div>' if sub else '<div style="margin-top:0.3rem;min-height:1.2rem"></div>'
    return (
        f'<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;'
        f'padding:1.25rem 1.5rem;text-align:center;min-height:90px;display:flex;flex-direction:column;justify-content:center">'
        f'<div style="font-size:0.7rem;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#94a3b8;margin-bottom:0.4rem">{label}</div>'
        f'<div style="font-size:1.8rem;font-weight:800;color:#0f172a;line-height:1">{value}</div>'
        f'{sub_html}'
        f'</div>'
    )


def section_header(title: str) -> str:
    return (
        f'<div style="font-size:0.7rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;'
        f'color:#94a3b8;margin:1.5rem 0 0.75rem 0;padding-bottom:0.4rem;border-bottom:1px solid #e2e8f0">'
        f'{title}</div>'
    )


def bar_class(provider: str, status: str) -> str:
    if status == "error":
        return "bar-error"
    mapping = {
        "openai": "bar-openai",
        "anthropic": "bar-anthropic",
        "litellm": "bar-litellm",
        "tool": "bar-tool",
    }
    return mapping.get(provider.lower(), "bar-default")


def waterfall_bar(pct: float, provider: str, status: str) -> str:
    gradients = {
        "error":     "linear-gradient(90deg,#ef4444,#f87171)",
        "openai":    "linear-gradient(90deg,#10b981,#34d399)",
        "anthropic": "linear-gradient(90deg,#f59e0b,#fbbf24)",
        "litellm":   "linear-gradient(90deg,#8b5cf6,#a78bfa)",
        "tool":      "linear-gradient(90deg,#3b82f6,#60a5fa)",
    }
    if status == "error":
        gradient = gradients["error"]
    else:
        gradient = gradients.get(provider.lower(), "linear-gradient(90deg,#94a3b8,#cbd5e1)")

    width = max(pct, 2)
    return (
        f'<div style="background:#f1f5f9;border-radius:4px;height:8px;width:100%;overflow:hidden;margin-top:0.4rem">'
        f'<div style="height:100%;border-radius:4px;min-width:4px;width:{width:.1f}%;background:{gradient}"></div>'
        f'</div>'
    )
