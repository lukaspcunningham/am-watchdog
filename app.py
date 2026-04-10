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
    st.caption("DISPLAY")
    norm_mode = st.radio("Normalize by", ["Per Unit", "Per Sq Ft"], horizontal=True)
    use_sqft = (norm_mode == "Per Sq Ft")

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

            if use_sqft and "per_sqft" in row and pd.notna(row.get("per_sqft")):
                val_str   = f'${row["per_sqft"]:.3f}/sf billed vs. ${row["eia_bench_sqft"]:.3f}/sf EIA benchmark'
            else:
                val_str   = f'${row["per_unit"]:.0f}/unit billed vs. ${row["eia_benchmark"]:.0f}/unit EIA benchmark'

            st.markdown(
                f'<div class="flag-card" style="border-color:{sc}">'
                f'<div class="flag-prop">{row["Property"]} — {row["Utility_Type"]}</div>'
                f'<div class="flag-meta">{row["PM_Company"]} · {row["Month"]}</div>'
                f'<div style="margin-top:8px">{tag_html}</div>'
                f'<div class="flag-detail">'
                f'{val_str} '
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
    trend_label = "Per Sq Ft" if use_sqft else "Per Unit"
    st.markdown(f'<div class="section-title">Portfolio Trend — {trend_label}</div>', unsafe_allow_html=True)

    util_sel = st.selectbox("Utility", ["Electric", "Gas", "Water/Sewer", "Trash"], label_visibility="collapsed")
    trend = df_analyzed[df_analyzed["Utility_Type"] == util_sel].copy()

    fig = go.Figure()
    palette = ["#4a7ab5","#5aaa7a","#D4A843","#cc7755","#7a7ab5","#55aacc","#aa7755","#aaaaaa"]
    flagged_props = df_flagged["Property"].unique()

    y_col   = "per_sqft" if (use_sqft and "per_sqft" in trend.columns) else "per_unit"
    y_label = "$/sf/month" if use_sqft else "$/unit/month"

    for i, (prop, pdata) in enumerate(trend.groupby("Property")):
        pdata = pdata.sort_values("Month")
        is_flagged = prop in flagged_props
        fig.add_trace(go.Scatter(
            x=pdata["Month"], y=pdata[y_col], name=prop,
            mode="lines+markers",
            line=dict(color=palette[i % len(palette)], width=2.5 if is_flagged else 1.5),
            marker=dict(size=5 if is_flagged else 3),
            opacity=1.0 if is_flagged else 0.55,
        ))

    bench_months = sorted(trend["Month"].unique())
    if use_sqft and "Avg_Unit_Sqft" in trend.columns:
        avg_sf     = trend.groupby("Property")["Avg_Unit_Sqft"].first().mean()
        bench_vals = [get_eia_benchmark(util_sel, int(m.split("-")[1])) / avg_sf for m in bench_months]
    else:
        bench_vals = [get_eia_benchmark(util_sel, int(m.split("-")[1])) for m in bench_months]

    fig.add_trace(go.Scatter(
        x=bench_months, y=bench_vals, name="EIA CO Benchmark",
        mode="lines", line=dict(color="#ffffff", width=1.5, dash="dash"), opacity=0.4,
    ))

    fig.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
        font=dict(color="#aaa", size=12),
        legend=dict(bgcolor="#1a1d27", bordercolor="#2a2d3a", borderwidth=1, font=dict(size=11)),
        xaxis=dict(gridcolor="#1e2030", title=None),
        yaxis=dict(gridcolor="#1e2030", title=y_label),
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

                d_y_col   = "per_sqft" if (use_sqft and "per_sqft" in udata.columns) else "per_unit"
                d_y_label = "$/sf/month" if use_sqft else "$/unit/month"
                point_colors = [severity_color(s) if pd.notna(s) else "#4a7ab5" for s in udata["severity"]]
                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=udata[d_y_col], name="Actual",
                    mode="lines+markers",
                    line=dict(color=line_color, width=2.5),
                    marker=dict(size=7, color=point_colors),
                ))

                avg_sf  = udata["Avg_Unit_Sqft"].iloc[0] if "Avg_Unit_Sqft" in udata.columns else 850
                if use_sqft:
                    bench = [get_eia_benchmark(utility, int(m.split("-")[1])) / avg_sf for m in udata["Month"]]
                    bud_y = udata["budget_per_sqft"] if "budget_per_sqft" in udata.columns else udata["budget_per_unit"] / avg_sf
                else:
                    bench = [get_eia_benchmark(utility, int(m.split("-")[1])) for m in udata["Month"]]
                    bud_y = udata["budget_per_unit"]

                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=bench, name="EIA Benchmark",
                    mode="lines", line=dict(color="#fff", width=1.2, dash="dash"), opacity=0.35,
                ))
                fig2.add_trace(go.Scatter(
                    x=udata["Month"], y=bud_y, name="Underwritten Budget",
                    mode="lines", line=dict(color="#5aaa7a", width=1.2, dash="dot"), opacity=0.5,
                ))

                fig2.update_layout(
                    paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                    font=dict(color="#aaa", size=11),
                    legend=dict(bgcolor="#1a1d27", font=dict(size=10)),
                    xaxis=dict(gridcolor="#1e2030", title=None),
                    yaxis=dict(gridcolor="#1e2030", title=d_y_label),
                    height=220, margin=dict(l=0, r=0, t=6, b=0),
                    hovermode="x unified",
                )
                st.plotly_chart(fig2, use_container_width=True)

            with st_col:
                if use_sqft and "per_sqft" in latest_u:
                    st.metric("Latest", f"${latest_u['per_sqft']:.3f}/sf")
                    st.metric("EIA Benchmark", f"${latest_u['eia_bench_sqft']:.3f}/sf")
                else:
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
                    # Electric: consistently 1.52x — common area lighting billed to master meter
                    # but the PM is passing it through on a flat per-unit allocation that
                    # doesn't reset seasonally. Classic billing structure issue.
                    # Water: looks fine Jan–May, then a slow escalation from June onward
                    # consistent with an irrigation controller leak or running toilet bank.
                    # Gas & Trash: within normal range.
                    if utility == "Electric":
                        mult = 1.52 + np.random.uniform(-0.03, 0.03)
                    elif utility == "Water/Sewer":
                        if mn <= 5:
                            mult = 1.0 + np.random.uniform(-0.04, 0.04)
                        else:
                            # escalating: +8% per month starting June
                            mult = 1.0 + (mn - 5) * 0.08 + np.random.uniform(-0.02, 0.02)
                    elif utility == "Gas":
                        mult = 1.07 + np.random.uniform(-0.04, 0.04)
                    else:  # Trash
                        mult = 1.0 + np.random.uniform(-0.02, 0.02)
                    total = max(1, int(bench * mult * 80 * np.random.uniform(0.99, 1.01)))
                    rows.append({
                        "Property": "Colfax Commons", "Address": "8800 E Colfax Ave - Aurora CO",
                        "PM_Company": "Seller PM Co.", "Asset_Type": "MF", "Units": 80,
                        "Avg_Unit_Sqft": 875,
                        "Month": m.strftime("%Y-%m"), "Utility_Type": utility,
                        "Total_Charge": total,
                        "Underwritten_Budget": int(get_eia_benchmark(utility, mn) * 1.08 * 80),
                    })
            return pd.DataFrame(rows)

        dd_raw = dd_demo()
        st.info(
            "**Demo — Colfax Commons:** 80-unit Aurora CO acquisition. "
            "Electric overbilled ~52% above EIA benchmark year-round (common area billing structure issue). "
            "Water trending sharply above benchmark since June — possible irrigation leak or running toilets."
        )

    dd_analyzed = run_analysis(dd_raw)
    dd_flagged  = get_flagged(dd_analyzed)

    prop_name = dd_raw["Property"].iloc[0]
    n_months  = dd_raw["Month"].nunique()
    n_units_dd = int(dd_raw["Units"].iloc[0])
    n_flags   = dd_flagged["Utility_Type"].nunique() if not dd_flagged.empty else 0
    maint     = bool(dd_flagged["maintenance_signal"].any()) if not dd_flagged.empty else False

    # ── Pre-compute utility summary (needed for KPIs and valuation) ───────────
    # BUG NOTE: dollar_impact_annual is monthly_overcharge×12 per row.
    # Summing across T-12 rows multiplies by months — use mean monthly × 12 instead.
    has_sqft_dd = "Avg_Unit_Sqft" in dd_analyzed.columns
    utility_summary = []
    for utility in ["Electric", "Gas", "Water/Sewer", "Trash"]:
        udata = dd_analyzed[dd_analyzed["Utility_Type"] == utility]
        if udata.empty:
            continue
        avg_pu   = udata["per_unit"].mean()
        avg_b    = udata["eia_benchmark"].mean()
        ratio    = avg_pu / avg_b if avg_b > 0 else 1.0
        n_fl     = udata["severity"].notna().sum()
        # Correct annualization: average monthly overcharge × 12
        avg_mo   = udata["dollar_impact_monthly"].mean()
        exp      = avg_mo * 12
        avg_sf   = udata["Avg_Unit_Sqft"].iloc[0] if has_sqft_dd else None
        avg_psf  = udata["per_sqft"].mean() if (has_sqft_dd and "per_sqft" in udata.columns) else None
        avg_b_sf = (avg_b / avg_sf) if (has_sqft_dd and avg_sf) else None
        utility_summary.append({
            "utility": utility, "avg_per_unit": avg_pu, "benchmark": avg_b,
            "ratio": ratio, "months_flagged": n_fl, "annual_exposure": exp,
            "avg_per_sqft": avg_psf, "benchmark_sqft": avg_b_sf,
        })

    # Correct total exposure (sum of per-utility annualized averages)
    total_exp = sum(u["annual_exposure"] for u in utility_summary)

    st.divider()
    st.markdown(f"### {prop_name}")
    st.caption(f"{n_units_dd} units · {dd_raw['Address'].iloc[0]} · {n_months} months of history")

    ck1, ck2, ck3 = st.columns(3)
    overall = "Elevated — Investigate" if n_flags >= 2 else ("Monitor" if n_flags == 1 else "Within Range")
    ck1.metric("Overall Assessment", overall)
    ck2.metric("Utilities Flagged", f"{n_flags} of 4")
    ck3.metric("Annualized Exposure", f"${total_exp:,.0f}")

    if maint:
        st.warning("Water usage is trending above benchmark for 3+ consecutive months. Recommend a plumbing inspection before close.")

    st.markdown('<div class="section-title">Utility Assessment</div>', unsafe_allow_html=True)

    for u_rec in utility_summary:
        utility  = u_rec["utility"]
        udata    = dd_analyzed[dd_analyzed["Utility_Type"] == utility]
        avg_pu   = u_rec["avg_per_unit"]
        avg_b    = u_rec["benchmark"]
        ratio    = u_rec["ratio"]
        n_fl     = u_rec["months_flagged"]
        exp      = u_rec["annual_exposure"]
        avg_psf  = u_rec.get("avg_per_sqft")
        avg_b_sf = u_rec.get("benchmark_sqft")
        avg_sf   = udata["Avg_Unit_Sqft"].iloc[0] if has_sqft_dd and len(udata) > 0 else None

        flag_icon = "⚠" if ratio > 1.18 else "✓"
        if use_sqft and avg_psf and avg_b_sf:
            exp_label = f"avg ${avg_psf:.3f}/sf vs ${avg_b_sf:.3f} EIA ({ratio:.2f}x)"
        else:
            exp_label = f"avg ${avg_pu:.0f}/unit vs ${avg_b:.0f} EIA ({ratio:.2f}x)"

        with st.expander(
            f"{flag_icon}  {utility}   ·   {exp_label}",
            expanded=(ratio > 1.18)
        ):
            udata_s = udata.sort_values("Month")
            fig3 = go.Figure()
            lc   = "#E07B54" if ratio > 1.40 else ("#D4A843" if ratio > 1.18 else "#4a7ab5")

            dd_y_col   = "per_sqft" if (use_sqft and has_sqft_dd and "per_sqft" in udata_s.columns) else "per_unit"
            dd_y_label = "$/sf/month" if (use_sqft and has_sqft_dd) else "$/unit/month"

            fig3.add_trace(go.Scatter(
                x=udata_s["Month"], y=udata_s[dd_y_col], name="Actual",
                mode="lines+markers", line=dict(color=lc, width=2.5), marker=dict(size=5),
            ))
            if use_sqft and has_sqft_dd and avg_sf:
                bvals = [get_eia_benchmark(utility, int(m.split("-")[1])) / avg_sf for m in udata_s["Month"]]
            else:
                bvals = [get_eia_benchmark(utility, int(m.split("-")[1])) for m in udata_s["Month"]]
            fig3.add_trace(go.Scatter(
                x=udata_s["Month"], y=bvals, name="EIA Benchmark",
                mode="lines", line=dict(color="#fff", width=1.2, dash="dash"), opacity=0.35,
            ))
            fig3.update_layout(
                paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                font=dict(color="#aaa", size=11),
                legend=dict(bgcolor="#1a1d27"),
                xaxis=dict(gridcolor="#1e2030"), yaxis=dict(gridcolor="#1e2030", title=dd_y_label),
                height=200, margin=dict(l=0, r=0, t=6, b=0), hovermode="x unified",
            )
            st.plotly_chart(fig3, use_container_width=True)
            st.caption(f"Months above threshold: {n_fl}/{n_months}  ·  Annualized exposure: ${exp:,.0f}")

    st.markdown('<div class="section-title">Investment Memo Note</div>', unsafe_allow_html=True)
    memo = generate_dd_narrative(prop_name, utility_summary, overall)
    st.markdown(f"_{memo}_")

    # ── Valuation Impact ─────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Valuation Impact — Overcharge Drag & Fix Upside</div>', unsafe_allow_html=True)
    st.caption(
        "Overpaying on utilities inflates OpEx, suppresses NOI, and erodes the value you can justify paying. "
        "But it also creates an opportunity — if you can fix the issue post-close, the NOI improvement "
        "translates directly into equity upside across every valuation method."
    )

    total_overcharge = sum(u["annual_exposure"] for u in utility_summary if u["annual_exposure"] > 0)

    # ── Inputs ────────────────────────────────────────────────────────────────
    inp1, inp2, inp3, inp4 = st.columns(4)
    with inp1:
        purchase_price = st.number_input(
            "OM Ask Price ($)", min_value=500_000, max_value=150_000_000,
            value=int(n_units_dd * 210_000), step=100_000, format="%d",
            help="Seller's asking price from the OM."
        )
    with inp2:
        gross_annual_rents = st.number_input(
            "Gross Annual Rents ($)", min_value=100_000, max_value=50_000_000,
            value=int(n_units_dd * 18_000), step=50_000, format="%d",
            help="T-12 effective gross income from the OM."
        )
    with inp3:
        capex_to_fix = st.number_input(
            "Est. Capex to Fix ($)", min_value=0, max_value=5_000_000,
            value=int(n_units_dd * 500), step=5_000, format="%d",
            help="Cost to remediate: re-billing audit, plumbing repair, controls upgrade, etc."
        )
    with inp4:
        exit_cap = st.number_input(
            "Assumed Exit Cap Rate (%)", min_value=3.0, max_value=10.0,
            value=5.5, step=0.25, format="%.2f",
            help="Cap rate applied at exit/refi to determine stabilized value post-fix."
        ) / 100.0

    # ── Market scenarios ───────────────────────────────────────────────────────
    scenarios = [
        {"label": "Bear",  "cap_rate": 0.070, "grm": 12.0, "color": "#E07B54",
         "note": "7% cap · GRM 12x — rates elevated, buyers price in risk"},
        {"label": "Base",  "cap_rate": 0.055, "grm": 14.5, "color": "#D4A843",
         "note": "5.5% cap · GRM 14.5x — stable Denver MF market"},
        {"label": "Bull",  "cap_rate": 0.045, "grm": 17.0, "color": "#5aaa7a",
         "note": "4.5% cap · GRM 17x — compressed yields, strong appetite"},
    ]

    seller_grm    = (purchase_price / gross_annual_rents) if gross_annual_rents > 0 else 0
    noi_drag_pct  = (total_overcharge / gross_annual_rents * 100) if gross_annual_rents > 0 else 0
    noi_per_unit  = total_overcharge / n_units_dd if n_units_dd > 0 else 0

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    kc1, kc2, kc3, kc4 = st.columns(4)
    kc1.markdown(
        f'<div class="kpi-card" style="border-color:#E07B54">'
        f'<div class="kpi-value" style="color:#E07B54">${total_overcharge:,.0f}</div>'
        f'<div class="kpi-label">Annual NOI Drag (vs. EIA)</div></div>', unsafe_allow_html=True)
    kc2.markdown(
        f'<div class="kpi-card" style="border-color:#D4A843">'
        f'<div class="kpi-value" style="color:#D4A843">${noi_per_unit:,.0f}</div>'
        f'<div class="kpi-label">NOI Drag Per Unit / Year</div></div>', unsafe_allow_html=True)
    kc3.markdown(
        f'<div class="kpi-card" style="border-color:#D4A843">'
        f'<div class="kpi-value" style="color:#D4A843">{noi_drag_pct:.1f}%</div>'
        f'<div class="kpi-label">NOI Drag as % of Gross Rents</div></div>', unsafe_allow_html=True)
    kc4.markdown(
        f'<div class="kpi-card" style="border-color:#4a7ab5">'
        f'<div class="kpi-value" style="color:#4a7ab5">{seller_grm:.1f}x</div>'
        f'<div class="kpi-label">Seller GRM (inflated OpEx)</div></div>', unsafe_allow_html=True)

    st.markdown("")

    # ── Tabs: three valuation methods ─────────────────────────────────────────
    tab_cap, tab_grm, tab_va = st.tabs([
        "📐  Direct Cap (NOI / Cap Rate)",
        "📊  Gross Rent Multiplier",
        "🔧  Value-Add Return (Fix Upside)",
    ])

    # ─ TAB 1: Direct Cap ─────────────────────────────────────────────────────
    with tab_cap:
        st.caption(
            "The most rigorous income approach. Overstated utilities inflate OpEx → suppress NOI → "
            "the value implied by cap rate is lower than the ask price reflects. "
            "Fixing the issue post-close creates equity equal to the NOI lift ÷ exit cap rate."
        )
        dc_labels, drag_vals, upside_vals, colors = [], [], [], []
        for sc in scenarios:
            drag   = total_overcharge / sc["cap_rate"]
            upside = (total_overcharge / exit_cap) - capex_to_fix
            dc_labels.append(sc["label"])
            drag_vals.append(round(drag))
            upside_vals.append(max(0, round(upside)))
            colors.append(sc["color"])

        fig_dc = go.Figure()
        fig_dc.add_trace(go.Bar(
            name="Value Drag (overpaying at ask)",
            x=dc_labels, y=[-v for v in drag_vals],
            marker_color=[c + "bb" for c in colors],
            text=[f"−${v/1e3:.0f}K" for v in drag_vals],
            textposition="outside", textfont=dict(color="#ccc", size=12),
        ))
        fix_upside_val = max(0, total_overcharge / exit_cap - capex_to_fix)
        fig_dc.add_trace(go.Bar(
            name=f"Fix Upside (at {exit_cap*100:.1f}% exit cap, net capex)",
            x=dc_labels, y=[fix_upside_val] * len(dc_labels),
            marker_color="#5aaa7a99",
            text=[f"+${fix_upside_val/1e3:.0f}K" for _ in dc_labels],
            textposition="outside", textfont=dict(color="#5aaa7a", size=12),
        ))
        fig_dc.update_layout(
            barmode="group",
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#aaa", size=12),
            legend=dict(bgcolor="#1a1d27", font=dict(size=11)),
            xaxis=dict(gridcolor="#1e2030", title="Market Scenario"),
            yaxis=dict(gridcolor="#1e2030", title="Value Impact ($)", tickprefix="$", tickformat=",.0f"),
            height=300, margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig_dc, use_container_width=True)

        dc_cols = st.columns(len(scenarios))
        for col, sc in zip(dc_cols, scenarios):
            drag      = total_overcharge / sc["cap_rate"]
            corr_ppu  = (purchase_price - drag) / n_units_dd
            pct_ask   = drag / purchase_price * 100 if purchase_price else 0
            with col:
                st.markdown(
                    f'<div class="kpi-card" style="border-color:{sc["color"]}">'
                    f'<div class="kpi-label" style="color:{sc["color"]}">{sc["label"]} · {sc["cap_rate"]*100:.1f}% cap</div>'
                    f'<div style="margin-top:8px;font-size:0.82rem;color:#ccc;line-height:1.9">'
                    f'<b>Value drag:</b> ${drag:,.0f}<br>'
                    f'<b>Drag per unit:</b> ${drag/n_units_dd:,.0f}<br>'
                    f'<b>% of ask price:</b> {pct_ask:.1f}%<br>'
                    f'<b>Corrected price/unit:</b> ${corr_ppu:,.0f}<br>'
                    f'<b>Fix upside (net capex):</b> ${max(0, fix_upside_val):,.0f}'
                    f'</div></div>', unsafe_allow_html=True)

    # ─ TAB 2: GRM ────────────────────────────────────────────────────────────
    with tab_grm:
        st.caption(
            "GRM ignores operating expenses, so a buyer relying on it alone won't catch the utility issue. "
            "The adjusted GRM — backed into from corrected NOI — shows the true income multiple you're paying."
        )
        grm_fig_labels, grm_ask_vals, grm_corr_vals, grm_mkt_vals = [], [], [], []
        for sc in scenarios:
            grm_ask_vals.append(seller_grm)
            # Corrected implied GRM: what price cap-rate method would produce / gross rents
            drag           = total_overcharge / sc["cap_rate"]
            corr_price     = purchase_price - drag
            corr_grm       = corr_price / gross_annual_rents if gross_annual_rents else 0
            grm_corr_vals.append(round(corr_grm, 2))
            grm_mkt_vals.append(sc["grm"])
            grm_fig_labels.append(sc["label"])

        fig_grm = go.Figure()
        fig_grm.add_trace(go.Bar(
            name="Seller's GRM (ask price)", x=grm_fig_labels, y=grm_ask_vals,
            marker_color="#E07B54aa",
            text=[f"{v:.1f}x" for v in grm_ask_vals],
            textposition="outside", textfont=dict(color="#E07B54", size=12),
        ))
        fig_grm.add_trace(go.Bar(
            name="Corrected GRM (utility-adjusted price)", x=grm_fig_labels, y=grm_corr_vals,
            marker_color="#D4A843aa",
            text=[f"{v:.1f}x" for v in grm_corr_vals],
            textposition="outside", textfont=dict(color="#D4A843", size=12),
        ))
        fig_grm.add_trace(go.Bar(
            name="Market GRM comp", x=grm_fig_labels, y=grm_mkt_vals,
            marker_color="#4a7ab5aa",
            text=[f"{v:.1f}x" for v in grm_mkt_vals],
            textposition="outside", textfont=dict(color="#4a7ab5", size=12),
        ))
        fig_grm.update_layout(
            barmode="group",
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#aaa", size=12),
            legend=dict(bgcolor="#1a1d27", font=dict(size=11)),
            xaxis=dict(gridcolor="#1e2030"),
            yaxis=dict(gridcolor="#1e2030", title="Gross Rent Multiplier (x)"),
            height=300, margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig_grm, use_container_width=True)
        st.caption(
            f"Seller's GRM at ask: **{seller_grm:.1f}x**. "
            f"If you priced this correctly for the elevated utility OpEx, your effective GRM would be lower — "
            f"closer to or below market. That gap is your negotiating anchor."
        )

    # ─ TAB 3: Value-Add Return ────────────────────────────────────────────────
    with tab_va:
        st.caption(
            "You pay full ask price and fix the issue post-close. Each scenario uses its cap rate as the "
            "exit/refi rate — bull exits at 4.5%, bear exits at 7%. This shows how market conditions at "
            "exit amplify or dampen the equity you create from fixing the utility problem."
        )
        # Each scenario uses its OWN cap rate as the exit rate (not the shared exit_cap input)
        va_labels, equity_created, eq_pct, eq_mult_list = [], [], [], []
        for sc in scenarios:
            val_lift   = total_overcharge / sc["cap_rate"]   # value at scenario's exit cap
            net_uplift = val_lift - capex_to_fix
            eq_pct_val = (net_uplift / purchase_price * 100) if purchase_price else 0
            mult_val   = (net_uplift / capex_to_fix) if capex_to_fix > 0 else 0
            va_labels.append(sc["label"])
            equity_created.append(max(0, round(net_uplift)))
            eq_pct.append(round(eq_pct_val, 1))
            eq_mult_list.append(round(mult_val, 1))

        fig_va = go.Figure()
        fig_va.add_trace(go.Bar(
            name="Net equity created (net of capex)",
            x=va_labels, y=equity_created,
            marker_color=[sc["color"] + "cc" for sc in scenarios],
            text=[f"${v/1e3:.0f}K" for v in equity_created],
            textposition="outside", textfont=dict(color="#ccc", size=13),
        ))
        fig_va.add_trace(go.Scatter(
            name="% of ask price",
            x=va_labels, y=eq_pct, mode="lines+markers+text",
            line=dict(color="#5aaa7a", width=2.5, dash="dot"),
            marker=dict(size=10, color="#5aaa7a"),
            text=[f"{p:.1f}%" for p in eq_pct],
            textposition="top center", textfont=dict(color="#5aaa7a", size=12),
            yaxis="y2",
        ))
        fig_va.update_layout(
            paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
            font=dict(color="#aaa", size=12),
            legend=dict(bgcolor="#1a1d27", font=dict(size=11)),
            xaxis=dict(gridcolor="#1e2030", title="Market Scenario at Exit"),
            yaxis=dict(gridcolor="#1e2030", title="Net Equity Created ($)",
                       tickprefix="$", tickformat=",.0f"),
            yaxis2=dict(overlaying="y", side="right", title="% of Ask Price",
                        ticksuffix="%", showgrid=False, color="#5aaa7a"),
            height=300, margin=dict(l=0, r=0, t=20, b=0),
        )
        st.plotly_chart(fig_va, use_container_width=True)

        va_cols = st.columns(len(scenarios))
        for col, sc, eq, pct, mult in zip(va_cols, scenarios, equity_created, eq_pct, eq_mult_list):
            roi_txt       = f"{mult:.1f}x on fix spend" if capex_to_fix > 0 else "Pure NOI play — no capex"
            sc_color      = sc["color"]
            sc_cap_label  = f'{sc["cap_rate"]*100:.1f}% cap'
            sc_exit_val   = f'${total_overcharge/sc["cap_rate"]:,.0f}'
            with col:
                st.markdown(
                    f'<div class="kpi-card" style="border-color:{sc_color}">'
                    f'<div class="kpi-label" style="color:{sc_color}">{sc["label"]} exit · {sc_cap_label}</div>'
                    f'<div style="margin-top:8px;font-size:0.82rem;color:#ccc;line-height:1.9">'
                    f'<b>NOI lift/yr:</b> ${total_overcharge:,.0f}<br>'
                    f'<b>Value at exit:</b> {sc_exit_val}<br>'
                    f'<b>Capex to fix:</b> −${capex_to_fix:,.0f}<br>'
                    f'<b>Net equity:</b> <span style="color:{sc_color}">${eq:,.0f}</span><br>'
                    f'<b>% of ask:</b> {pct:.1f}%<br>'
                    f'<b>{roi_txt}</b>'
                    f'</div></div>', unsafe_allow_html=True)

    # ── OM vs. Corrected comparison ───────────────────────────────────────────
    st.markdown('<div class="section-title">OM Financials vs. Corrected (Base Case)</div>', unsafe_allow_html=True)
    base_cap  = next(sc["cap_rate"] for sc in scenarios if sc["label"] == "Base")
    base_drag = total_overcharge / base_cap

    om_noi       = purchase_price * base_cap               # implied OM NOI at ask price
    corr_noi     = max(0, om_noi - total_overcharge)       # actual NOI once utilities corrected
    corr_value   = corr_noi / base_cap if base_cap else 0  # corrected asset value at base cap
    om_ppu       = purchase_price / n_units_dd
    corr_ppu     = corr_value / n_units_dd

    tbl_data = {
        "Metric": [
            "Implied NOI (at ask price & base cap)",
            "Utility Overcharge (annual)",
            "Corrected NOI",
            "Implied Value (base cap)",
            "Price Per Unit",
        ],
        "OM / Ask": [
            f"${om_noi:,.0f}",
            "—",
            "—",
            f"${purchase_price:,.0f}",
            f"${om_ppu:,.0f}",
        ],
        "Corrected": [
            "—",
            f"−${total_overcharge:,.0f}",
            f"${corr_noi:,.0f}",
            f"${corr_value:,.0f}",
            f"${corr_ppu:,.0f}",
        ],
        "Δ": [
            "—",
            f"−${total_overcharge:,.0f}/yr",
            f"−${total_overcharge:,.0f}/yr",
            f"−${base_drag:,.0f}",
            f"−${om_ppu - corr_ppu:,.0f}/unit",
        ],
    }
    st.dataframe(
        pd.DataFrame(tbl_data),
        use_container_width=True, hide_index=True,
    )

    # ── Negotiating Leverage Callout ──────────────────────────────────────────
    neg_reduction = base_drag
    neg_pct       = (neg_reduction / purchase_price * 100) if purchase_price else 0
    st.markdown(
        f'<div style="background:#1a2a1a;border-left:4px solid #5aaa7a;border-radius:6px;'
        f'padding:16px 20px;margin:16px 0;font-size:0.88rem;color:#ccc;line-height:1.8">'
        f'<b style="color:#5aaa7a">💡 Negotiating Leverage</b><br><br>'
        f'Utility overcharges of <b>${total_overcharge:,.0f}/yr</b> — if accepted as normal operating baseline '
        f'— imply the asset is worth <b>${neg_reduction:,.0f} ({neg_pct:.1f}%) less</b> than the ask price at a '
        f'{base_cap*100:.1f}% cap rate. Use this as your price reduction request in LOI negotiations, '
        f'or structure an escrow holdback contingent on the PM company resolving the billing discrepancy '
        f'and providing corrected invoices within 60 days of close.'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("**Recommended DD actions**")
        if any(u["ratio"] > 1.18 for u in utility_summary):
            st.markdown("- Request master meter invoices & billing worksheets for flagged utilities")
            st.markdown("- Reconcile PM allocation methodology against provider invoices")
            st.markdown("- Re-underwrite at EIA benchmark OpEx and reprice accordingly")
        if maint:
            st.markdown("- Commission licensed plumbing inspection before close")
            st.markdown("- Get repair bid to size capex-to-fix estimate above")
    with r2:
        st.markdown("**Stabilized benchmarks for UW model**")
        for u in utility_summary:
            st.markdown(f"- {u['utility']}: ${u['benchmark']:.0f}/unit/mo (EIA CO)")
