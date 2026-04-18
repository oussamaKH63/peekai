"""
CSS and HTML component helpers for the PeekAI Streamlit UI.
"""

from __future__ import annotations


GLOBAL_CSS = """
<style>
/* ── Base ─────────────────────────────────────────────────────────── */
[data-testid="stAppViewContainer"] {
    background: #0f1117;
}
[data-testid="stSidebar"] {
    background: #161b27 !important;
    border-right: 1px solid #1e2535;
}
[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 2rem !important;
    max-width: 1200px;
}

/* ── Typography ───────────────────────────────────────────────────── */
h1, h2, h3 { color: #f1f5f9 !important; font-weight: 700 !important; }
p, li, span { color: #cbd5e1; }
code {
    background: #1e2535 !important;
    color: #7dd3fc !important;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 0.8rem;
}

/* ── KPI Cards ────────────────────────────────────────────────────── */
.kpi-card {
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    text-align: center;
}
.kpi-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.4rem;
}
.kpi-value {
    font-size: 1.8rem;
    font-weight: 800;
    color: #f1f5f9;
    line-height: 1;
}
.kpi-sub {
    font-size: 0.72rem;
    color: #475569;
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
.pill-ok      { background: #14532d; color: #4ade80; border: 1px solid #166534; }
.pill-error   { background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
.pill-pending { background: #451a03; color: #fb923c; border: 1px solid #7c2d12; }

/* ── Trace list cards ─────────────────────────────────────────────── */
.trace-card {
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.6rem;
    transition: border-color 0.15s;
}
.trace-card:hover { border-color: #334155; }
.trace-name {
    font-size: 0.95rem;
    font-weight: 600;
    color: #f1f5f9;
}
.trace-meta {
    font-size: 0.75rem;
    color: #475569;
    margin-top: 0.2rem;
}

/* ── Span waterfall ───────────────────────────────────────────────── */
.waterfall-container {
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.5rem;
}
.waterfall-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.5rem;
}
.span-name {
    font-size: 0.88rem;
    font-weight: 600;
    color: #e2e8f0;
}
.span-meta {
    font-size: 0.72rem;
    color: #64748b;
}
.bar-track {
    background: #1e2535;
    border-radius: 4px;
    height: 8px;
    width: 100%;
    overflow: hidden;
    margin-top: 0.4rem;
}
.bar-fill {
    height: 100%;
    border-radius: 4px;
    min-width: 4px;
}
.bar-openai    { background: linear-gradient(90deg, #10b981, #34d399); }
.bar-anthropic { background: linear-gradient(90deg, #f59e0b, #fbbf24); }
.bar-litellm   { background: linear-gradient(90deg, #8b5cf6, #a78bfa); }
.bar-tool      { background: linear-gradient(90deg, #3b82f6, #60a5fa); }
.bar-default   { background: linear-gradient(90deg, #475569, #64748b); }
.bar-error     { background: linear-gradient(90deg, #ef4444, #f87171); }

/* ── Section headers ──────────────────────────────────────────────── */
.section-header {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #475569;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #1e2535;
}

/* ── Sidebar nav ──────────────────────────────────────────────────── */
[data-testid="stRadio"] label {
    font-size: 0.85rem !important;
    padding: 0.3rem 0 !important;
}
[data-testid="stRadio"] > div {
    gap: 0.1rem !important;
}

/* ── Tabs ─────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button {
    font-size: 0.8rem !important;
    color: #64748b !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color: #7dd3fc !important;
    border-bottom-color: #7dd3fc !important;
}

/* ── Dataframe ────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid #1e2535 !important;
    border-radius: 8px !important;
}

/* ── Divider ──────────────────────────────────────────────────────── */
hr { border-color: #1e2535 !important; }

/* ── Buttons ──────────────────────────────────────────────────────── */
[data-testid="stButton"] button {
    background: #1e2535 !important;
    border: 1px solid #334155 !important;
    color: #e2e8f0 !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
}
[data-testid="stButton"] button:hover {
    border-color: #7dd3fc !important;
    color: #7dd3fc !important;
}

/* ── Input ────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input {
    background: #1e2535 !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
}

/* ── Expander ─────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #161b27 !important;
    border: 1px solid #1e2535 !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary {
    color: #94a3b8 !important;
    font-size: 0.82rem !important;
}

/* ── Metric ───────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #161b27;
    border: 1px solid #1e2535;
    border-radius: 10px;
    padding: 0.75rem 1rem;
}
[data-testid="stMetricLabel"] { color: #64748b !important; font-size: 0.72rem !important; }
[data-testid="stMetricValue"] { color: #f1f5f9 !important; }

/* ── Chat messages ────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {
    background: #1e2535 !important;
    border-radius: 8px !important;
    border: 1px solid #334155 !important;
}
</style>
"""


def pill(status: str) -> str:
    cls = f"pill-{status}"
    icons = {"ok": "✓", "error": "✗", "pending": "⏳"}
    icon = icons.get(status, "")
    return f'<span class="pill {cls}">{icon} {status}</span>'


def kpi_card(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
        {sub_html}
    </div>
    """


def section_header(title: str) -> str:
    return f'<div class="section-header">{title}</div>'


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
    cls = bar_class(provider, status)
    return f"""
    <div class="bar-track">
        <div class="bar-fill {cls}" style="width:{max(pct, 2):.1f}%"></div>
    </div>
    """
