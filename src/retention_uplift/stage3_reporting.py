"""Aggregate-only figures and a concise business brief from saved numeric results."""

import html

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def interval(result):
    return f"{result['estimate']:,.2f} [{result['ci95'][0]:,.2f}, {result['ci95'][1]:,.2f}]"


def business_summary(report):
    c = report["protocol"]["economics"]
    s = report["scenarios"][c["primary"]]
    p, o = s["planning"]["profit"], s["observed"]["policies"]["profit"]
    pilot = report["pilot"]
    lines = [
        "# Customer retention decision brief",
        "",
        "**Synthetic customers; illustrative GBP economics; no real campaign or profit.**",
        "",
        "**Decision question.** Which offers are worth funding? Churn risk alone "
        "measures who may leave; "
        "it does not measure who changes behaviour because of an offer. Positive uplift "
        "must also cover cost.",
        "",
        f"**Current decision: {s['recommendation'].replace('_', ' ')}.** The frozen "
        f"T-learner ranks "
        "customers by predicted incremental contribution less cost, excluding "
        "nonpositive opportunities. "
        "A prediction is a planning estimate, not a guaranteed customer or financial return.",
        "",
        f"**Plan.** Across {report['n_customers']:,} fresh synthetic customers, select "
        f"{p['selected']:,}; "
        f"spend £{p['spend_gbp']:,.2f} of the £{c['budget']:,.2f} maximum, with a "
        f"{c['maximum_contacts']:,}-contact ceiling. Predicted incremental retained customers: "
        f"{p['predicted_incremental_retained']:.2f}; gross value £{p['predicted_gross_gbp']:,.2f}; "
        f"net value £{p['predicted_net_gbp']:,.2f}. Unspent budget £{p['unspent_gbp']:,.2f}.",
        "",
        f"**Evidence.** Randomized-outcome estimated net value: £{interval(o['net_gbp'])}; "
        f"incremental retained customers: {interval(o['incremental_retained'])}. "
        f"Brackets are pointwise "
        "95% intervals. They condition on the model and assumed economics. They do not "
        "validate real profit.",
        "",
        f"**Assumptions.** Each extra retained customer contributes "
        f"£{s['assumptions']['value']:.2f} "
        f"over 30 days. Each selected customer costs £{s['assumptions']['offer_cost']:.2f} plus "
        f"£{s['assumptions']['contact_cost']:.2f} contact cost, even if they leave. "
        f"These are examples, "
        "not measured lifetime values or industry costs. Customer spending is not company revenue.",
        "",
        "**Sensitivity.** Prespecified scenarios give the following decisions:",
        "",
        "| Assumption | Contacts | Spend GBP | Estimated net GBP [95% CI] | Decision |",
        "|---|---:|---:|---|---|",
    ]
    for name, scenario in report["scenarios"].items():
        plan = scenario["planning"]["profit"]
        lines.append(
            f"| {name} | {plan['selected']} | {plan['spend_gbp']:.2f} | "
            f"{interval(scenario['observed']['policies']['profit']['net_gbp'])} | "
            f"{scenario['recommendation'].replace('_', ' ')} |"
        )
    lines += [
        "",
        f"**Next evidence, not rollout.** If business assumptions and guardrails are validated, "
        f"randomize offers within the frozen targeted population: {pilot['control']:,} "
        f"controls and "
        f"{pilot['treatment']:,} treated customers for an assumed "
        f"{100 * pilot['p0']:.0f}% baseline, "
        f"+{pilot['mde_pp']:.1f} "
        f"percentage-point effect, "
        "80% power and two-sided 5% significance. This tests the offer within that "
        "population, not whole-policy "
        "superiority or profit. Review complaints, opt-outs and delivery quality; avoid "
        "repeated interim testing.",
        "",
        "**Limits.** Designed simulation, uncertain effects, hypothetical economics and "
        "unadjusted scenario "
        "comparisons. Stage 2 results were already examined; this final cohort has a "
        "different seed and "
        "disjoint IDs. No real retention or profitability gain has been demonstrated. "
        "Real deployment requires "
        "privacy assessment, domain validation and genuine randomized evidence.",
    ]
    return "\n".join(lines) + "\n"


