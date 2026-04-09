"""
Claude API narrative generation and draft email composition.
Falls back to templated output if ANTHROPIC_API_KEY not set.
"""

import os
import re

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


def _call_claude(prompt: str) -> str:
    if not HAS_ANTHROPIC:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def generate_anomaly_narrative(row: dict) -> str:
    """Generate a 2-3 sentence plain-English summary of an anomaly."""
    prompt = f"""You are an asset manager at a real estate private equity firm reviewing utility anomalies.
Write 2-3 concise, professional sentences summarizing this anomaly for the AM dashboard.
Be specific about the numbers and what action may be warranted. No bullet points.

Property: {row.get('Property')}
PM Company: {row.get('PM_Company')}
Utility: {row.get('Utility_Type')}
Month: {row.get('Month')}
Per-unit charge: ${row.get('per_unit', 0):.0f}
EIA benchmark: ${row.get('eia_benchmark', 0):.0f}
Ratio to benchmark: {row.get('ratio_to_eia', 0):.1f}x
Severity: {row.get('severity')}
Flags: {row.get('flags')}
Annualized dollar impact: ${row.get('dollar_impact_annual', 0):,.0f}
Maintenance signal: {row.get('maintenance_signal', False)}
Weather context: {row.get('weather_note', '')}"""

    result = _call_claude(prompt)
    if result:
        return result

    # Fallback template
    ratio = row.get('ratio_to_eia', 0)
    impact = row.get('dollar_impact_annual', 0)
    sev = row.get('severity', '')
    prop = row.get('Property', '')
    pm = row.get('PM_Company', '')
    utility = row.get('Utility_Type', '')
    per_unit = row.get('per_unit', 0)
    benchmark = row.get('eia_benchmark', 0)

    if row.get('maintenance_signal'):
        return (f"{prop}'s {utility.lower()} usage has been {ratio:.1f}x the EIA Colorado benchmark "
                f"for 3+ consecutive months, a pattern inconsistent with billing errors. "
                f"Recommend requesting a plumbing inspection — sustained water spikes at this level "
                f"typically indicate an active leak or failed valve, with annualized exposure of ${impact:,.0f}.")
    elif row.get('drift_signal'):
        return (f"{prop}'s {utility.lower()} charges have been drifting upward and now sit at "
                f"${per_unit:.0f}/unit vs. the ${benchmark:.0f}/unit EIA benchmark ({ratio:.1f}x). "
                f"The trend suggests gradual billing creep by {pm} rather than a one-time event. "
                f"Annualized exposure at current rate: ${impact:,.0f}.")
    else:
        return (f"{prop} is being billed ${per_unit:.0f}/unit for {utility.lower()} — "
                f"{ratio:.1f}x the EIA Colorado benchmark of ${benchmark:.0f}/unit. "
                f"This overcharge appears to have been present from the start of the billing period, "
                f"suggesting a structural billing error by {pm}. "
                f"Annualized exposure: ${impact:,.0f}.")


def draft_pm_email(property_name: str, pm_company: str, flags: list) -> str:
    """Draft a Level 2 escalation email to the PM for AM review."""
    flag_summary = "\n".join([
        f"  - {f.get('Utility_Type', f.get('utility',''))}: ${f.get('per_unit',0):.0f}/unit vs. ${f.get('eia_benchmark',0):.0f}/unit EIA benchmark ({f.get('ratio_to_eia',0):.1f}x), annualized impact ${f.get('dollar_impact_annual',0):,.0f}"
        for f in flags
    ])

    prompt = f"""Draft a professional but direct email from an asset manager to a property management company
flagging utility billing anomalies. Tone: firm, factual, not accusatory. Request a written explanation
and supporting documentation within 5 business days. Keep it under 200 words.

Property: {property_name}
PM Company: {pm_company}
Anomalies:
{flag_summary}"""

    result = _call_claude(prompt)
    if result:
        return result

    # Fallback template
    lines = []
    for f in flags:
        lines.append(
            f"  • {f['utility']}: ${f.get('per_unit',0):.0f}/unit billed vs. "
            f"${f.get('eia_benchmark',0):.0f}/unit EIA benchmark "
            f"({f.get('ratio_to_eia',0):.1f}x) — est. annualized impact ${f.get('dollar_impact_annual',0):,.0f}"
        )
    bullet_block = "\n".join(lines)

    return f"""Subject: Utility Billing Review — {property_name}

{pm_company} Team,

Our internal utility monitoring has identified billing anomalies at {property_name} that require your immediate attention and explanation.

The following utilities are materially above EIA Colorado benchmarks for comparable multifamily properties:

{bullet_block}

Please provide a written explanation and supporting documentation (master meter invoices, utility provider statements) within 5 business days. If these charges reflect an error, please confirm the correction timeline and any applicable credits.

We take utility cost management seriously and will escalate unresolved discrepancies to our investment committee.

Best regards,
Asset Management"""


