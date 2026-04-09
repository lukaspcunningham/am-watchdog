"""
PM Scorecard module.
Score is based on clean streak (time without anomalies), relative to each
property's own expected baseline — not portfolio-wide absolutes.
"""

import pandas as pd
import numpy as np
from datetime import datetime

RISK_THRESHOLDS = {
    "CRITICAL": 0,    # active critical anomaly
    "HIGH":     20,   # score 0–20
    "MODERATE": 50,   # score 20–50
    "LOW":      80,   # score 50–80
    "CLEAN":    100,  # score 80–100
}

SEVERITY_PENALTY = {
    "CRITICAL": 40,
    "HIGH":     25,
    "MEDIUM":   12,
    "LOW":       5,
}

def compute_pm_scorecard(df_analyzed: pd.DataFrame) -> pd.DataFrame:
    """
    Compute PM-level scorecard from analyzed data.
    Score = 100 - cumulative penalty (decays 3pts/month of clean performance).
    """
    records = []

    for pm, pm_group in df_analyzed.groupby("PM_Company"):
        properties = pm_group["Property"].unique().tolist()
        n_properties = len(properties)

        # Score per property, then average to PM level
        prop_scores = []
        all_flags = []
        total_annual_impact = 0

        for prop, prop_group in pm_group.groupby("Property"):
            prop_group = prop_group.sort_values("Month_dt")
            score = 100
            months_since_flag = 0
            last_severity = None

            for _, row in prop_group.iterrows():
                sev = row.get("severity")
                if pd.notna(sev) and sev is not None:
                    penalty = SEVERITY_PENALTY.get(sev, 0)
                    score = max(0, score - penalty)
                    months_since_flag = 0
                    last_severity = sev
                    all_flags.append({
                        "property": prop,
                        "month": row["Month"],
                        "utility": row["Utility_Type"],
                        "severity": sev,
                        "flags": row.get("flags", ""),
                        "dollar_impact_annual": row.get("dollar_impact_annual", 0),
                    })
                else:
                    # Clean month: recover 3 points
                    score = min(100, score + 3)
                    months_since_flag += 1

            prop_scores.append(score)

        # Dollar impact: peak annualized exposure per property/utility combination
        if all_flags:
            flag_df = pd.DataFrame(all_flags)
            total_annual_impact = int(
                flag_df.groupby(["property","utility"])["dollar_impact_annual"].max().sum()
            )

        avg_score = round(np.mean(prop_scores), 1)

        # Risk tier
        risk = "CLEAN"
        for tier, threshold in sorted(RISK_THRESHOLDS.items(), key=lambda x: x[1]):
            if avg_score <= threshold:
                risk = tier
                break

        # Active anomalies (most recent month)
        latest_month = df_analyzed["Month"].max()
        latest = pm_group[pm_group["Month"] == latest_month]
        active_anomalies = latest[latest["severity"].notna()].shape[0]
        active_critical  = latest[latest["severity"] == "CRITICAL"].shape[0]

        # Clean streak (consecutive months with no flags, most recent)
        all_months_sorted = sorted(pm_group["Month"].unique())
        streak = 0
        for m in reversed(all_months_sorted):
            month_data = pm_group[pm_group["Month"] == m]
            if month_data["severity"].notna().any():
                break
            streak += 1

        records.append({
            "PM_Company":          pm,
            "Properties":          n_properties,
            "Property_List":       ", ".join(properties),
            "Score":               avg_score,
            "Risk_Tier":           risk,
            "Active_Anomalies":    active_anomalies,
            "Active_Critical":     active_critical,
            "Clean_Streak_Months": streak,
            "Total_Annual_Impact": int(total_annual_impact),
            "Flag_History":        all_flags,
        })

    return pd.DataFrame(records).sort_values("Score")


def risk_color(risk: str) -> str:
    return {
        "CRITICAL": "#FF4444",
        "HIGH":     "#FF8C00",
        "MODERATE": "#FFD700",
        "LOW":      "#90EE90",
        "CLEAN":    "#00CC66",
    }.get(risk, "#CCCCCC")


def risk_emoji(risk: str) -> str:
    return {
        "CRITICAL": "🔴",
        "HIGH":     "🟠",
        "MODERATE": "🟡",
        "LOW":      "🟢",
        "CLEAN":    "✅",
    }.get(risk, "⚪")