def render(report, output):
    label = "Synthetic customers | illustrative economics"
    economics = report["protocol"]["economics"]
    primary = report["scenarios"][economics["primary"]]

    def save(name):
        plt.tight_layout()
        plt.savefig(output / name, dpi=150)
        plt.close()

    plt.figure(figsize=(8, 4.5))
    rows = report["budget_curve"]
    plt.plot([r["budget_gbp"] for r in rows], [r["predicted_net_gbp"] for r in rows], marker="o")
    plt.xlabel("Maximum campaign budget (GBP)")
    plt.ylabel("Predicted incremental net value (GBP)")
    plt.title("Profit-aware planning at fixed contact ceiling\n" + label)
    save("net-vs-budget.png")
    for name, entries in (
        (
            "policy-comparison.png",
            {k: v["net_gbp"] for k, v in primary["observed"]["policies"].items()},
        ),
        (
            "financial-sensitivity.png",
            {
                k: v["observed"]["policies"]["profit"]["net_gbp"]
                for k, v in report["scenarios"].items()
            },
        ),
    ):
        plt.figure(figsize=(9, 5))
        for i, (_key, value) in enumerate(entries.items()):
            plt.plot(value["ci95"], [i, i], color="tab:blue")
            plt.scatter(value["estimate"], i, color="tab:blue")
        labels = [f"{k} (screened)" if k in ("random", "churn", "uplift") else k for k in entries]
        plt.yticks(range(len(entries)), labels)
        plt.axvline(0, color="black", linestyle="--", linewidth=1)
        plt.xlabel("Observed-outcome incremental net GBP (pointwise 95% CI)")
        plt.title(
            f"Maximum GBP{economics['budget']:g}; {economics['maximum_contacts']} contacts\n"
            + label
        )
        save(name)
    plt.figure(figsize=(8, 4.5))
    plt.plot(
        [r["mde_pp"] for r in report["pilot_curve"]],
        [r["total"] for r in report["pilot_curve"]],
        marker="o",
    )
    plt.xlabel("Minimum detectable retention effect (percentage points)")
    plt.ylabel("Required customers, both arms")
    plt.title(
        f"Hypothetical pilot: {100 * report['pilot']['target_power']:g}% power, "
        f"{100 * report['pilot']['alpha']:g}% two-sided alpha\nSynthetic "
        "planning assumptions; economics illustrative"
    )
    save("pilot-sample-size.png")
    (output / "business-summary.md").write_text(business_summary(report), encoding="utf-8")
    (output / "business-summary.html").write_text(business_html(report), encoding="utf-8")


def business_html(report):
    """Self-contained A4 business page; no external fonts, scripts or tracking."""
    blocks, in_table = [], False
    for line in business_summary(report).splitlines():
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            if not in_table:
                blocks.append("<table>")
                in_table = True
            blocks.append(
                "<tr>"
                + "".join(
                    "<td>" + html.escape(c.strip()) + "</td>" for c in line.strip("|").split("|")
                )
                + "</tr>"
            )
        else:
            if in_table:
                blocks.append("</table>")
                in_table = False
            if line:
                tag = "h1" if line.startswith("# ") else "p"
                text = line.removeprefix("# ").replace("**", "")
                blocks.append(f"<{tag}>{html.escape(text)}</{tag}>")
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>Synthetic retention decision brief</title><style>"
        "@page{size:A4;margin:12mm}*{box-sizing:border-box}"
        "body{font:10pt/1.3 Arial,sans-serif;color:#172b3a;margin:0}"
        "main{width:186mm;margin:auto}h1{font-size:20pt;margin:0 0 8px}"
        "p{margin:0 0 8px}table{border-collapse:collapse;width:100%;font-size:8.3pt;"
        "margin-bottom:8px}td{border-bottom:1px solid #ccd6dc;padding:4px}"
        "tr:first-child{background:#e8f0f5;font-weight:bold}"
        "@media screen{body{background:#edf1f4;padding:20px}"
        "main{background:white;padding:12mm;width:210mm;min-height:297mm}}"
        "</style><main>" + "".join(blocks) + "</main></html>"
    )
