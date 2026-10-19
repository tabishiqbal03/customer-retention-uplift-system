"""Freeze protocol, generate disjoint cohort, freeze decisions, evaluate, then oracle."""

import csv
import hashlib
import json
import platform
import time
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np

from retention_uplift.config import Config
from retention_uplift.economics import break_even, customer_values, read_economics
from retention_uplift.evaluation import load_test_truth
from retention_uplift.experiment_design import monte_carlo, sample_size
from retention_uplift.features import MODEL_FEATURES
from retention_uplift.financial_evaluation import evaluate_financial
from retention_uplift.modelling_data import load_observations, read_frame
from retention_uplift.optimizer import build_policies
from retention_uplift.pipeline import run
from retention_uplift.stage2 import save_json


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_features(spark, source, max_customers=120000):
    """Does not open assignment, outcome or oracle files."""
    if not (source / "_SUCCESS").exists():
        raise ValueError("Validated generation required")
    frame = read_frame(spark, source, "features").select("customer_id", *MODEL_FEATURES)
    if not 30 <= frame.count() <= max_customers:
        raise ValueError("Feature collection bound exceeded")
    rows = frame.orderBy("customer_id").collect()
    ids = np.array([r.customer_id for r in rows])
    x = np.array([[r[k] for k in MODEL_FEATURES] for r in rows], dtype=float)
    if (
        len(set(ids)) != len(ids)
        or any(i is None or not i for i in ids)
        or not np.isfinite(x).all()
    ):
        raise ValueError("Unique IDs and finite features required")
    return ids, x


