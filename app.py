import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from modules.detection import detect_anomalies, get_flagged, severity_color, escalation_label
from modules.narrative import generate_anomaly_narrative, draft_pm_email, generate_dd_narrative
from modules.benchmarks import get_eia_benchmark, get_rate_events

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AM Watchdog",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background-color: #0f1117; }
    [data-testid="stSidebar"] { background-color: #13151f; }
    .kpi-card {
        background: #1a1d27; border-radius: 8px; padding: 22px 20px;
        border-top: 3px solid; margin-bottom: 4px;
    }
    .kpi-value { font-size: 1.9rem; font-weight: 700; line-height: 1.1; }
    .kpi-label { font-size: 0.75rem; color: #777; text-transform: uppercase;
                 letter-spacing: 1px; margin-top: 4px; }
    .flag-card {
        background: #1a1d27; border-radius: 8px; padding: 18px 20px;
        margin-bottom: 10px; border-left: 4px solid;
    }
    .flag-prop   { font-size: 1.05rem; font-weight: 600; color: #e8e8e8; }
    .flag-meta   { font-size: 0.82rem; color: #888; margin-top: 2px; }
    .flag-detail { font-size: 0.88rem; color: #bbb; margin-top: 10px; line-height: 1.5; }
    .tag {
        display: inline-block; padding: 2px 9px; border-radius: 4px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.4px; margin-right: 6px;
    }
    .section-title {
        font-size: 0.7rem; font-weight: 700; color: #555;
        text-transform: uppercase; letter-spacing: 1.5px;
        margin: 28px 0 12px 0; border-bottom: 1px solid #1e2030; padding-bottom: 6px;
    }
    .email-draft {
        background: #13151f; border: 1px solid #2a2d3a; border-radius: 6px;
        padding: 18px; font-family: 'Courier New', monospace; font-size: 0.83rem;
        color: #c8c8c8; white-space: pre-wrap; line-height: 1.6;
    }
    .rate-banner {
        background: #1a2030; border-left: 3px solid #4a7ab5; border-radius: 4px;
        padding: 9px 14px; font-size: 0.83rem; color: #8aabcc; margin-bottom: 16px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data
def load_data(path):
    return pd.read_csv(path)

@st.cache_data
def run_analysis(df):
    return detect_anomalies(df)

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "data", "sample_data.csv")

# ─── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## AM Watchdog")
    st.caption("Utility Anomaly Detection")
    st.divider()

    page = st.radio("", ["Portfolio Overview", "Property Deep Dive", "Acquisition DD"],
                    label_visibility="collapsed")

    st.divider()
    st.caption("DATA SOURCE")
    use_demo = st.toggle("Demo portfolio", value=True)

    if use_demo:
        df_raw = load_data(SAMPLE_PATH)
        st.caption("8 Denver MF properties · 12 months")
    else:
        up = st.file_uploader("Upload CSV", type=["csv"])
        if up:
            df_raw = pd.read_csv(up)
        else:
            st.info("Upload a CSV or enable demo mode.")
            st.stop()

    st.divider()
    api_key = st.text_input("Anthropic API key", type="password",
                             help="Enables AI-generated summaries and email drafts")
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

df_analyzed  = run_analysis(df_raw)
df_flagged   = get_flagged(df_analyzed)
latest_month = df_analyzed["Month"].max()
latest_flags = df_flagged[df_flagged["Month"] == latest_month].sort_values(
    ["escalation_level", "dollar_impact_annual"], ascending=[False, False]
)


# ══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
if page == "Portfolio Overview":

    st.markdown(f"## Portfolio Overview")
    st.caption(f"Reporting period: {latest_month} · {df_raw['Property'].nunique()} properties · {df_raw['PM_Company'].nunique()} PM companies")

    # Rate event banner
    for ev in get_rate_events(latest_month):
        st.markdown(f'<div class="rate-banner">📊 {ev["note"]}</div>', unsafe_allow_html=True)

    # ── KPI cards ─────────────────────────────────────────────────────────────
    n_flagged   = latest_flags["Property"].nunique()
    n_high      = latest_flags[latest_flags["severity"] == "HIGH"]["Property"].nunique()
    exposure_mo = latest_flags["dollar_impact_monthly"].sum()
    exposure_yr = latest_flags["dollar_impact_annual"].sum()

    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, str(df_raw["Property"].nunique()), "Properties Monitored", "#4a7ab5"),
        (c2, str(n_flagged),                    "Properties Flagged",   "#E07B54" if n_flagged else "#3a7a4a"),
        (c3, f"${exposure_mo:,.0f}",             "Est. Monthly Overcharge", "#D4A843" if exposure_mo else "#3a7a4a"),
        (c4, f"${exposure_yr:,.0f}",             "Annualized Exposure",  "#E07B54" if exposure_yr else "#3a7a4a"),
    ]
    for col, val, label, color in cards:
        with col:
            st.markdown(
                f'<div class="kpi-card" style="border-color:{color}">'
                f'<div class="kpi-value" style="color:{color}">{val}</div>'
                f'<div class="kpi-label">{label}</div></div>',
                unsafe_allow_html=True
            )

    # ── Active flags ──────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Active Flags</div>', unsafe_allow_html=True)

    if latest_flags.empty:
        st.success("No anomalies detected this month across the portfolio.")
    else:
        for _, row in latest_flags.iterrows():
            sc = severity_color(row["severity"])
            sev = row["severity"]
            esc = escalation_label(row["escalation_level"])
            maint = row.get("maintenance_signal", False)
            drift = row.get("drift_signal", False)

            tag_html = f'<span class="tag" style="background:{sc}22;color:{sc}">{sev}</span>'
            if maint:
                tag_html += '<span class="tag" style="background:#2a3545;color:#7aaacc">Maintenance Signal</span>'
            if drift:
                tag_html += '<span class="tag" style="background:#2a2d3a;color:#999">Drift Detected</span>'
            tag_html += f'<span class="tag" style="background:#1e2030;color:#666">{esc}</span>'

            narrative = generate_anomaly_narrative(row.to_dict())

            st.markdown(
                f'<div class="flag-card" style="border-color:{sc}">'
                f'<div class="flag-prop">{row["Property"]} — {row["Utility_Type"]}</div>'
                f'<div class="flag-meta">{row["PM_Company"]} · {row["Month"]}</div>'
                f'<div style="margin-top:8px">{tag_html}</div>'
                f'<div class="flag-detail">'
                f'${row["per_unit"]:.0f}/unit billed vs. ${row["eia_benchmark"]:.0f}/unit EIA benchmark '
                f'({row["ratio_to_eia"]:.2f}x) &nbsp;·&nbsp; '
                f'${row["dollar_impact_monthly"]:,.0f}/mo &nbsp;·&nbsp; '
                f'${row["dollar_impact_annual"]:,.0f} annualized<br><br>'
                f'{narrative}'
                f'</div></div>',
                unsafe_allow_html=True
            )

            if row["escalation_level"] == 2:
                with st.expander("📧 Generate draft PM email"):
                    prop_flags = latest_flags[latest_flags["Property"] == row["Property"]].to_dict("records")
                    email = draft_pm_email(row["Property"], row["PM_Company"], prop_flags)
                    st.markdown(f'<div class="email-draft">{email}</div>', unsafe_allow_html=True)
                    st.caption("Review and edit before sending.")

    # ── Portfolio trend ───────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Portfolio Trend — Per Unit</div>', unsafe_allow_html=True)

    util_sel = st.selectbox("Utility", ["Electric", "Gas", "Water/Sewer", "Trash"], label_visibility="collapsed")
    trend = df_analyzed[df_analyzed["Utility_Type"] == util_sel].copy()

    fig = go.Figure()
    palette = ["#4a7ab5","#5aaa7a","#D4A843","#cc7755","#7a7ab5","#55aacc","#aa7755","#aaaaaa"]
    flagged_props = df_flagged["Property"].unique()

    for i, (prop, pdata) in enumerate(trend.groupby("Property")):
        pdata = pdata.sort_values("Month")
        is_flagged = prop in flagged_props
        fig.add_trace(go.Scatter(
            x=pdata["Month"], y=pdata["per_unit"], name=prop,
            mode="lines+markers",
            line=dict(color=palette[i % len(palette)], width=2.5 if is_flagged else 1.5,
                      dash="solid"),
            marker=dict(size=5 if is_flagged else 3),
            opacity=1.0 if is_flagged else 0.55,
        ))

    bench_months = sorted(trend["Month"].unique())
    bench_vals   = [get_eia_benchmark(util_sel, int(m.split("-")[1])) for m in bench_months]
    fig.add_trace(go.Scatter(
        x=bench_months, y=bench_vals, name="EIA CO Benchmark",
        mode="lines", line=dict(color="#ffffff", width=1.5, dash="dash"), opacity=0.4,
    ))

    fig.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
        font=dict(color="#aaa", size=12),
        legend=dict(bgcolor="#1a1d27", bordercolor="#2a2d3a", borderwidth=1, font=dict(size=11)),
        xaxis=dict(gridcolor="#1e2030", title=None),
        yaxis=dict(gridcolor="#1e2030", title="$/unit/month"),
        height=340, margin=dict(l=0, r=0, t=10, b=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PROPERTY DEEP DIVE
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Property Deep Dive":

    st.markdown("## Property Deep Dive")

    props = sorted(df_analyzed["Property"].unique())
    sel   = st.selectbox("Property", props, label_visibility="collapsed")

    pdata = df_analyzed[df_analyzed["Property"] == sel].copy()
    info  = df_raw[df_raw["Property"] == sel].iloc[0]
    pm    = info["PM_Company"]
    units = int(info["Units"])
    addr  = info["Address"]

    col1, col2, col3 = st.columns(3)
    col1.metric("PM Company", pm)
    col2.metric("Units", units)
    col3.metric("Asset Type", info.get("Asset_Type", "MF"))
    st.caption(f"📍 {addr}")
    st.divider()

    for utility in ["Electric", "Gas", "Water/Sewer", "Trash"]:
        udata = pdata[pdata["Utility_Type"] == utility].sort_values("Month")
        if udata.empty:
            continue

        latest_u    = udata.iloc[-1]
        has_flag    = pd.notna(latest_u["severity"])
        sev         = latest_u["severity"] if has_flag else None
        line_color  = severity_color(sev) if has_flag else "#4a7ab5"
        flag_icon   = "⚠" if has_flag else "✓"

        with st.expander(
            f"{flag_icon}  {utility}   ·   ${latest_u['per_unit']:.0f}/unit   ·   "
            f"EIA: ${latest_u['eia_benchmark']:.0f}/unit"
            + (f"   ·   {sev}" if has_flag else "   ·   Within range"),
            expanded=has_flag
        ):
            ch_col, st_col = st.columns([3, 1])

            with ch_col:
                fig2 = go.Figure()

                # Actual line — color points by severity
                point_colors = [severity_color(s) if pd.notna(s) else "#4a7ab5" for s in udata["severity"]]
                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=udata["per_unit"], name="Actual",
                    mode="lines+markers",
                    line=dict(color=line_color, width=2.5),
                    marker=dict(size=7, color=point_colors),
                ))

                # EIA benchmark
                bench = [get_eia_benchmark(utility, int(m.split("-")[1])) for m in udata["Month"]]
                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=bench, name="EIA Benchmark",
                    mode="lines", line=dict(color="#fff", width=1.2, dash="dash"), opacity=0.35,
                ))

                # Budget line
                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=udata["budget_per_unit"], name="Underwritten Budget",
                    mode="lines", line=dict(color="#5aaa7a", width=1.2, dash="dot"), opacity=0.5,
                ))

                fig2.update_layout(
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#aaa", size=11),
                    legend=dict(bgcolor="#1a1d27", font=dict(size=10)),
                    xaxis=dict(gridcolor="#1e2030", title=None),
                    yaxis=dict(gridcolor="#1e2030", title="$/unit/month"),
                    height=220, margin=dict(l=0, r=0, t=6, b=0),
                    hovermode="x unified",
                )
                st.plotly_chart(fig2, use_container_width=True)

            with st_col:
                st.metric("Latest", f"${latest_u['per_unit']:.0f}/unit")
                st.metric("EIA Benchmark", f"${latest_u['eia_benchmark']:.0f}/unit")
                ratio = latest_u["ratio_to_eia"]
                delta_str = f"{(ratio-1)*100:+.0f}% vs EIA"
                st.metric("Ratio", f"{ratio:.2f}x",
                          delta=delta_str,
                          delta_color="inverse" if ratio > 1.18 else "normal")
                if has_flag:
                    st.metric("Annual Exposure", f"${latest_u['dollar_impact_annual']:,.0f}")

            if has_flag:
                narrative = generate_anomaly_narrative(latest_u.to_dict())
                st.info(narrative)

                if latest_u["escalation_level"] == 2:
                    with st.expander("📧 Generate draft PM email"):
                        prop_flags = df_flagged[
                            (df_flagged["Property"] == sel) &
                            (df_flagged["Month"] == latest_month)
                        ].to_dict("records")
                        email = draft_pm_email(sel, pm, prop_flags)
                        st.markdown(f'<div class="email-draft">{email}</div>', unsafe_allow_html=True)
                        st.caption("Review and edit before sending.")


