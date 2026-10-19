"""Economic, exact-allocation, causal and independent-cohort protocol checks."""

import itertools
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from retention_uplift.config import Config
from retention_uplift.economics import (
    Scenario,
    break_even,
    customer_values,
    net_scores,
    read_economics,
)
from retention_uplift.experiment_design import monte_carlo, sample_size
from retention_uplift.features import MODEL_FEATURES
from retention_uplift.financial_evaluation import evaluate_financial
from retention_uplift.modelling_data import Observations
from retention_uplift.optimizer import build_policies


def test_economic_units_negative_zero_and_break_even():
    np.testing.assert_allclose(net_scores([0.1, -0.2, 0.05], [40, 40, 40], 2), [2, -10, 0])
    np.testing.assert_equal(net_scores([-0.1, 0.2], [0, 0], 0), [0, 0])
    assert break_even(40, 2) == 0.05
    assert break_even(0, 2) is None
    assert break_even(0, 0) is None
    assert break_even(40, 0) == 0


@pytest.mark.parametrize("value,cost", [(-1, 2), (2, -1), (np.nan, 1), (1, np.inf), (1, [1])])
def test_invalid_money(value, cost):
    with pytest.raises(ValueError):
        net_scores([0.2], [value], cost)


def test_valuation_only_named_historical_usage():
    x = np.zeros((3, len(MODEL_FEATURES)))
    x[:, MODEL_FEATURES.index("active_months")] = [0, 6, 12]
    x[:, MODEL_FEATURES.index("products_used")] = [0, 1.5, 3]
    scenario = Scenario("example", 40, 1.5, 0.5, "usage")
    np.testing.assert_equal(customer_values(x, scenario), [20, 40, 60])
    x[:, MODEL_FEATURES.index("card_spend_gbp")] = 10000000
    np.testing.assert_equal(customer_values(x, scenario), [20, 40, 60])
    np.testing.assert_equal(customer_values(x, replace(scenario, value_mode="fixed")), [40] * 3)
    with pytest.raises(ValueError):
        customer_values(np.column_stack((x, np.ones(3))), scenario)
    with pytest.raises(ValueError):
        Scenario("bad", -1, 0, 0)


def test_optimality_by_exhaustive_binary_enumeration():
    ids = np.array(list("abcde"))
    uplift = np.array([0.1, -0.1, 0.3, 0.2, 0.05])
    values = np.array([20, 20, 10, 40, 20])
    net = net_scores(uplift, values, 1)
    policies, plans = build_policies(ids, np.arange(5), uplift, values, 1, 2.5, 3)
    feasible = [
        np.dot(bits, net)
        for bits in itertools.product((0, 1), repeat=5)
        if sum(bits) <= 3
        and sum(bits) <= 2.5
        and all(not b or v > 0 for b, v in zip(bits, net, strict=True))
    ]
    assert plans["profit"]["predicted_net_gbp"] == max(feasible)
    for name, mask in policies.items():
        assert mask.sum() <= 3
        assert plans[name]["spend_gbp"] <= 2.5
        assert (net[mask] > 0).all()
    reversed_policies, _ = build_policies(
        ids[::-1], np.arange(5)[::-1], uplift[::-1], values[::-1], 1, 2.5, 3
    )
    for name in policies:
        np.testing.assert_equal(policies[name][::-1], reversed_policies[name])


@pytest.mark.parametrize(
    "cost,budget,capacity,expected", [(0, 0, 2, 2), (2, 1, 3, 0), (1, 100, 0, 0), (1, 100, 3, 1)]
)
def test_zero_and_unspent_cases(cost, budget, capacity, expected):
    _, p = build_policies(
        np.array(list("abc")), [1, 1, 1], [0.2, 0.05, -0.1], np.full(3, 10), cost, budget, capacity
    )
    assert p["profit"]["selected"] == expected
    assert p["profit"]["unspent_gbp"] == budget - cost * expected


@pytest.mark.parametrize("budget,capacity", [(-1, 2), (np.inf, 2), (1, -1), (1, 1.5)])
def test_invalid_constraints(budget, capacity):
    with pytest.raises(ValueError):
        build_policies(["a"], [1], [0.2], [40], 1, budget, capacity)


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        build_policies(["a", "a"], [1, 2], [0.1, 0.2], [40, 40], 1, 10, 2)


def test_weighted_financial_fixture_cost_on_controls_and_paired_covariance():
    d = Observations(
        np.array(list("abcd")),
        np.zeros((4, 22)),
        np.array([1, 0, 1, 0]),
        np.array([1, 1, 0, 0]),
        np.full(4, 0.25),
    )
    mask = np.array([1, 1, 0, 0])
    policies = {"no_offer": np.zeros(4), "profit": mask, "uplift": mask}
    a = evaluate_financial(d, policies, np.full(4, 3), 2, 100)
    # 3*(4-4/3) - 2*2 = 4. Cost includes the selected control.
    assert a["policies"]["profit"]["net_gbp"]["estimate"] == pytest.approx(4)
    assert a["policies"]["profit"]["incremental_retained"]["estimate"] == pytest.approx(8 / 3)
    assert a["policies"]["no_offer"]["net_gbp"]["ci95"] == [0, 0]
    assert a["paired_net_gbp"]["profit - uplift"]["ci95"] == [0, 0]
    assert a == evaluate_financial(d, policies, np.full(4, 3), 2, 100)


