"""Reproducible Stage 2 workflow: lock selection, freeze decisions, then evaluate."""

import csv
import json
import platform
import time
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np

from retention_uplift.evaluation import churn_metrics, load_test_truth, oracle_metrics
from retention_uplift.features import MODEL_FEATURES
from retention_uplift.modelling_data import load_observations, split_customers
from retention_uplift.models import select_models
from retention_uplift.policy import evaluate_policies, gain_curve, ipw_signal, make_policies


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def run_stage2(spark, source: Path, output: Path, replications=1000, iterations=100):
    if output.exists():
        raise FileExistsError(output)
    started = time.perf_counter()
    output.mkdir(parents=True)
    data = load_observations(spark, source)
    membership = split_customers(data)
    subsets = {k: data.subset(membership == k) for k in ("train", "validation", "test")}
    with (output / "split-manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["customer_id", "split"])
        writer.writerows(zip(data.ids, membership, strict=True))
    models, risk_model, selected, attempts = select_models(
        subsets["train"], subsets["validation"], iterations=iterations
    )
    selection = {
        "selected_uplift": selected,
        "selected_leaves": {k: m.leaves for k, m in models.items() if k != "constant"},
        "selected_churn_C": risk_model[-1].C,
        "tree_parameters": {
            "learning_rate": 0.05,
            "min_samples_leaf": 40,
            "l2_regularization": 10,
            "early_stopping": False,
        },
        "attempts": attempts,
        "iterations": iterations,
        "features": list(MODEL_FEATURES),
        "split_seed": 20261020,
        "model_seed": 20261021,
        "policy_seed": 20261022,
        "bootstrap_seed": 20261023,
        "replications": replications,
        "refit_validation": False,
    }
    # Persist selected configuration BEFORE any test prediction/evaluation or truth read.
    save_json(output / "selection.json", selection)
    joblib.dump(
        {"uplift": models, "churn": risk_model, "selection": selection}, output / "models.joblib"
    )
    test = subsets["test"]
    scores = {k: m.predict(test.x) for k, m in models.items()}
    risk = risk_model.predict_proba(test.x)[:, 1]
    policies = make_policies(test.ids, risk, scores[selected])
    # Save frozen policies/predictions before seeing observed test outcomes or oracle.
    np.savez_compressed(
        output / "test-predictions.npz", ids=test.ids, risk=risk, **scores, **policies
    )
    observed = evaluate_policies(test, policies, replications)
    signal = ipw_signal(test.treatment, test.outcome, test.propensity)
    curves = {k: gain_curve(test.ids, v, signal) for k, v in scores.items()}
    curves["churn"] = gain_curve(test.ids, risk, signal)
    truth = load_test_truth(spark, source, test.ids)
    for k, mask in policies.items():
        observed["policies"][k]["oracle_increment"] = float(np.mean(mask * truth["tau"]))
        observed["policies"][k]["oracle_retention_value"] = float(
            np.mean(truth["p0"] + mask * truth["tau"])
        )
    counts = {}
    for k, d in subsets.items():
        counts[k] = {
            "n": len(d.ids),
            "treated": int(d.treatment.sum()),
            "control": int((1 - d.treatment).sum()),
            "retained": int(d.outcome.sum()),
            "retention_rate": float(d.outcome.mean()),
            "arms": {
                str(a): {
                    "n": int(sum(d.treatment == a)),
                    "retained": int(d.outcome[d.treatment == a].sum()),
                }
                for a in (0, 1)
            },
        }
    report = {
        "synthetic": True,
        "n_customers": len(data.ids),
        "n_test": len(test.ids),
        "selection": selection,
        "splits": counts,
        "churn": churn_metrics(test, risk),
        "oracle": {k: oracle_metrics(test.ids, v, truth["tau"]) for k, v in scores.items()},
        "curves": curves,
        "observed": observed,
        "versions": {
            k: version(k)
            for k in (
                "numpy",
                "scikit-learn",
                "scipy",
                "matplotlib",
                "pyspark",
                "pyarrow",
                "joblib",
            )
        },
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_config": json.loads((source / "config.json").read_text()),
        "source_fingerprints": json.loads((source / "validation.json").read_text())["fingerprints"],
        "customer_matrix_bytes": data.x.nbytes,
        "elapsed_seconds_before_rendering": time.perf_counter() - started,
    }
    save_json(output / "metrics.json", report)
    from retention_uplift.stage2_reporting import render

    render(report, output)
    (output / "_SUCCESS").write_text(
        "Stage 2 fit, selection, evaluation and reporting completed.\n"
    )
    return report
