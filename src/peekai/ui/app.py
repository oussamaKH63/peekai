"""
PeekAI Streamlit Dashboard — Phase 3 (polished)

Pages:
  📊 Dashboard  — KPIs, cost over time, per-model breakdown
  🔍 Traces     — filterable trace list
  🔎 Trace View — span waterfall with duration bars, I/O tabs, error highlighting
"""

from __future__ import annotations

import json

import streamlit as st

from peekai.core.models import SpanStatus, Trace
from peekai.core.storage import Storage
from peekai.ui.styles import (
    GLOBAL_CSS,
    kpi_card,
    pill,
    section_header,
    waterfall_bar,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="PeekAI",
    page_icon="👀",
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
def load_stats() -> dict:
    return storage.get_stats()


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


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        """
        <div style="padding: 0.5rem 0 1rem 0;">
            <span style="font-size:1.6rem;">👀</span>
            <span style="font-size:1.1rem; font-weight:800; color:#f1f5f9; margin-left:0.4rem;">PeekAI</span>
            <div style="font-size:0.7rem; color:#475569; margin-top:0.1rem; letter-spacing:0.05em;">
                LOCAL-FIRST AI OBSERVABILITY
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    page = st.radio(
        "nav",
        ["📊 Dashboard", "🔍 Traces", "🔎 Trace View"],
        label_visibility="collapsed",
    )

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
        <div style="font-size:0.7rem; color:#475569; letter-spacing:0.06em; text-transform:uppercase; margin-bottom:0.5rem;">
            Quick stats
        </div>
        <div style="display:flex; flex-direction:column; gap:0.3rem;">
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Runs</span>
                <span style="color:#e2e8f0; font-weight:600;">{stats_sb['total_runs']}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Tokens</span>
                <span style="color:#e2e8f0; font-weight:600;">{stats_sb['total_tokens']:,}</span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.8rem;">
                <span style="color:#64748b;">Cost</span>
                <span style="color:#a78bfa; font-weight:600;">{fmt_cost(stats_sb['total_cost_usd'])}</span>
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

    model_stats: dict[str, dict] = {}
    for t in traces:
        for span in t.spans:
            if not span.model:
                continue
            m = span.model
            if m not in model_stats:
                model_stats[m] = {"calls": 0, "tokens": 0, "cost": 0.0, "provider": span.provider}
            model_stats[m]["calls"] += 1
            model_stats[m]["tokens"] += span.total_tokens
            model_stats[m]["cost"] += span.cost_usd

    if model_stats:
        try:
            import pandas as pd

            df = pd.DataFrame(
                [
                    {
                        "Model": m,
                        "Provider": v["provider"] or "—",
                        "Calls": v["calls"],
                        "Tokens": f"{v['tokens']:,}",
                        "Cost (USD)": fmt_cost_long(v["cost"]),
                    }
                    for m, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
                ]
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError:
            for m, v in model_stats.items():
                st.text(f"{m}: {v['calls']} calls · {v['tokens']:,} tokens · {fmt_cost_long(v['cost'])}")
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
            f"<span style='font-weight:600;color:#e2e8f0'>{t.name}</span>"
            f"&nbsp;&nbsp;<code>{t.trace_id[:8]}</code>"
            f"<div style='font-size:0.72rem;color:#475569;margin-top:2px'>{started}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        col_status.markdown(
            f"<div style='padding-top:6px'>{status_html}</div>",
            unsafe_allow_html=True,
        )
        col_tokens.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{fmt_tokens(t.total_tokens)}</div>",
            unsafe_allow_html=True,
        )
        col_cost.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#a78bfa'>{fmt_cost_long(t.total_cost_usd)}</div>",
            unsafe_allow_html=True,
        )
        col_dur.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#64748b'>{duration}</div>",
            unsafe_allow_html=True,
        )
        if col_btn.button("View", key=f"dash_view_{t.trace_id}"):
            st.session_state["selected_trace_id"] = t.trace_id
            st.rerun()

        st.markdown("<hr style='margin:0.4rem 0;border-color:#1e2535'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Traces
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Traces":
    st.markdown("## Traces")

    traces = load_traces()

    if not traces:
        st.info("No traces yet. Instrument your agent with `peekai.init()` and run it.")
        st.stop()

    # ── Filters ───────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns([2, 2, 2, 1])
    search = f1.text_input("Search", placeholder="Filter by name…", label_visibility="collapsed")
    status_filter = f2.selectbox("Status", ["All statuses", "ok", "error", "pending"], label_visibility="collapsed")
    all_models = sorted({s.model for t in traces for s in t.spans if s.model})
    model_filter = f3.selectbox("Model", ["All models"] + all_models, label_visibility="collapsed")

    filtered = traces
    if search:
        filtered = [t for t in filtered if search.lower() in t.name.lower()]
    if status_filter != "All statuses":
        filtered = [t for t in filtered if t.status.value == status_filter]
    if model_filter != "All models":
        filtered = [t for t in filtered if any(s.model == model_filter for s in t.spans)]

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
            f"<div style='font-size:0.68rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#475569'>{label}</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<hr style='margin:0.3rem 0;border-color:#1e2535'>", unsafe_allow_html=True)

    # ── Rows ──────────────────────────────────────────────────────
    for t in filtered:
        c1, c2, c3, c4, c5, c6, c7 = st.columns([4, 1.5, 1, 1.5, 1.5, 2, 1])

        c1.markdown(
            f"<div style='padding-top:4px'>"
            f"<span style='font-weight:600;color:#e2e8f0;font-size:0.88rem'>{t.name}</span>"
            f"&nbsp;<code>{t.trace_id[:8]}</code>"
            f"</div>",
            unsafe_allow_html=True,
        )
        c2.markdown(
            f"<div style='padding-top:5px'>{pill(t.status.value)}</div>",
            unsafe_allow_html=True,
        )
        c3.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{len(t.spans) if t.spans else '—'}</div>",
            unsafe_allow_html=True,
        )
        c4.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#94a3b8'>{fmt_tokens(t.total_tokens)}</div>",
            unsafe_allow_html=True,
        )
        c5.markdown(
            f"<div style='padding-top:6px;font-size:0.82rem;color:#a78bfa'>{fmt_cost_long(t.total_cost_usd)}</div>",
            unsafe_allow_html=True,
        )
        c6.markdown(
            f"<div style='padding-top:6px;font-size:0.75rem;color:#475569'>{t.started_at.strftime('%m-%d %H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )
        if c7.button("→", key=f"list_view_{t.trace_id}"):
            st.session_state["selected_trace_id"] = t.trace_id
            st.rerun()

        st.markdown("<hr style='margin:0.25rem 0;border-color:#1e2535'>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Trace View
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🔎 Trace View":
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
        <div style="background:#161b27;border:1px solid #1e2535;border-radius:12px;padding:1.25rem 1.5rem;margin-bottom:1.25rem;">
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.6rem;">
                <span style="font-size:1.1rem;font-weight:800;color:#f1f5f9">{trace.name}</span>
                {pill(trace.status.value)}
            </div>
            <div style="display:flex;gap:2rem;flex-wrap:wrap;">
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Trace ID</span><br>
                    <code style="font-size:0.78rem">{trace.trace_id}</code></div>
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Started</span><br>
                    <span style="font-size:0.82rem;color:#94a3b8">{trace.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")}</span></div>
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Duration</span><br>
                    <span style="font-size:0.82rem;color:#94a3b8">{fmt_duration(trace.duration_ms)}</span></div>
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Spans</span><br>
                    <span style="font-size:0.82rem;color:#94a3b8">{len(trace.spans)}</span></div>
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Tokens</span><br>
                    <span style="font-size:0.82rem;color:#94a3b8">{fmt_tokens(trace.total_tokens)}</span></div>
                <div><span style="font-size:0.68rem;color:#475569;text-transform:uppercase;letter-spacing:0.06em">Cost</span><br>
                    <span style="font-size:0.82rem;color:#a78bfa;font-weight:600">{fmt_cost_long(trace.total_cost_usd)}</span></div>
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

    # ── Span waterfall ────────────────────────────────────────────
    st.markdown(section_header("Span waterfall"), unsafe_allow_html=True)

    # Compute total trace duration for bar scaling
    total_ms = trace.duration_ms or 1.0
    if total_ms == 0:
        total_ms = 1.0

    for span in trace.spans:
        is_error = span.status == SpanStatus.ERROR
        indent_px = "24px" if span.parent_span_id else "0px"
        span_ms = span.duration_ms or 0
        bar_pct = min((span_ms / total_ms) * 100, 100)

        bar_html = waterfall_bar(bar_pct, span.provider or span.kind.value, span.status.value)
        status_html = pill(span.status.value)

        st.markdown(
            f"""
            <div style="margin-left:{indent_px};background:#161b27;border:1px solid {'#3f1515' if is_error else '#1e2535'};
                        border-radius:10px;padding:0.9rem 1.1rem;margin-bottom:0.5rem;">
                <div style="display:flex;align-items:center;gap:0.6rem;margin-bottom:0.35rem;">
                    {'<span style="color:#64748b;font-size:0.8rem">↳</span>' if span.parent_span_id else ''}
                    <span style="font-weight:600;color:#e2e8f0;font-size:0.88rem">{span.name}</span>
                    {status_html}
                    <span style="font-size:0.72rem;color:#475569;margin-left:auto">
                        {fmt_duration(span.duration_ms)}
                        &nbsp;·&nbsp; {fmt_tokens(span.total_tokens)} tokens
                        &nbsp;·&nbsp; <span style="color:#a78bfa">{fmt_cost_long(span.cost_usd)}</span>
                    </span>
                </div>
                {bar_html}
                {'<div style="margin-top:0.5rem;padding:0.5rem 0.75rem;background:#2d0a0a;border-radius:6px;font-size:0.8rem;color:#f87171"><strong>' + (span.error_type or "Error") + ':</strong> ' + (span.error or "") + '</div>' if is_error and span.error else ''}
            </div>
            """,
            unsafe_allow_html=True,
        )

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
                            st.markdown(str(content))
                else:
                    st.caption("No input recorded.")

            with tab_out:
                if span.output:
                    st.markdown(
                        f"<div style='background:#1e2535;border-radius:8px;padding:1rem;font-size:0.88rem;color:#e2e8f0;line-height:1.6'>{span.output}</div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.caption("No output recorded.")

            with tab_tools:
                if span.tool_calls:
                    for tc in span.tool_calls:
                        st.markdown(
                            f"<div style='font-weight:600;color:#7dd3fc;font-size:0.85rem;margin-bottom:0.3rem'>"
                            f"⚙ {tc.get('function', '?')}"
                            f"&nbsp;&nbsp;<code style='font-size:0.72rem'>{tc.get('id', '')}</code>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
                        args = tc.get("arguments", "")
                        if args:
                            try:
                                parsed = json.loads(args) if isinstance(args, str) else args
                                st.json(parsed)
                            except Exception:
                                st.code(str(args), language="text")
                        st.markdown("<hr style='border-color:#1e2535;margin:0.5rem 0'>", unsafe_allow_html=True)
                else:
                    st.caption("No tool calls.")

            with tab_raw:
                if span.raw_response:
                    st.json(span.raw_response)
                else:
                    st.caption("No raw response recorded.")
