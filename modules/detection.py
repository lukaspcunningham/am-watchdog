"""
Core anomaly detection engine.
Three-tier: EIA benchmark → portfolio average → property historical baseline.
Two modes: absolute (day-1 overcharging) + drift (ratio-based, seasonality-corrected).
Maintenance signal: sustained water spend above benchmark flags potential plumbing issue.
"""

import pandas as pd
import numpy as np
from modules.benchmarks import get_eia_benchmark

# ─── Thresholds ───────────────────────────────────────────────────────────────
SEVERITY_THRESHOLDS = {
    "HIGH":   1.40,   # >40% above benchmark — clear overcharge
    "MEDIUM": 1.18,   # 18–40% above — warrants investigation
}

MIN_OVERCHARGE_PER_UNIT = 5.0    # ignore if absolute $ delta is trivial
DRIFT_MONTHS_REQUIRED   = 3      # months of trend needed to flag drift
DRIFT_SLOPE_THRESHOLD   = 0.04   # 4%/month ratio growth triggers drift
MAINTENANCE_MONTHS      = 3      # consecutive months of elevated water
MAINTENANCE_MULT        = 1.35   # 35% above benchmark triggers maintenance flag


def compute_per_unit(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Month_dt"]      = pd.to_datetime(df["Month"])
    df["month_num"]     = df["Month_dt"].dt.month
    df["per_unit"]      = df["Total_Charge"] / df["Units"]
    df["eia_benchmark"] = df.apply(lambda r: get_eia_benchmark(r["Utility_Type"], r["month_num"]), axis=1)
    df["ratio_to_eia"]  = df["per_unit"] / df["eia_benchmark"].replace(0, np.nan)
    df["budget_per_unit"] = df["Underwritten_Budget"] / df["Units"]
    df["vs_budget_pct"] = ((df["per_unit"] - df["budget_per_unit"]) / df["budget_per_unit"] * 100).round(1)
    return df


def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    df = compute_per_unit(df)
    results = []

    for (prop, utility), group in df.groupby(["Property", "Utility_Type"]):
        group = group.sort_values("Month_dt").reset_index(drop=True)

        for idx, row in group.iterrows():
            flags             = []
            severity          = None
            drift_signal      = False
            maintenance_signal = False

            ratio          = row["ratio_to_eia"]
            overcharge_abs = max(0, row["per_unit"] - row["eia_benchmark"])

            # ── Absolute anomaly ──────────────────────────────────────────────
            if pd.notna(ratio) and overcharge_abs >= MIN_OVERCHARGE_PER_UNIT:
                for sev, thresh in SEVERITY_THRESHOLDS.items():
                    if ratio >= thresh:
                        severity = sev
                        flags.append(f"{ratio:.2f}x EIA benchmark")
                        break

            # ── Drift (ratio trend, seasonality-corrected) ────────────────────
            if idx >= DRIFT_MONTHS_REQUIRED:
                w_ratio = group.loc[max(0, idx - DRIFT_MONTHS_REQUIRED + 1):idx, "ratio_to_eia"].values
                w_pu    = group.loc[max(0, idx - DRIFT_MONTHS_REQUIRED + 1):idx, "per_unit"].values
                if len(w_ratio) >= DRIFT_MONTHS_REQUIRED and w_ratio[0] > 0:
                    growth = (w_ratio[-1] / w_ratio[0]) ** (1 / (len(w_ratio) - 1)) - 1
                    current_over = max(0, w_pu[-1] - row["eia_benchmark"])
                    if growth >= DRIFT_SLOPE_THRESHOLD and current_over >= MIN_OVERCHARGE_PER_UNIT:
                        drift_signal = True
                        flags.append(f"Drifting +{growth*100:.1f}%/mo (last {len(w_ratio)} months)")
                        if severity is None:
                            severity = "MEDIUM"

            # ── Maintenance signal (water) ─────────────────────────────────────
            if utility == "Water/Sewer" and idx >= MAINTENANCE_MONTHS - 1:
                recent = group.loc[max(0, idx - MAINTENANCE_MONTHS + 1):idx, "ratio_to_eia"].values
                if all(pd.notna(recent)) and all(r >= MAINTENANCE_MULT for r in recent):
                    maintenance_signal = True
                    flags.append(f"Sustained {recent[-1]:.2f}x for {MAINTENANCE_MONTHS}+ months — possible plumbing issue")
                    if severity is None or severity == "MEDIUM":
                        severity = "HIGH"

            # ── Dollar impact ─────────────────────────────────────────────────
            dollar_monthly = max(0, row["per_unit"] - row["eia_benchmark"]) * row["Units"]
            dollar_annual  = dollar_monthly * 12

            # ── Escalation ────────────────────────────────────────────────────
            if severity == "HIGH" or maintenance_signal:
                escalation = 2
            elif severity == "MEDIUM":
                escalation = 1
            else:
                escalation = 0

            results.append({
                **row.to_dict(),
                "severity":              severity,
                "flags":                 " · ".join(flags) if flags else None,
                "drift_signal":          drift_signal,
                "maintenance_signal":    maintenance_signal,
                "dollar_impact_monthly": round(dollar_monthly),
                "dollar_impact_annual":  round(dollar_annual),
                "escalation_level":      escalation if severity else 0,
            })

    return pd.DataFrame(results)


def get_flagged(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["severity"].notna()].copy()


def severity_color(sev: str) -> str:
    return {"HIGH": "#E07B54", "MEDIUM": "#D4A843"}.get(sev, "#888")


def escalation_label(level: int) -> str:
    return {1: "Monitor", 2: "Action Recommended"}.get(level, "—")
