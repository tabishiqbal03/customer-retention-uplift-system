"""Analytical, leakage, repeatability and real Spark integration checks for Stage 2."""

import json
from dataclasses import replace

import numpy as np
import pytest
from pyspark.sql import functions as F

from retention_uplift.features import MODEL_FEATURES
from retention_uplift.modelling_data import Observations, build_observations, split_customers
from retention_uplift.models import UpliftModel, select_models
from retention_uplift.policy import (
    bootstrap_means,
    evaluate_policies,
    gain_curve,
    ipw_signal,
    make_policies,
    ranking,
)


@pytest.fixture
def observations():
    rng = np.random.default_rng(72)
    n = 600
    x = rng.normal(size=(n, len(MODEL_FEATURES)))
    t = rng.integers(0, 2, n).astype(float)
    y = (rng.random(n) < (0.3 + 0.2 * (x[:, 0] > 0) + 0.15 * t)).astype(float)
    return Observations(np.array([f"C{i}" for i in range(n)]), x, t, y, np.full(n, 0.5))


def test_split_disjoint_complete_reorder_and_outcome_invariant(observations):
    d = observations
    split = split_customers(d)
    assert set(split) == {"train", "validation", "test"}
    assert (split == "train").sum() in (359, 360)
    assert np.array_equal(split, split_customers(replace(d, outcome=1 - d.outcome)))
    order = np.arange(len(d.ids))[::-1]
    assert np.array_equal(split[order], split_customers(d.subset(order)))
    assert not np.array_equal(split, split_customers(d, seed=9))
    for name in set(split):
        assert set(d.treatment[split == name]) == {0, 1}


@pytest.mark.parametrize(
    "field,value",
    [
        ("x", np.zeros((600, 23))),
        ("x", np.full((600, 22), np.nan)),
        ("treatment", np.full(600, 2)),
        ("outcome", np.full(600, -1)),
        ("propensity", np.zeros(600)),
        ("ids", np.full(600, "duplicate")),
    ],
)
def test_invalid_observations(observations, field, value):
    with pytest.raises(ValueError):
        replace(observations, **{field: value})


@pytest.mark.parametrize("kind", ["constant", "t", "s"])
def test_model_shapes_probabilities_and_reproducibility(observations, kind):
    a = UpliftModel(kind, iterations=10).fit(observations)
    b = UpliftModel(kind, iterations=10).fit(observations)
    pred = a.predict(observations.x[:10])
    assert pred.shape == (10,)
    np.testing.assert_array_equal(pred, b.predict(observations.x[:10]))
    if kind != "constant":
        p0, p1 = a.potential_outcomes(observations.x[:10])
        assert ((p0 >= 0) & (p0 <= 1) & (p1 >= 0) & (p1 <= 1)).all()
        np.testing.assert_allclose(pred, p1 - p0)


def test_counterfactual_mechanics_and_arm_training(observations):
    class FakeOutcome:
        def __init__(self, probability):
            self.probability = probability

        def predict_proba(self, x):
            p = (
                np.full(len(x), self.probability)
                if self.probability is not None
                else 0.2 + 0.5 * x[:, -1]
            )
            return np.column_stack((1 - p, p))

    t = UpliftModel("t")
    t.arms_ = [FakeOutcome(0.7), FakeOutcome(0.4)]
    np.testing.assert_allclose(t.predict(observations.x), -0.3)
    s = UpliftModel("s")
    s.model_ = FakeOutcome(None)
    np.testing.assert_allclose(s.predict(observations.x), 0.5)
    fitted = UpliftModel("t", iterations=5).fit(observations)
    for arm in (0, 1):
        # HGB initializes its intercept at the observed arm's log odds.
        mean = observations.outcome[observations.treatment == arm].mean()
        np.testing.assert_allclose(
            fitted.arms_[arm]._baseline_prediction, np.log(mean / (1 - mean))
        )


def test_preprocessing_uses_training_controls_only(observations):
    train, validation = (
        observations.subset(np.arange(400)),
        observations.subset(np.arange(400, 600)),
    )
    validation = replace(validation, x=validation.x + 1000)
    _, risk, _, _ = select_models(train, validation, iterations=5)
    np.testing.assert_allclose(risk[0].mean_, train.x[train.treatment == 0].mean(axis=0))
    assert risk[0].n_samples_seen_ == (train.treatment == 0).sum()


def test_constant_uses_training_ipw(observations):
    model = UpliftModel("constant").fit(observations)
    expected = np.mean(
        2 * observations.treatment * observations.outcome
        - 2 * (1 - observations.treatment) * observations.outcome
    )
    assert model.effect_ == pytest.approx(expected)


def test_selection_rejects_overlapping_customers(observations):
    with pytest.raises(ValueError, match="disjoint"):
        select_models(observations, observations, iterations=5)


