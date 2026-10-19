"""Figures and readable summaries derived exclusively from saved aggregate metrics."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render(report: dict, output: Path):
    label = f"Synthetic; N={report['n_customers']:,}; held-out test n={report['n_test']:,}"
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

    def finish(fig, name):
        fig.suptitle(label, fontsize=11)
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.savefig(output / f"{name}.png", dpi=160)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    groups = report["churn"]["calibration"]
    ax.plot([g["predicted"] for g in groups], [g["observed"] for g in groups], "o-")
    ax.plot([0, 1], [0, 1], "--", color="gray")
    ax.set(
        xlabel="Predicted untreated churn probability",
        ylabel="Observed control churn frequency",
        title=f"Control-only calibration (n={report['churn']['n_control']:,})",
    )
    finish(fig, "churn-calibration")

    fig, ax = plt.subplots(figsize=(7, 5))
    for name, result in report["oracle"].items():
        g = result["rank_groups"]
        ax.plot(np.arange(1, len(g) + 1), [100 * x["true"] for x in g], "o-", label=f"{name}: true")
        ax.plot(
            np.arange(1, len(g) + 1),
            [100 * x["predicted"] for x in g],
            "--",
            label=f"{name}: predicted",
        )
    ax.set(
        xlabel="Ranked group (1 = highest predicted uplift)",
        ylabel="Retention effect (percentage points)",
        title="Evaluation-only oracle calibration",
    )
    ax.legend(fontsize=8, ncol=2)
    finish(fig, "uplift-calibration")

    fig, ax = plt.subplots(figsize=(7, 5))
    for name, curve in report["curves"].items():
        ax.plot(curve["fraction"], 100 * np.array(curve["gain"]), label=name)
    ate = report["observed"]["ate"]["estimate"]
    ax.plot([0, 1], [0, 100 * ate], "--", color="gray", label="Random-ranking expectation")
    ax.set(
        xlabel="Fraction ranked for outreach",
        ylabel="Cumulative IPW gain / test N (pp)",
        title="Observed randomized-outcome gain curves",
    )
    ax.legend()
    finish(fig, "observed-gain")

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    for name, color in (("random", "gray"), ("churn", "#bd6000"), ("uplift", "#0068a8")):
        items = [
            (k, v) for k, v in report["observed"]["policies"].items() if k.startswith(name + "@")
        ]
        x = [float(k.split("@")[1]) * 100 for k, v in items]
        axes[0].plot(
            x, [100 * v["oracle_increment"] for k, v in items], "o-", color=color, label=name
        )
        means = np.array([v["estimate"] for k, v in items]) * 100
        lo = np.array([v["ci95"][0] for k, v in items]) * 100
        hi = np.array([v["ci95"][1] for k, v in items]) * 100
        axes[1].plot(x, means, "o-", color=color, label=name)
        axes[1].fill_between(x, lo, hi, color=color, alpha=0.12)
    axes[0].set_title("Oracle expected incremental retention")
    axes[1].set_title("Observed IPW estimates with pointwise 95% CIs")
    for ax in axes:
        ax.set(
            xlabel="Requested outreach (%) — shared positive-score cap",
            ylabel="Increment vs no offer, all test customers (pp)",
        )
        ax.axhline(0, color="black", lw=0.6)
        ax.legend()
    finish(fig, "policy-comparison")

    lines = [
        "# Stage 2 measured results",
        "",
        label,
        "",
        f"Selected estimator: **{report['selection']['selected_uplift']}**, "
        "using validation observed transformed-outcome loss only.",
        "",
        "Churn targeting ranks untreated churn risk; "
        "uplift targeting ranks predicted treatment benefit.",
        "",
        f"Control test ROC-AUC: {report['churn']['roc_auc']}; Brier: {report['churn']['brier']}.",
        "",
        "| Model | Oracle MAE | Oracle RMSE | Observed Qini area |",
        "|---|---:|---:|---:|",
    ]
    for name, v in report["oracle"].items():
        lines.append(
            f"| {name} | {v['mae']:.6f} | {v['rmse']:.6f} | "
            f"{report['curves'][name]['qini_area']:.6f} |"
        )
    lines += [
        "",
        "All policy estimates below are percentage points over the entire test population "
        "relative to no offer.",
        "",
        "| Policy / requested fraction | Actual count | IPW pp | 95% CI pp | Oracle pp |",
        "|---|---:|---:|---|---:|",
    ]
    for k, v in report["observed"]["policies"].items():
        lines.append(
            f"| {k} | {v['targeted']} | {100 * v['estimate']:.3f} | "
            f"[{100 * v['ci95'][0]:.3f}, {100 * v['ci95'][1]:.3f}] | "
            f"{100 * v['oracle_increment']:.3f} |"
        )
    lines += [
        "",
        "Paired differences (uplift minus comparator), pointwise 95% bootstrap intervals:",
        "",
    ]
    for k, v in report["observed"]["paired_differences"].items():
        lines.append(
            f"- {k}: {100 * v['estimate']:.3f} pp "
            f"[{100 * v['ci95'][0]:.3f}, {100 * v['ci95'][1]:.3f}]."
        )
    lines += [
        "",
        "Intervals condition on fitted models and fixed test allocations; no training uncertainty "
        "or multiplicity correction. Test customers come from the same synthetic experiment. "
        "Oracle error includes inaccessible latent heterogeneity. No real retention improvement, "
        "profit, ROI or production validation has been demonstrated. Stage 3 is not implemented.",
    ]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