def run_stage3(spark, cohort_config, model_dir, training_source, economics_path, output):
    """Load only trusted local joblib artifacts, never arbitrary downloaded pickle files."""
    started = time.perf_counter()
    if output.exists():
        raise FileExistsError(output)
    config, scenarios = read_economics(economics_path)
    cohort = Config.read(cohort_config)
    training = json.loads((training_source / "config.json").read_text())
    if cohort.seed == training["seed"] or cohort.customer_prefix == training.get(
        "customer_prefix", "C"
    ):
        raise ValueError("Fresh evaluation requires distinct seed AND ID namespace")
    if not (model_dir / "_SUCCESS").exists() or not (training_source / "_SUCCESS").exists():
        raise ValueError("Completed Stage 1 and Stage 2 artifacts required")
    selection = json.loads((model_dir / "selection.json").read_text())
    model_metrics = json.loads((model_dir / "metrics.json").read_text())
    training_validation = json.loads((training_source / "validation.json").read_text())
    if (
        model_metrics["source_config"] != training
        or model_metrics["source_fingerprints"] != training_validation["fingerprints"]
    ):
        raise ValueError("Stage 2 model provenance does not match training source")
    if selection["features"] != list(MODEL_FEATURES) or selection["selected_uplift"] != "t":
        raise ValueError("Stage 3 protocol freezes the Stage 2 selected T-learner")
    bundle = joblib.load(model_dir / "models.joblib")
    if bundle["selection"] != selection or bundle["uplift"]["t"].kind != "t":
        raise ValueError("Model artifact and selection disagree")
    with (model_dir / "split-manifest.csv").open(newline="") as f:
        old_ids = {r["customer_id"] for r in csv.DictReader(f)}
    model_hash = digest(model_dir / "models.joblib")
    protocol = {
        "synthetic": True,
        "illustrative_economics": True,
        "economics": config,
        "cohort_config": cohort.as_dict(),
        "training_config": training,
        "model_sha256": model_hash,
        "selection": selection,
        "economics_sha256": digest(economics_path),
        "metrics": "IPW incremental retained and net GBP; paired percentile 95% customer bootstrap",
        "freeze_order": [
            "protocol",
            "generation",
            "features_only",
            "policies",
            "observed",
            "oracle",
        ],
        "stage2_test_previously_examined": True,
    }
    output.mkdir(parents=True)
    save_json(output / "protocol.json", protocol)  # BEFORE any fresh data exists
    source = output / "cohort"
    generation = run(spark, cohort, source, "portable")
    ids, x = load_features(spark, source)
    if old_ids.intersection(ids):
        raise ValueError("Fresh IDs overlap Stage 2 customers")
    uplift = bundle["uplift"]["t"].predict(x)
    risk = bundle["churn"].predict_proba(x)[:, 1]
    frozen, results, arrays = {}, {}, {"ids": ids, "uplift": uplift, "risk": risk}
    for s in scenarios:
        values = customer_values(x, s)
        policies, planning = build_policies(
            ids,
            risk,
            uplift,
            values,
            s.cost,
            config["budget"],
            config["maximum_contacts"],
            config["policy_seed"],
        )
        frozen[s.name] = (values, policies)
        arrays[s.name + "_values"] = values
        arrays.update({s.name + "_" + k: v for k, v in policies.items()})
        results[s.name] = {
            "assumptions": asdict(s),
            "planning": planning,
            "break_even_uplift": break_even(s.value, s.cost) if s.value_mode == "fixed" else None,
        }
    primary = next(s for s in scenarios if s.name == config["primary"])
    budget_curve = []
    for budget in config["budget_grid"]:
        _, planning = build_policies(
            ids,
            risk,
            uplift,
            frozen[primary.name][0],
            primary.cost,
            budget,
            config["maximum_contacts"],
            config["policy_seed"],
        )
        budget_curve.append({"budget_gbp": budget, **planning["profit"]})
    np.savez_compressed(output / "frozen-policies.npz", **arrays)
    save_json(output / "planning.json", results)
    save_json(
        output / "decision-freeze.json",
        {
            "policies_sha256": digest(output / "frozen-policies.npz"),
            "planning_sha256": digest(output / "planning.json"),
            "ids_disjoint": True,
            "old_customers": len(old_ids),
            "new_customers": len(ids),
        },
    )
    # Only now does the financial workflow open observed outcome/assignment tables.
    data = load_observations(spark, source)
    if not np.array_equal(ids, data.ids) or not np.array_equal(x, data.x):
        raise ValueError("Evaluation customer alignment changed")
    for s in scenarios:
        values, policies = frozen[s.name]
        observed = evaluate_financial(
            data, policies, values, s.cost, config["bootstrap"], config["bootstrap_seed"]
        )
        results[s.name]["observed"] = observed
        ci = observed["policies"]["profit"]["net_gbp"]["ci95"]
        results[s.name]["recommendation"] = (
            "no_offer"
            if results[s.name]["planning"]["profit"]["selected"] == 0
            else "no_rollout_negative_evidence"
            if ci[1] < 0
            else "controlled_pilot"
            if ci[0] > 0
            else "inconclusive_no_rollout"
        )
    save_json(output / "observed.json", results)
    # Oracle diagnostics cannot affect frozen masks or observed estimation.
    truth = load_test_truth(spark, source, ids)
    for s in scenarios:
        values, policies = frozen[s.name]
        results[s.name]["oracle_diagnostic"] = {
            k: {
                "incremental_retained": float(np.sum(mask * truth["tau"])),
                "net_gbp": float(np.sum(mask * (values * truth["tau"] - s.cost))),
            }
            for k, mask in policies.items()
        }
    pilot = sample_size(**config["pilot"])
    pilot["simulation"] = monte_carlo(pilot)
    pilot_curve = [
        sample_size(**{**config["pilot"], "mde": m}) for m in (0.01, 0.02, 0.03, 0.04, 0.05)
    ]
    if digest(model_dir / "models.joblib") != model_hash:
        raise ValueError("Model artifact changed during evaluation")
    report = {
        "schema_version": 1,
        "synthetic": True,
        "illustrative_economics": True,
        "n_customers": len(ids),
        "protocol": protocol,
        "scenarios": results,
        "budget_curve": budget_curve,
        "pilot": pilot,
        "pilot_curve": pilot_curve,
        "generation": generation,
        "python": platform.python_version(),
        "versions": {
            k: version(k)
            for k in ("numpy", "scipy", "scikit-learn", "pyspark", "pyarrow", "matplotlib")
        },
        "elapsed_before_rendering_seconds": time.perf_counter() - started,
    }
    save_json(output / "metrics.json", report)
    from retention_uplift.stage3_reporting import render

    render(report, output)
    (output / "_SUCCESS").write_text(
        "Stage 3 generation, frozen policies, evaluation and reports complete.\n"
    )
    return report