def test_ipw_expectation_equals_oracle_policy_increment():
    # Enumerate every (T,Y) event at each x with its true probability.
    p0, p1, e = 0.3, 0.7, 0.2
    t, y = np.array([0, 0, 1, 1]), np.array([0, 1, 0, 1])
    weights = np.array([(1 - e) * (1 - p0), (1 - e) * p0, e * (1 - p1), e * p1])
    z = ipw_signal(t, y, np.full(4, e))
    assert np.dot(weights, z) == pytest.approx(p1 - p0)
    assert np.dot(weights, np.zeros(4) * z) == 0


def test_analytical_ipw_nonhalf_propensity_and_policy(observations):
    t = np.array([1.0, 0.0, 1.0, 0.0])
    y = np.array([1.0, 1.0, 0.0, 0.0])
    e = np.full(4, 0.25)
    np.testing.assert_allclose(ipw_signal(t, y, e), [4, -4 / 3, 0, 0])
    d = Observations(np.array(list("abcd")), observations.x[:4], t, y, e)
    result = evaluate_policies(d, {"offer": np.array([1, 0, 0, 0]), "none": np.zeros(4)}, 100)
    assert result["policies"]["offer"]["estimate"] == 1
    assert result["ate"]["estimate"] == pytest.approx(2 / 3)
    assert result["policies"]["none"]["ci95"] == [0, 0]


def test_budgets_positive_cap_ties_and_reordering(observations):
    ids = observations.ids[:20]
    risk = np.arange(20.0)
    uplift = np.r_[np.full(3, 0.1), np.full(17, -0.1)]
    policies = make_policies(ids, risk, uplift, fractions=(0.1, 0.5))
    for name in ("random", "churn", "uplift"):
        assert policies[name + "@0.1"].sum() == 2
        assert policies[name + "@0.5"].sum() == 3
    assert np.all(uplift[policies["uplift@0.5"].astype(bool)] > 0)
    reverse = make_policies(ids[::-1], risk[::-1], uplift[::-1], fractions=(0.1, 0.5))
    for name in policies:
        np.testing.assert_array_equal(policies[name][::-1], reverse[name])
    np.testing.assert_array_equal(ranking(ids, np.zeros(20)), ranking(ids, np.zeros(20)))
    assert all(v.sum() == 0 for v in make_policies(ids, risk, -np.ones(20)).values())


def test_paired_bootstrap_preserves_covariance():
    values = np.column_stack((np.arange(10), np.arange(10), np.zeros(10)))
    a = bootstrap_means(values, 100)
    np.testing.assert_array_equal(a[:, 0], a[:, 1])
    np.testing.assert_array_equal(a, bootstrap_means(values, 100))
    assert (a[:, 2] == 0).all()


def test_gain_curve_analytical():
    result = gain_curve(np.array(["a", "b"]), np.array([1.0, 0.0]), np.array([2.0, -2.0]))
    assert result["gain"] == [0.0, 1.0, 0.0]
    assert result["qini_area"] == pytest.approx(0.5)


@pytest.mark.integration
def test_spark_bridge_allowlist_and_key_integrity(generated):
    _, t = generated
    original = build_observations(t["features"], t["assignments"], t["outcomes"])
    contaminated = t["features"].withColumns(
        {k: F.lit(999) for k in ("tau", "p0", "p1", "treatment", "retained", "future_activity")}
    )
    clean = build_observations(contaminated, t["assignments"], t["outcomes"])
    np.testing.assert_array_equal(original.x, clean.x)
    assert original.x.shape == (1000, 22)
    for bad in (t["outcomes"].limit(999), t["outcomes"].unionByName(t["outcomes"].limit(1))):
        with pytest.raises(ValueError, match="keys"):
            build_observations(t["features"], t["assignments"], bad)
    with pytest.raises(ValueError, match="bound"):
        build_observations(t["features"], t["assignments"], t["outcomes"], max_customers=500)


@pytest.mark.integration
def test_stage2_full_workflow(spark, tmp_path, monkeypatch):
    import retention_uplift.stage2 as workflow
    from retention_uplift.config import Config
    from retention_uplift.pipeline import run
    from retention_uplift.stage2 import run_stage2

    source, output = tmp_path / "source", tmp_path / "models"
    run(spark, Config(customers=160, partitions=2), source, "portable")
    actual_loader = workflow.load_test_truth

    def guarded_loader(*args):
        assert (output / "selection.json").exists()
        assert (output / "test-predictions.npz").exists()
        return actual_loader(*args)

    monkeypatch.setattr(workflow, "load_test_truth", guarded_loader)
    report = run_stage2(spark, source, output, replications=100, iterations=5)
    assert report["n_customers"] == 160
    assert sum(v["n"] for v in report["splits"].values()) == 160
    assert (output / "_SUCCESS").exists()
    assert len(list(output.glob("*.png"))) == 4
    assert json.loads((output / "metrics.json").read_text()) == report
    summary = (output / "summary.md").read_text(encoding="utf-8")
    for name, result in report["observed"]["policies"].items():
        assert f"| {name} | {result['targeted']} | {100 * result['estimate']:.3f} |" in summary
    assert f"**{report['selection']['selected_uplift']}**" in summary
    with pytest.raises(FileExistsError):
        run_stage2(spark, source, output)
