"""
PeekAI Streamlit Dashboard — Phase 3 + 4

Pages:
  📊 Dashboard  — KPIs, cost over time, per-model breakdown
  🔍 Traces     — filterable trace list
  🔎 Trace View — span waterfall with duration bars, I/O tabs, error highlighting
  🔁 Replay     — re-run a trace with model swap, side-by-side comparison
"""

from __future__ import annotations

import json
from html import escape as esc
from pathlib import Path
from typing import Any

import streamlit as st

from peekai.core.models import (
    Span,  # noqa: F401 — used in get_depth annotation
    SpanKind,
    SpanStatus,
    Trace,
)
from peekai.core.storage import Storage
from peekai.ui.styles import (
    GLOBAL_CSS,
    ICON_URI,
    kpi_card,
    pill,
    section_header,
    waterfall_bar,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="peekai",
    page_icon=ICON_URI,
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ── Storage ───────────────────────────────────────────────────────────────────
@st.cache_resource
def get_storage() -> Storage:
    return Storage()


storage = get_storage()


# ── Data loaders ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def load_traces(limit: int = 200) -> list[Trace]:
    return storage.list_traces(limit=limit)


@st.cache_data(ttl=10)
def load_trace(trace_id: str) -> Trace | None:
    return storage.get_trace(trace_id)


@st.cache_data(ttl=10)
def load_stats() -> dict[str, Any]:
    return storage.get_stats()


@st.cache_data(ttl=10)
def load_model_stats() -> list[dict[str, Any]]:
    return storage.get_model_stats()


@st.cache_data(ttl=10)
def load_trace_ids_by_model(model: str) -> set[str]:
    return storage.get_trace_ids_by_model(model)


# ── Formatters ────────────────────────────────────────────────────────────────
def fmt_cost(v: float) -> str:
    return f"${v:.4f}" if v else "$0.0000"


def fmt_cost_long(v: float) -> str:
    return f"${v:.6f}" if v else "—"


def fmt_tokens(n: int) -> str:
    return f"{n:,}" if n else "—"


def fmt_duration(ms: float | None) -> str:
    if ms is None:
        return "—"
    return f"{ms:.0f}ms" if ms < 1000 else f"{ms / 1000:.2f}s"


# ── Agent graph builder ───────────────────────────────────────────────────────
def _build_agent_graph_dot(spans: list[Span]) -> str:
    """Generate a Graphviz DOT string for the agent execution graph."""
    span_map = {s.span_id: s for s in spans}

    _kind_style: dict[str, tuple[str, str]] = {
        "agent": ('fillcolor="#fef3c7" color="#f59e0b"', "agent"),
        "llm":   ('fillcolor="#eff6ff" color="#3b82f6"', "llm"),
        "tool":  ('fillcolor="#f0fdf4" color="#22c55e"', "tool"),
        "chain": ('fillcolor="#f8fafc" color="#64748b"', "chain"),
    }

    lines = [
        "digraph {",
        '  rankdir=TB;',
        '  graph [bgcolor="#ffffff" pad="0.5" nodesep="0.6" ranksep="0.8" fontname="monospace"];',
        '  node [shape=box style="filled,rounded" fontname="monospace" fontsize=10 margin="0.25,0.15" penwidth=1.5];',
        '  edge [color="#94a3b8" arrowsize="0.8" penwidth=1.2];',
    ]

    for span in spans:
        style, kind_label = _kind_style.get(
            span.kind.value, ('fillcolor="#ffffff" color="#e2e8f0"', span.kind.value)
        )
        if span.status == SpanStatus.ERROR:
            style = 'fillcolor="#fee2e2" color="#ef4444"'

        name = span.name[:36].replace("\\", "\\\\").replace('"', '\\"')
        stats: list[str] = []
        if span.duration_ms is not None:
            stats.append(fmt_duration(span.duration_ms))
        if span.total_tokens:
            stats.append(f"{span.total_tokens:,} tok")
        if span.cost_usd:
            stats.append(f"${span.cost_usd:.4f}")

        label = f"{name}\\n[{kind_label}]"
        if stats:
            label += "\\n" + " · ".join(stats)

        lines.append(f'  "{span.span_id}" [label="{label}" {style}];')

    for span in spans:
        if span.parent_span_id and span.parent_span_id in span_map:
            lines.append(f'  "{span.parent_span_id}" -> "{span.span_id}";')

    lines.append("}")
    return "\n".join(lines)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    logo_path = Path(__file__).parent / "peekai-logo.png"
    if logo_path.exists():
        import base64
        logo_b64 = base64.b64encode(logo_path.read_bytes()).decode()
        st.markdown(
            f'<img src="data:image/png;base64,{logo_b64}" '
            f'style="width:160px; height:auto; display:block; margin:0 0 0.25rem 0;" />',
            unsafe_allow_html=True,
        )
    st.markdown(
        "<div style='font-size:0.65rem; color:#94a3b8; letter-spacing:0.05em; margin-bottom:1rem;'>"
        "LOCAL-FIRST AI OBSERVABILITY</div>",
        unsafe_allow_html=True,
    )

    # ── Sidebar navigation buttons ──────────────────────────────────────
    page_options = ["📊 Dashboard", "📋 Traces", "👁️ Trace View", "🔁 Replay"]
    page = st.session_state.get("current_page", "📊 Dashboard")
    
    for page_option in page_options:
        if st.button(
            page_option,
            key=f"nav_{page_option}",
            use_container_width=True,
        ):
            st.session_state["current_page"] = page_option
            st.rerun()
    
    # Style navigation buttons
    st.markdown("""
        <style>
        div[data-testid="stSidebar"] button[kind="secondary"] {
            background-color: transparent !important;
            border: 1px solid transparent !important;
            color: #334155 !important;
            font-weight: 400 !important;
            border-radius: 6px !important;
            padding: 0.5rem 0.75rem !important;
            margin-bottom: 0.25rem !important;
            transition: all 0.15s ease !important;
            text-align: left !important;
            justify-content: flex-start !important;
        }
        div[data-testid="stSidebar"] button[kind="secondary"]:hover {
            border-color: #ff6600 !important;
            background-color: #f1f5f9 !important;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.divider()

    col_r, col_c = st.columns(2)
    if col_r.button("↺ Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    if col_c.button("🗑 Clear", use_container_width=True):
        storage.delete_all()
        st.cache_data.clear()
        st.rerun()

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # Quick stats in sidebar
    stats_sb = load_stats()
    st.markdown(
        f"""
        <div style="font-size:0.7rem; color:#94a3b8; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:0.5rem;">
            Quick stats
        </div>
        <div style="display:flex; flex-direction:column; gap:0.3rem;">
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Runs</span>
                <span style="color:#0f172a; font-weight:600;">{stats_sb['total_runs']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Tokens</span>
                <span style="color:#0f172a; font-weight:600;">{stats_sb['total_tokens']:,}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Cost</span>
                <span style="color:#ff6600; font-weight:600;">{fmt_cost(stats_sb['total_cost_usd'])}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Dashboard
# ══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.markdown("## Dashboard")

    stats = load_stats()
    traces = load_traces()

    error_count = sum(1 for t in traces if t.status == SpanStatus.ERROR)
    ok_count = sum(1 for t in traces if t.status == SpanStatus.OK)
    success_rate = f"{ok_count / max(len(traces), 1) * 100:.0f}%" if traces else "—"

    # ── KPI row ───────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown(kpi_card("Total Runs", str(stats["total_runs"])), unsafe_allow_html=True)
    k2.markdown(kpi_card("Total Tokens", f"{stats['total_tokens']:,}"), unsafe_allow_html=True)
    k3.markdown(kpi_card("Total Cost", fmt_cost(stats["total_cost_usd"]), "USD"), unsafe_allow_html=True)
    k4.markdown(kpi_card("Success Rate", success_rate, f"{error_count} error(s)"), unsafe_allow_html=True)

    if not traces:
        st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
        st.info("No traces yet. Instrument your agent with `peekai.init()` and run it.")
        st.stop()

    # ── Charts ────────────────────────────────────────────────────
    st.markdown(section_header("Cost over time"), unsafe_allow_html=True)
    try:
        import pandas as pd

        chart_data = pd.DataFrame(
            [
                {
                    "Time": t.started_at.strftime("%m-%d %H:%M"),
                    "Cost (USD)": t.total_cost_usd,
                    "Tokens": t.total_tokens,
                }
                for t in reversed(traces)
                if t.ended_at
            ]
        )
        if not chart_data.empty:
            st.area_chart(
                chart_data.set_index("Time")["Cost (USD)"],
                height=180,
                color="#7dd3fc",
            )
    except ImportError:
        st.warning("Install pandas for charts: `uv add pandas`")

    # ── Per-model breakdown ───────────────────────────────────────
    st.markdown(section_header("By model"), unsafe_allow_html=True)

    model_stats = load_model_stats()

    if model_stats:
        try:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "Model": m["model"],
                        "Provider": m["provider"] or "—",
                        "Calls": m["calls"],
                        "Tokens": f"{m['tokens']:,}",
                        "Cost (USD)": fmt_cost_long(m["cost_usd"]),
                    }
                    for m in model_stats
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            for m in model_stats:
                st.text(f"{m['model']}: {m['calls']} calls · {m['tokens']:,} tokens · {fmt_cost_long(m['cost_usd'])}")
    else:
        st.caption("No model data yet.")

    # ── Recent runs ───────────────────────────────────────────────
    st.markdown(section_header("Recent runs"), unsafe_allow_html=True)

    for t in traces[:8]:
        duration = fmt_duration(t.duration_ms)
        started = t.started_at.strftime("%Y-%m-%d %H:%M:%S")
        status_html = pill(t.status.value)

        col_info, col_status, col_tokens, col_cost, col_dur, col_btn = st.columns(
            [4, 1.5, 1.5, 1.5, 1.5, 1]
        )
        col_info.markdown(
            f"<div style='padding-top:4px'>"
            f"<span style='font-weight:600;color:#0f172a'>{esc(t.name)}</span>"
            f"&nbsp;&nbsp;<code>{t.trace_id[:8]}</code>"
            f"<div style='font-size:0.72rem;color:#94a3b8;margin-top:2px'>{started}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        col_status.markdown(
            f"<div style='padding-top:6px'>{status_html}</div>",
            unsafe_allow_html=True,
        )
        col_tokens.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#64748b'>{fmt_tokens(t.total_tokens)}</div>",
            unsafe_allow_html=True,
        )
        col_cost.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#ff6600'>{fmt_cost_long(t.total_cost_usd)}</div>",
            unsafe_allow_html=True,
        )
        col_dur.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{duration}</div>",
            unsafe_allow_html=True,
        )
        if col_btn.button("View", key=f"dash_view_{t.trace_id}"):
            st.session_state["selected_trace_id"] = t.trace_id
            st.session_state["current_page"] = "👁️ Trace View"
            st.rerun()

        st.markdown("<hr style='margin:0.4rem 0;border-color:#e2e8f0'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Traces
# ══════════════════════════════════════════════════════════════════════════════
elif page == "📋 Traces":
    st.markdown("## Traces")

    traces = load_traces()

    if not traces:
        st.info("No traces yet. Instrument your agent with `peekai.init()` and run it.")
        st.stop()

    # ── Filters ───────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    search = f1.text_input("Search", placeholder="Filter by name…", label_visibility="collapsed")
    status_filter = f2.selectbox("Status", ["All statuses", "ok", "error", "pending"], label_visibility="collapsed")
    model_stats = load_model_stats()
    all_models = sorted({m["model"] for m in model_stats if m["model"]})
    model_filter = f3.selectbox("Model", ["All models"] + all_models, label_visibility="collapsed")

    filtered = traces
    if search:
        filtered = [t for t in filtered if search.lower() in t.name.lower()]
    if status_filter != "All statuses":
        filtered = [t for t in filtered if t.status.value == status_filter]
    if model_filter != "All models":
        trace_ids_with_model = load_trace_ids_by_model(str(model_filter))
        filtered = [t for t in filtered if t.trace_id in trace_ids_with_model]

    st.markdown(
        f"<div style='font-size:0.75rem;color:#475569;margin-bottom:0.75rem'>{len(filtered)} trace(s)</div>",
        unsafe_allow_html=True,
    )

    # ── Column headers ────────────────────────────────────────────
    hc1, hc2, hc3, hc4, hc5, hc6, hc7 = st.columns([4, 1.5, 1, 1.5, 1.5, 2, 1])
    for col, label in zip(
        [hc1, hc2, hc3, hc4, hc5, hc6, hc7],
        ["Name", "Status", "Spans", "Tokens", "Cost", "Started", ""],
    ):
        col.markdown(
            f"<div style='font-size:0.68rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#94a3b8'>{label}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='margin:0.3rem 0;border-color:#e2e8f0'>", unsafe_allow_html=True)

    # ── Rows ──────────────────────────────────────────────────────
    for t in filtered:
        c1, c2, c3, c4, c5, c6, c7 = st.columns([4, 1.5, 1, 1.5, 1.5, 2, 1])

        c1.markdown(
            f"<div style='padding-top:4px'>"
            f"<span style='font-weight:600;color:#0f172a;font-size:0.88rem'>{esc(t.name)}</span>"
            f"&nbsp;<code>{t.trace_id[:8]}</code>"
            f"</div>",
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"<div style='padding-top:5px'>{pill(t.status.value)}</div>",
            unsafe_allow_html=True,
        )
        c3.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{t.span_count or '—'}</div>",
            unsafe_allow_html=True,
        )
        c4.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{fmt_tokens(t.total_tokens)}</div>",
            unsafe_allow_html=True,
        )
        c5.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#ff6600'>{fmt_cost_long(t.total_cost_usd)}</div>",
            unsafe_allow_html=True,
        )
        c6.markdown(
            f"<div style='padding-top:6px;font-size:0.75rem;color:#94a3b8'>{t.started_at.strftime('%m-%d %H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )
        if c7.button("→", key=f"list_view_{t.trace_id}"):
            st.session_state["selected_trace_id"] = t.trace_id
            st.session_state["current_page"] = "👁️ Trace View"
            st.rerun()

        st.markdown("<hr style='margin:0.25rem 0;border-color:#e2e8f0'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trace View
# ══════════════════════════════════════════════════════════════════════════════
elif page == "👁️ Trace View":
    st.markdown("## Trace View")

    default_id = st.session_state.get("selected_trace_id", "")
    trace_id_input = st.text_input(
        "Trace ID",
        value=default_id,
        placeholder="Paste a trace ID or first 8 chars…",
        label_visibility="collapsed",
    )

    if not trace_id_input:
        st.markdown(
            "<div style='color:#475569;font-size:0.88rem;margin-top:1rem'>"
            "Enter a trace ID above, or navigate here from the Traces page."
            "</div>",
            unsafe_allow_html=True,
        )
        st.stop()

    # Resolve short IDs
    trace: Trace | None = None
    if len(trace_id_input) < 36:
        all_traces = load_traces(200)
        matches = [t for t in all_traces if t.trace_id.startswith(trace_id_input)]
        if matches:
            trace = load_trace(matches[0].trace_id)
    else:
        trace = load_trace(trace_id_input)

    if trace is None:
        st.error(f"Trace `{trace_id_input}` not found.")
        st.stop()

    # ── Trace header ──────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:1.25rem;">
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.6rem;">
                <span style="font-size:1.1rem;font-weight:800;color:#0f172a">{esc(trace.name)}</span>
                {pill(trace.status.value)}
            </div>
            <div style="display:flex;gap:2rem;flex-wrap:wrap;">
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Trace ID</span><br>
                    <code style="font-size:0.78rem">{trace.trace_id}</code></div>
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Started</span><br>
                    <span style="font-size:0.82rem;color:#64748b">{trace.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</span></div>
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Duration</span><br>
                    <span style="font-size:0.82rem;color:#64748b">{fmt_duration(trace.duration_ms)}</span></div>
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Spans</span><br>
                    <span style="font-size:0.82rem;color:#64748b">{len(trace.spans)}</span></div>
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Tokens</span><br>
                    <span style="font-size:0.82rem;color:#64748b">{fmt_tokens(trace.total_tokens)}</span></div>
                <div><span style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em">Cost</span><br>
                    <span style="font-size:0.82rem;color:#ff6600;font-weight:600">{fmt_cost_long(trace.total_cost_usd)}</span></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not trace.spans:
        st.info("No spans in this trace.")
        st.stop()

    # ── Token breakdown table ─────────────────────────────────────
    with st.expander("Token & cost breakdown", expanded=False):
        try:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "Span": s.name,
                        "Model": s.model or "—",
                        "Provider": s.provider or "—",
                        "In": s.input_tokens,
                        "Out": s.output_tokens,
                        "Total": s.total_tokens,
                        "Cost": fmt_cost_long(s.cost_usd),
                        "Duration": fmt_duration(s.duration_ms),
                        "Status": s.status.value,
                    }
                    for s in trace.spans
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            for s in trace.spans:
                st.text(f"{s.name}: {s.total_tokens} tokens · {fmt_cost_long(s.cost_usd)}")

    # ── Views: Waterfall | Agent Graph ────────────────────────────
    wtab, gtab = st.tabs(["📊 Span Waterfall", "🕸️ Agent Graph"])

    with wtab:
        st.markdown(section_header("Span waterfall"), unsafe_allow_html=True)

        # Build depth map for proper tree indentation
        span_map = {s.span_id: s for s in trace.spans}

        def get_depth(span: Span) -> int:
            depth = 0
            current = span
            while current.parent_span_id and current.parent_span_id in span_map:
                depth += 1
                current = span_map[current.parent_span_id]
            return depth

        # Kind icons and colors
        kind_icons = {
            "llm": "🤖", "tool": "🔧", "agent": "🧠", "chain": "🔗",
        }
        kind_colors = {
            "agent": "#f59e0b",  # amber for agent spans
        }

        # Compute total trace duration for bar scaling
        total_ms = trace.duration_ms or 1.0
        if total_ms == 0:
            total_ms = 1.0

        for span in trace.spans:
            is_error = span.status == SpanStatus.ERROR
            is_agent = span.kind == SpanKind.AGENT
            span_ms = span.duration_ms or 0
            bar_pct = min((span_ms / total_ms) * 100, 100)
            bar_html = waterfall_bar(bar_pct, span.provider or span.kind.value, span.status.value)
            status_html = pill(span.status.value)
            border_color = "#fecaca" if is_error else ("#fed7aa" if is_agent else "#e2e8f0")
            icon = kind_icons.get(span.kind.value, "•")
            name_color = kind_colors.get(span.kind.value, "#0f172a")

            error_html = ""
            if is_error and span.error:
                error_html = (
                    f'<div style="margin-top:0.5rem;padding:0.4rem 0.75rem;background:#fee2e2;'
                    f'border-radius:6px;font-size:0.8rem;color:#dc2626">'
                    f'<strong>{esc(span.error_type or "Error")}:</strong> {esc(span.error)}</div>'
                )

            st.markdown(
                f'<div style="background:#ffffff;border:1px solid {border_color};'
                f'border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.25rem;">'
                f'<div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.35rem;">'
                f'<span style="font-size:0.9rem">{icon}</span>'
                f'<span style="color:{name_color};font-size:0.88rem;font-weight:600">{esc(span.name)}</span>'
                f'<span style="font-size:0.68rem;color:#64748b;background:#f1f5f9;padding:1px 6px;border-radius:4px">{span.kind.value}</span>'
                f'{status_html}'
                f'<span style="font-size:0.72rem;color:#94a3b8;margin-left:auto">'
                f'{fmt_duration(span.duration_ms)}'
                f'&nbsp;·&nbsp;{fmt_tokens(span.total_tokens)} tokens'
                f'&nbsp;·&nbsp;<span style="color:#ff6600">{fmt_cost_long(span.cost_usd)}</span>'
                f'</span></div>'
                f'{bar_html}'
                f'{error_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Agent spans have no I/O — skip the expander entirely
            if is_agent:
                st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)
                continue

            with st.expander(f"Details — {span.name}", expanded=is_error):
                tab_in, tab_out, tab_tools, tab_raw = st.tabs(
                    ["📨 Input", "💬 Output", "🔧 Tool Calls", "📄 Raw"]
                )

                with tab_in:
                    if span.input:
                        for msg in span.input:
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            safe_role = role if role in ("user", "assistant", "system") else "user"
                            with st.chat_message(safe_role):
                                st.write(str(content))
                    else:
                        st.caption("No input recorded.")

                with tab_out:
                    if span.output:
                        st.text_area(
                            "output",
                            value=span.output,
                            height=150,
                            disabled=True,
                            label_visibility="collapsed",
                            key=f"out_{span.span_id}",
                        )
                    else:
                        st.caption("No output recorded.")

                with tab_tools:
                    if span.tool_calls:
                        for tc in span.tool_calls:
                            st.write(f"**⚙ {tc.get('function', '?')}**  `{tc.get('id', '')}`")
                            args = tc.get("arguments", "")
                            if args:
                                try:
                                    parsed = json.loads(args) if isinstance(args, str) else args
                                    st.json(parsed)
                                except Exception:
                                    st.code(str(args), language="text")
                            st.divider()
                    else:
                        st.caption("No tool calls.")

                with tab_raw:
                    if span.raw_response:
                        st.json(span.raw_response)
                    else:
                        st.caption("No raw response recorded.")

            st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

    with gtab:
        st.markdown(section_header("Agent execution graph"), unsafe_allow_html=True)
        dot_src = _build_agent_graph_dot(trace.spans)
        st.graphviz_chart(dot_src, use_container_width=True)
        st.markdown(
            "<div style='display:flex;gap:1.5rem;flex-wrap:wrap;margin-top:0.5rem;"
            "font-size:0.75rem;color:#64748b;padding:0.5rem 0'>"
            "<span style='display:flex;align-items:center;gap:0.3rem'>"
            "<span style='display:inline-block;width:12px;height:12px;border-radius:2px;"
            "background:#fef3c7;border:1.5px solid #f59e0b'></span>agent</span>"
            "<span style='display:flex;align-items:center;gap:0.3rem'>"
            "<span style='display:inline-block;width:12px;height:12px;border-radius:2px;"
            "background:#eff6ff;border:1.5px solid #3b82f6'></span>llm</span>"
            "<span style='display:flex;align-items:center;gap:0.3rem'>"
            "<span style='display:inline-block;width:12px;height:12px;border-radius:2px;"
            "background:#f0fdf4;border:1.5px solid #22c55e'></span>tool</span>"
            "<span style='display:flex;align-items:center;gap:0.3rem'>"
            "<span style='display:inline-block;width:12px;height:12px;border-radius:2px;"
            "background:#f8fafc;border:1.5px solid #64748b'></span>chain</span>"
            "<span style='display:flex;align-items:center;gap:0.3rem'>"
            "<span style='display:inline-block;width:12px;height:12px;border-radius:2px;"
            "background:#fee2e2;border:1.5px solid #ef4444'></span>error</span>"
            "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Replay
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔁 Replay":
    st.markdown("## Replay")
    st.markdown(
        "<div style='color:#64748b;font-size:0.88rem;margin-bottom:1.5rem'>"
        "Re-run any past trace with a different model or modified tool responses. "
        "Results are saved as a new trace and shown side by side."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Config form ───────────────────────────────────────────────
    with st.form("replay_form"):
        r1, r2 = st.columns([3, 2])
        trace_id_input = r1.text_input(
            "Trace ID",
            placeholder="Paste trace ID or first 8 chars…",
            label_visibility="visible",
        )
        model_override = r2.text_input(
            "Model override (optional)",
            placeholder="e.g. gpt-4o or claude-3-5-sonnet-20241022",
            label_visibility="visible",
        )
        a1, a2 = st.columns([2, 3])
        api_key_input = a1.text_input(
            "API Key (optional)",
            placeholder="sk-… (or set OPENAI_API_KEY env var)",
            type="password",
            label_visibility="visible",
        )
        base_url_input = a2.text_input(
            "Base URL (optional)",
            placeholder="https://api.openai.com/v1 or custom endpoint",
            label_visibility="visible",
        )
        submitted = st.form_submit_button("▶ Run Replay", type="primary", use_container_width=True)

    if not submitted or not trace_id_input:
        st.stop()

    # ── Run replay ────────────────────────────────────────────────
    from peekai.replay.engine import ReplayEngine

    engine = ReplayEngine(
        storage=storage,
        model_override=model_override.strip() or None,
        api_key=api_key_input.strip() or None,
        base_url=base_url_input.strip() or None,
    )

    with st.spinner("Replaying trace…"):
        try:
            result = engine.replay(trace_id_input.strip())
        except ValueError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:
            st.error(f"Replay failed: {e}")
            st.stop()

    orig = result.original
    rep = result.replayed

    st.success(f"Replay complete — saved as `{rep.trace_id[:8]}`")
    st.divider()

    # ── Summary metrics ───────────────────────────────────────────
    st.markdown(section_header("Summary"), unsafe_allow_html=True)

    tok_delta = rep.total_tokens - orig.total_tokens
    cost_delta = rep.total_cost_usd - orig.total_cost_usd
    dur_orig = orig.duration_ms or 0
    dur_rep = rep.duration_ms or 0

    def delta_html(val: float, fmt: str = "+.0f") -> str:
        color = "#4ade80" if val <= 0 else "#f87171"
        sign = "+" if val > 0 else ""
        return f'<span style="font-size:0.75rem;color:{color};font-weight:600">{sign}{val:{fmt[1:]}}</span>'

    def summary_card(label: str, value: str, delta: str = "") -> str:
        delta_row = f'<div style="margin-top:0.3rem;min-height:1.2rem">{delta}</div>' if delta else '<div style="min-height:1.2rem;margin-top:0.3rem"></div>'
        return (
            f'<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;'
            f'padding:1rem 1.25rem;height:100px;display:flex;flex-direction:column;justify-content:center">'
            f'<div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:0.35rem">{label}</div>'
            f'<div style="font-size:1.3rem;font-weight:700;color:#0f172a;white-space:nowrap">{value}</div>'
            f'{delta_row}'
            f'</div>'
        )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(summary_card("Orig tokens", fmt_tokens(orig.total_tokens)), unsafe_allow_html=True)
    c2.markdown(summary_card("New tokens", fmt_tokens(rep.total_tokens), delta_html(tok_delta)), unsafe_allow_html=True)
    c3.markdown(summary_card("Orig cost", fmt_cost_long(orig.total_cost_usd)), unsafe_allow_html=True)
    c4.markdown(summary_card("New cost", fmt_cost_long(rep.total_cost_usd), delta_html(cost_delta, "+.6f")), unsafe_allow_html=True)
    c5.markdown(summary_card("Orig duration", fmt_duration(dur_orig)), unsafe_allow_html=True)
    c6.markdown(summary_card("New duration", fmt_duration(dur_rep), delta_html(dur_rep - dur_orig)), unsafe_allow_html=True)

    st.divider()

    # ── Side-by-side span comparison ──────────────────────────────
    st.markdown(section_header("Span comparison"), unsafe_allow_html=True)

    from peekai.core.models import SpanKind

    for orig_span, rep_span in result.span_pairs:
        if orig_span.kind != SpanKind.LLM:
            st.markdown(
                f'<div style="color:#94a3b8;font-size:0.8rem;margin:0.3rem 0">'
                f'⊘ <em>{esc(orig_span.name)}</em> — skipped (not an LLM span)</div>',
                unsafe_allow_html=True,
            )
            continue

        st.markdown(
            f'<div style="font-weight:600;color:#0f172a;font-size:0.9rem;margin:0.75rem 0 0.4rem 0">'
            f'{esc(orig_span.name)}</div>',
            unsafe_allow_html=True,
        )

        col_orig, col_rep = st.columns(2)

        # Original span
        with col_orig:
            st.markdown(
                f'<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:0.75rem 1rem">'
                f'<div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem">Original</div>'
                f'<div style="font-size:0.78rem;color:#001f5b;margin-bottom:0.3rem">{esc(orig_span.model)}</div>'
                f'<div style="font-size:0.75rem;color:#64748b">'
                f'{fmt_tokens(orig_span.total_tokens)} tokens &nbsp;·&nbsp; '
                f'<span style="color:#ff6600">{fmt_cost_long(orig_span.cost_usd)}</span> &nbsp;·&nbsp; '
                f'{fmt_duration(orig_span.duration_ms)}'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            if orig_span.output:
                st.text_area(
                    "orig_out",
                    value=orig_span.output,
                    height=160,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"orig_{orig_span.span_id}",
                )

        # Replayed span
        with col_rep:
            if rep_span:
                is_err = rep_span.status == SpanStatus.ERROR
                border = "#fecaca" if is_err else "#e2e8f0"
                st.markdown(
                    f'<div style="background:#ffffff;border:1px solid {border};border-radius:8px;padding:0.75rem 1rem">'
                    f'<div style="font-size:0.68rem;color:#94a3b8;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.4rem">Replayed</div>'
                    f'<div style="font-size:0.78rem;color:#001f5b;margin-bottom:0.3rem">{esc(rep_span.model)}</div>'
                    f'<div style="font-size:0.75rem;color:#64748b">'
                    f'{fmt_tokens(rep_span.total_tokens)} tokens &nbsp;·&nbsp; '
                    f'<span style="color:#ff6600">{fmt_cost_long(rep_span.cost_usd)}</span> &nbsp;·&nbsp; '
                    f'{fmt_duration(rep_span.duration_ms)}'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )
                if is_err and rep_span.error:
                    st.error(f"{rep_span.error_type}: {rep_span.error}")
                elif rep_span.output:
                    st.text_area(
                        "rep_out",
                        value=rep_span.output,
                        height=160,
                        disabled=True,
                        label_visibility="collapsed",
                        key=f"rep_{rep_span.span_id}",
                    )
            else:
                st.markdown(
                    '<div style="color:#94a3b8;font-size:0.8rem;padding:1rem">No replay data.</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