def generate_gp_report(property_name: str, pm_company: str, flags: list) -> str:
    """
    Generate a Level 3 one-page summary for the AM to present to GPs.
    This is NOT auto-sent — it's a report the AM brings to the GP conversation.
    """
    flag_summary = "\n".join([
        f"  - {f.get('Utility_Type', f.get('utility',''))}: ${f.get('per_unit',0):.0f}/unit vs ${f.get('eia_benchmark',0):.0f}/unit EIA "
        f"({f.get('ratio_to_eia',0):.1f}x) — annualized impact ${f.get('dollar_impact_annual',0):,.0f}"
        for f in flags
    ])
    total_exposure = sum(f.get('dollar_impact_annual', 0) for f in flags)
    maint = any(f.get('maintenance_signal') for f in flags)

    prompt = f"""Generate a concise one-page GP briefing summary for an asset manager to present verbally.
Format: plain text, 3 sections (Situation, Financial Impact, Recommended Action). No fluff. Under 250 words.

Property: {property_name}
PM: {pm_company}
Total annualized exposure: ${total_exposure:,.0f}
Maintenance signal: {maint}
Anomaly detail:
{flag_summary}"""

    result = _call_claude(prompt)
    if result:
        return result

    # Fallback template
    maint_note = "\nA sustained water usage anomaly has also been detected, consistent with an active plumbing issue. A physical inspection is recommended before further action with the PM." if maint else ""

    return f"""GP BRIEFING — {property_name}
{'='*50}

SITUATION
Our utility monitoring has flagged {pm_company} for material billing anomalies at {property_name}. Charges across multiple utility categories are significantly above EIA Colorado benchmarks for comparable multifamily assets, and the pattern is consistent across the full billing history — indicating this is structural, not a one-time error.{maint_note}

FINANCIAL IMPACT
Total annualized exposure: ${total_exposure:,.0f}

Breakdown by utility:
{flag_summary}

RECOMMENDED ACTION
1. Issue a formal written inquiry to {pm_company} requesting master meter invoices and billing reconciliation within 5 business days.
2. If no satisfactory explanation is provided, engage a third-party utility auditor.
3. Evaluate PM contract terms for recovery options on historical overcharges.
4. Consider PM replacement if pattern cannot be resolved — this is not a one-property issue.

Note: This report was generated by AM Watchdog and is for internal use only. All figures are based on EIA Colorado benchmarks for comparable MF assets and have not yet been verified against source invoices."""


def generate_dd_narrative(property_name: str, utility_summary: list, overall_flag: str) -> str:
    """Generate an acquisition DD utility assessment narrative."""
    lines = [f"  - {u['utility']}: avg ${u['avg_per_unit']:.0f}/unit/mo vs ${u['benchmark']:.0f}/unit benchmark ({u['ratio']:.1f}x)" for u in utility_summary]
    summary_block = "\n".join(lines)

    prompt = f"""You are underwriting a multifamily acquisition. Summarize the utility cost findings
in 3-4 professional sentences for an investment memo. Flag any risks clearly. No bullet points.

Property: {property_name}
Overall flag: {overall_flag}
Utility findings:
{summary_block}"""

    result = _call_claude(prompt)
    if result:
        return result

    # Fallback
    flagged = [u for u in utility_summary if u['ratio'] > 1.4]
    if not flagged:
        return (f"Utility costs at {property_name} are in line with EIA Colorado benchmarks across all categories. "
                f"No material billing anomalies detected in the historical data provided. "
                f"Utility expense assumptions in the underwriting model appear supportable.")
    else:
        items = ", ".join([f"{u['utility'].lower()} ({u['ratio']:.1f}x benchmark)" for u in flagged])
        return (f"Historical utility data for {property_name} shows elevated costs in {items}, "
                f"which warrant further investigation during due diligence. "
                f"These levels may reflect deferred maintenance, billing irregularities, or structural inefficiencies "
                f"that could compress NOI post-acquisition. "
                f"Recommend requesting master meter invoices and PM billing reconciliations before closing.")
