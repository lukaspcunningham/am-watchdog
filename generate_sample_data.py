import pandas as pd
import numpy as np

np.random.seed(42)

properties = [
    {"name": "Lakewood Flats",    "address": "1240 Garrison St - Lakewood CO",    "pm": "Summit Property Group", "units": 52, "asset_type": "MF"},
    {"name": "Aurora Commons",    "address": "3350 Peoria St - Aurora CO",         "pm": "Summit Property Group", "units": 66, "asset_type": "MF"},
    {"name": "Arvada Heights",    "address": "7821 Wadsworth Blvd - Arvada CO",    "pm": "Front Range PM",        "units": 38, "asset_type": "MF"},
    {"name": "Englewood Park",    "address": "555 S Broadway - Englewood CO",      "pm": "Front Range PM",        "units": 30, "asset_type": "MF"},
    {"name": "Morrison Ridge",    "address": "400 Bear Creek Ave - Morrison CO",   "pm": "Front Range PM",        "units": 20, "asset_type": "MF"},
    {"name": "Wheat Ridge Lofts", "address": "4455 Kipling St - Wheat Ridge CO",   "pm": "Apex Management",       "units": 44, "asset_type": "MF"},
    {"name": "Thornton Terrace",  "address": "1100 E 128th Ave - Thornton CO",     "pm": "Apex Management",       "units": 60, "asset_type": "MF"},
    {"name": "Fitzsimons Court",  "address": "1450 Emporia St - Aurora CO",        "pm": "Rocky Mountain PM",     "units": 28, "asset_type": "MF"},
]

# Annual avg per unit per month baselines (Colorado MF, realistic)
baselines = {"Electric": 88, "Gas": 38, "Water/Sewer": 34, "Trash": 15}

# Underwritten budgets per unit per month (set at acquisition)
budgets = {"Electric": 92, "Gas": 40, "Water/Sewer": 36, "Trash": 16}

# Seasonal multipliers (must average to 1.0 over 12 months)
seasonal = {
    "Electric":    [0.92, 0.89, 0.86, 0.83, 0.91, 1.11, 1.30, 1.26, 1.03, 0.88, 0.91, 0.95],
    "Gas":         [2.18, 2.08, 1.53, 0.87, 0.47, 0.27, 0.21, 0.21, 0.31, 0.77, 1.46, 1.94],
    "Water/Sewer": [0.85, 0.85, 0.90, 0.96, 1.06, 1.16, 1.21, 1.21, 1.06, 0.96, 0.89, 0.86],
    "Trash":       [1.0]*12,
}

# Property-level baseline multiplier (older stock = slightly higher)
prop_factors = {
    "Lakewood Flats": 1.05, "Aurora Commons": 1.04, "Arvada Heights": 1.03,
    "Englewood Park": 1.01, "Morrison Ridge": 0.99, "Wheat Ridge Lofts": 1.04,
    "Thornton Terrace": 1.06, "Fitzsimons Court": 1.0,
}

months = pd.date_range("2024-01", "2024-12", freq="MS")
rows = []

for prop in properties:
    for month in months:
        m = month.month
        month_str = month.strftime("%Y-%m")

        for utility in ["Electric", "Gas", "Water/Sewer", "Trash"]:
            base = baselines[utility] * seasonal[utility][m-1] * prop_factors[prop["name"]]
            noise = np.random.uniform(0.96, 1.04)
            per_unit = base * noise

            # ── ANOMALY STORIES ──────────────────────────────────────────────

            # Fitzsimons Court: Rocky Mountain PM overcharging ALL utilities from day 1
            if prop["name"] == "Fitzsimons Court":
                mult = {"Electric": 6.8, "Gas": 6.4, "Water/Sewer": 5.1, "Trash": 3.4}[utility]
                per_unit = baselines[utility] * seasonal[utility][m-1] * mult * np.random.uniform(0.97, 1.03)

            # Arvada Heights: Plumbing leak — water spike starting month 9, grows each month
            elif prop["name"] == "Arvada Heights" and utility == "Water/Sewer" and m >= 9:
                spike = 1.0 + (m - 8) * 0.55  # 1.55x, 2.10x, 2.65x, 3.20x
                per_unit = base * spike * np.random.uniform(0.97, 1.03)

            # Englewood Park: Gas billing drift starting month 7 (gradual creep by PM)
            elif prop["name"] == "Englewood Park" and utility == "Gas" and m >= 7:
                drift = 1.0 + (m - 6) * 0.16  # 1.16, 1.32, 1.48, 1.64, 1.80, 1.96
                per_unit = base * drift * np.random.uniform(0.97, 1.03)

            total = int(round(per_unit * prop["units"]))
            budget = int(round(budgets[utility] * prop["units"]))

            rows.append({
                "Property":            prop["name"],
                "Address":             prop["address"],
                "PM_Company":          prop["pm"],
                "Asset_Type":          prop["asset_type"],
                "Units":               prop["units"],
                "Month":               month_str,
                "Utility_Type":        utility,
                "Total_Charge":        total,
                "Underwritten_Budget": budget,
            })

df = pd.DataFrame(rows)
df.to_csv("/sessions/sleepy-zen-planck/am-watchdog/data/sample_data.csv", index=False)
print(f"✓ Generated {len(df)} rows across {df['Property'].nunique()} properties")
print(f"\nAnomalies preview (per-unit charges):")
for prop in ["Fitzsimons Court","Arvada Heights","Englewood Park"]:
    sub = df[df["Property"]==prop].copy()
    sub["per_unit"] = sub["Total_Charge"] / sub["Units"]
    print(f"\n{prop}:")
    print(sub.groupby(["Utility_Type","Month"])["per_unit"].mean().unstack().round(1).to_string())