# ══════════════════════════════════════════════════════════════════════════════
# ACQUISITION DD
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Acquisition DD":

    st.markdown("## Acquisition Due Diligence — Utility Screen")
    st.caption("Upload T-12 utility data from an offering memorandum to screen for anomalies before close.")

    mode = st.radio("", ["Try demo scenario", "Upload OM data"], horizontal=True, label_visibility="collapsed")

    if mode == "Upload OM data":
        tab_up, tab_fmt = st.tabs(["Upload", "CSV Format"])
        with tab_fmt:
            st.markdown("Your CSV needs these columns:")
            eg = pd.DataFrame({
                "Property":["Target Asset"], "Address":["123 Main St - Denver CO"],
                "PM_Company":["Unknown"], "Asset_Type":["MF"], "Units":[80],
                "Month":["2023-01"], "Utility_Type":["Electric"],
                "Total_Charge":[8200], "Underwritten_Budget":[7360],
            })
            st.dataframe(eg, use_container_width=True, hide_index=True)
        with tab_up:
            up2 = st.file_uploader("T-12 utility CSV", type=["csv"], key="dd")
            if not up2:
                st.stop()
            dd_raw = pd.read_csv(up2)
    else:
        @st.cache_data
        def dd_demo():
            months = pd.date_range("2023-01", "2023-12", freq="MS")
            rows = []
            np.random.seed(7)
            for m in months:
                mn = m.month
                for utility in ["Electric", "Gas", "Water/Sewer", "Trash"]:
                    bench = get_eia_benchmark(utility, mn)
                    # Elevated electric throughout; water worsening in second half
                    mult = {"Electric": 1.35, "Gas": 1.05, "Water/Sewer": 1.0, "Trash": 1.0}[utility]
                    if utility == "Water/Sewer" and mn >= 7:
                        mult = 1.0 + (mn - 6) * 0.09
                    total = int(bench * mult * 75 * np.random.uniform(0.98, 1.02))
                    rows.append({
                        "Property": "Colfax Commons", "Address": "8800 E Colfax Ave - Aurora CO",
                        "PM_Company": "Seller PM", "Asset_Type": "MF", "Units": 75,
                        "Month": m.strftime("%Y-%m"), "Utility_Type": utility,
                        "Total_Charge": total,
                        "Underwritten_Budget": int(get_eia_benchmark(utility, mn) * 1.08 * 75),
                    })
            return pd.DataFrame(rows)

        dd_raw = dd_demo()
        st.info("Demo: Colfax Commons — 75-unit Aurora CO acquisition target with T-12 utility history.")

    dd_analyzed = run_analysis(dd_raw)
    dd_flagged  = get_flagged(dd_analyzed)

    prop_name = dd_raw["Property"].iloc[0]
    n_months  = dd_raw["Month"].nunique()
    total_exp = dd_flagged["dollar_impact_annual"].sum()
    n_flags   = dd_flagged["Utility_Type"].nunique() if not dd_flagged.empty else 0
    maint     = bool(dd_flagged["maintenance_signal"].any()) if not dd_flagged.empty else False

    st.divider()
    st.markdown(f"### {prop_name}")
    st.caption(f"{dd_raw['Units'].iloc[0]} units · {dd_raw['Address'].iloc[0]} · {n_months} months of history")

    ck1, ck2, ck3 = st.columns(3)
    overall = "Elevated — Investigate" if n_flags >= 2 else ("Monitor" if n_flags == 1 else "Within Range")
    ck1.metric("Overall Assessment", overall)
    ck2.metric("Utilities Flagged", f"{n_flags} of 4")
    ck3.metric("Annualized Exposure", f"${total_exp:,.0f}")

    if maint:
        st.warning("Water usage is trending above benchmark for 3+ consecutive months. Recommend a plumbing inspection before close.")

    st.markdown('<div class="section-title">Utility Assessment</div>', unsafe_allow_html=True)

    utility_summary = []
    for utility in ["Electric", "Gas", "Water/Sewer", "Trash"]:
        udata = dd_analyzed[dd_analyzed["Utility_Type"] == utility]
        if udata.empty:
            continue
        avg_pu   = udata["per_unit"].mean()
        avg_b    = udata["eia_benchmark"].mean()
        ratio    = avg_pu / avg_b if avg_b > 0 else 1.0
        n_fl     = udata["severity"].notna().sum()
        exp      = udata["dollar_impact_annual"].sum()
        utility_summary.append({"utility": utility, "avg_per_unit": avg_pu,
                                 "benchmark": avg_b, "ratio": ratio,
                                 "months_flagged": n_fl, "annual_exposure": exp})

        flag_icon = "⚠" if ratio > 1.18 else "✓"
        with st.expander(
            f"{flag_icon}  {utility}   ·   avg ${avg_pu:.0f}/unit vs ${avg_b:.0f} EIA ({ratio:.2f}x)",
            expanded=(ratio > 1.18)
        ):
            udata_s = udata.sort_values("Month")
            fig3 = go.Figure()
            lc   = "#E07B54" if ratio > 1.40 else ("#D4A843" if ratio > 1.18 else "#4a7ab5")
            fig3.add_trace(go.Scatter(
                x=udata_s["Month"], y=udata_s["per_unit"], name="Actual",
                mode="lines+markers", line=dict(color=lc, width=2.5), marker=dict(size=5),
            ))
            bvals = [get_eia_benchmark(utility, int(m.split("-")[1])) for m in udata_s["Month"]]
            fig3.add_trace(go.Scatter(
                x=udata_s["Month"], y=bvals, name="EIA Benchmark",
                mode="lines", line=dict(color="#fff", width=1.2, dash="dash"), opacity=0.35,
            ))
            fig3.update_layout(
                paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                font=dict(color="#aaa", size=11),
                legend=dict(bgcolor="#1a1d27"),
                xaxis=dict(gridcolor="#1e2030"), yaxis=dict(gridcolor="#1e2030", title="$/unit/month"),
                height=200, margin=dict(l=0, r=0, t=6, b=0), hovermode="x unified",
            )
            st.plotly_chart(fig3, use_container_width=True)
            st.caption(f"Months above threshold: {n_fl}/{n_months}  ·  Annualized exposure: ${exp:,.0f}")

    st.markdown('<div class="section-title">Investment Memo Note</div>', unsafe_allow_html=True)
    memo = generate_dd_narrative(prop_name, utility_summary, overall)
    st.markdown(f"_{memo}_")

    st.markdown("")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Recommended DD actions**")
        if any(u["ratio"] > 1.18 for u in utility_summary):
            st.markdown("- Request master meter invoices for flagged utilities")
            st.markdown("- Reconcile PM billing statements vs. provider invoices")
        if maint:
            st.markdown("- Commission plumbing inspection")
    with r2:
        st.markdown("**Stabilized benchmarks for UW model**")
        for u in utility_summary:
            st.markdown(f"- {u['utility']}: ${u['benchmark']:.0f}/unit/mo (EIA CO)")