def test_financial_estimator_expectation_enumerated():
    # Four possible randomized events; exact probability-weighted expectation.
    from retention_uplift.policy import ipw_signal

    p0, p1, e, v, c = 0.3, 0.7, 0.2, 40, 2
    weights = np.array([(1 - e) * (1 - p0), (1 - e) * p0, e * (1 - p1), e * p1])
    signal = ipw_signal([0, 0, 1, 1], [0, 1, 0, 1], [e] * 4)
    assert np.dot(weights, v * signal - c) == pytest.approx(v * (p1 - p0) - c)


def test_power_reference_and_allocation():
    # Independent arithmetic using tabulated normal quantiles: .50 vs .55,
    # alpha .05, power .8 needs 1565 per arm (unrounded 1564.672053).
    p = sample_size(0.5, 0.05)
    assert p["control"] == p["treatment"] == 1565
    assert p["raw_control"] == pytest.approx(1564.672053, abs=0.00001)
    assert sample_size(0.6, 0.02)["total"] > sample_size(0.6, 0.03)["total"]
    unequal = sample_size(0.6, 0.03, ratio=2)
    assert unequal["treatment"] == 2 * unequal["control"]
    assert sample_size(0.6, p1=0.63) == sample_size(0.6, 0.03)
    mc = monte_carlo(sample_size(0.6, 0.03), repetitions=10000)
    assert abs(mc["power"]["estimate"] - 0.8) < 0.025
    assert abs(mc["type1"]["estimate"] - 0.05) < 0.015


@pytest.mark.parametrize(
    "kwargs",
    [
        {"p0": 0},
        {"p0": 0.99},
        {"alpha": 0},
        {"power": 1},
        {"ratio": 0},
        {"mde": 0},
        {"mde": -0.1},
        {"alpha": np.nan},
    ],
)
def test_invalid_power(kwargs):
    with pytest.raises(ValueError):
        sample_size(**{**{"p0": 0.6, "mde": 0.03}, **kwargs})


def test_config_and_prefix():
    config, scenarios = read_economics(Path("configs/economics.toml"))
    assert config["bootstrap"] >= 1000
    assert len(scenarios) == 7
    assert Config().customer_prefix == "C"
    with pytest.raises(ValueError):
        Config(customer_prefix="C1|")


@pytest.mark.integration
def test_stage3_complete_workflow_and_read_order(spark, tmp_path, monkeypatch):
    import retention_uplift.stage3 as workflow
    from retention_uplift.pipeline import run
    from retention_uplift.stage2 import run_stage2

    source, models, output = (tmp_path / k for k in ("old", "models", "final"))
    run(spark, Config(customers=160, partitions=2), source, "portable")
    run_stage2(spark, source, models, replications=100, iterations=5)
    # Engineering fixture may select S; explicitly use fitted T for protocol mechanics.
    import joblib

    from retention_uplift.stage2 import save_json

    bundle = joblib.load(models / "models.joblib")
    bundle["selection"]["selected_uplift"] = "t"
    joblib.dump(bundle, models / "models.joblib")
    save_json(models / "selection.json", bundle["selection"])
    cohort = tmp_path / "cohort.toml"
    cohort.write_text('customers=160\nseed=20261103\ncustomer_prefix="FINAL"\npartitions=2\n')
    original_run, original_obs, original_truth = (
        workflow.run,
        workflow.load_observations,
        workflow.load_test_truth,
    )
    events = []

    def generate(*args):
        assert (output / "protocol.json").exists()
        events.append("generate")
        return original_run(*args)

    def observed(*args):
        assert (output / "decision-freeze.json").exists()
        assert not (output / "observed.json").exists()
        events.append("observed")
        return original_obs(*args)

    def oracle(*args):
        assert (output / "observed.json").exists()
        events.append("oracle")
        return original_truth(*args)

    monkeypatch.setattr(workflow, "run", generate)
    monkeypatch.setattr(workflow, "load_observations", observed)
    monkeypatch.setattr(workflow, "load_test_truth", oracle)
    report = workflow.run_stage3(
        spark, cohort, models, source, Path("configs/economics.toml"), output
    )
    assert events == ["generate", "observed", "oracle"]
    assert (output / "_SUCCESS").exists()
    assert len(list(output.glob("*.png"))) == 4
    assert json.loads((output / "metrics.json").read_text()) == report
    from retention_uplift.stage3_reporting import business_summary

    assert (output / "business-summary.md").read_text(encoding="utf-8") == business_summary(report)
    frozen = np.load(output / "frozen-policies.npz")
    assert all(i.startswith("FINAL") for i in frozen["ids"])
    assert report["scenarios"]["unfavourable"]["planning"]["profit"]["selected"] == 0
    with pytest.raises(FileExistsError):
        workflow.run_stage3(spark, cohort, models, source, Path("configs/economics.toml"), output)


def test_decimal_budget_does_not_lose_a_feasible_contact():
    _, p = build_policies(
        np.array(list("abc")), [1, 1, 1], [0.2, 0.2, 0.2], [10, 10, 10], 0.1, 0.3, 3
    )
    assert p["profit"]["selected"] == 3
    assert p["profit"]["spend_gbp"] == 0.3


def test_power_reference_using_independent_normal_quantiles():
    # Hand evaluation with tabulated z(.975)=1.959963985 and z(.8)=.841621234.
    # p0=.6, p1=.63, r=2, so pooled=.62; A=.3534, B=.35655.
    reference = ((1.959963985 * 0.3534**0.5 + 0.841621234 * 0.35655**0.5) / 0.03) ** 2
    assert sample_size(0.6, 0.03, ratio=2)["raw_control"] == pytest.approx(reference, rel=1e-8)
