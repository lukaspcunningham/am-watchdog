# AM Watchdog — Deployment Guide

## What This Is
A utility anomaly detection tool for multifamily asset management.
Detects overcharging, billing drift, and maintenance signals across a portfolio.
Built with Streamlit, hosted free on Streamlit Cloud.

---

## Deploy to Streamlit Cloud (5 minutes)

### Step 1 — Push to GitHub
1. Create a new GitHub repo (e.g. `am-watchdog`)
2. Upload all files from this folder, maintaining the directory structure:
   ```
   am-watchdog/
   ├── app.py
   ├── requirements.txt
   ├── .streamlit/config.toml
   ├── data/sample_data.csv
   └── modules/
       ├── __init__.py
       ├── benchmarks.py
       ├── detection.py
       ├── narrative.py
       └── scoring.py
   ```

### Step 2 — Deploy on Streamlit Cloud
1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click **New app**
4. Select your repo, branch `main`, main file `app.py`
5. Click **Deploy**

Your app will be live at: `https://[your-username]-am-watchdog-app-[hash].streamlit.app`

### Step 3 — (Optional) Add Anthropic API Key
For AI-generated narratives and email drafts:
1. In Streamlit Cloud → your app → **Settings** → **Secrets**
2. Add: `ANTHROPIC_API_KEY = "your-key-here"`

Or enter it directly in the app sidebar when demoing.

---

## Running Locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Demo Story (for presenting to GPs)
The demo loads automatically with 8 Denver MF properties and 12 months of data.

**Key findings to walk through:**
- **Fitzsimons Court** (Rocky Mountain PM) — all 4 utilities CRITICAL, 6.8x electric benchmark, $452K annual exposure. Level 3 GP alert.
- **Arvada Heights** (Front Range PM) — water usage 3.3x benchmark for 3+ months. Maintenance signal: likely plumbing issue.
- **Englewood Park** (Front Range PM) — gas charges drifting up 16%/month since July. Level 2 PM email drafted automatically.
- **Apex Management & Summit Property Group** — Score 100/100, clean streak all 12 months.

**Acquisition DD mode:** Use the "Try distressed asset scenario" option to show how it screens T-12 utility data before close.

---

## Architecture Notes
- **Benchmarks:** EIA Colorado MF benchmarks hardcoded from 2024 EIA Form 861 data.
  In production, replace with live calls to `api.eia.gov/v2/electricity/retail-sales`.
- **Weather:** NOAA Denver station HDD/CDD data for 2024, hardcoded.
  In production, call `api.weather.gov` or NOAA CDO API.
- **Normalization:** Per-unit for MF. Extend `modules/detection.py` for per-sq-ft industrial.
- **Narratives:** Falls back to templates if no Anthropic API key. Claude Opus 4.6 when key present.
