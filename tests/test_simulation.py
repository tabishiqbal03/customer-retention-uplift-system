import math
from dataclasses import replace

import pytest
from pyspark.sql import functions as F

from retention_uplift.config import Config
from retention_uplift.pipeline import build_tables
from retention_uplift.simulator import assign_treatment, generate_outcomes
from retention_uplift.validation import validate_tables

pytestmark = pytest.mark.integration


def test_quality_and_randomized_diagnostics(generated):
    config, tables = generated
    result = validate_tables(tables, config)
    assert result["structural_validation"] == "passed"
    assert result["row_counts"]["customers"] == 1000
    assert result["row_counts"]["transactions"] > 1000
    assert result["row_counts"]["features"] == 1000
    assert abs(result["allocation_z"]) < 4
    assert all(abs(v["z"]) < 4 for v in result["covariate_balance"].values())
    assert result["positive_share"] > 0.15 and result["negative_share"] > 0.10
    assert result["near_zero_share"] > 0.01
    assert abs(result["ate_discrepancy"]) < 4 * result["difference_standard_error"]


def test_probability_formula_matches_independent_calculation(generated):
    config, tables = generated
    m = config.mechanism
    for r in tables["truth"].orderBy("customer_id").limit(10).collect():
        logit = (
            m.baseline_intercept
            + m.engagement_weight * r.engagement
            + m.trend_weight * r.trend
            + m.savings_weight * r.has_savings
            + m.latent_noise * r.residual
        )
        delta = (
            m.benefit_strength
            * 4
            * r.engagement
            * (1 - r.engagement)
            / (1 + math.exp(3 * r.trend))
            * r.sensitivity
            - m.harm_strength * r.aversion
        )
        assert r.p0 == pytest.approx(1 / (1 + math.exp(-logit)))
        assert r.p1 == pytest.approx(1 / (1 + math.exp(-logit - delta)))
        assert r.tau == pytest.approx(r.p1 - r.p0)


def test_reproducible_across_partition_counts(spark):
    config = Config(customers=24, partitions=1)
    first = build_tables(spark, config)
    second = build_tables(spark, replace(config, partitions=3))
    try:
        for name in first:
            assert first[name].exceptAll(second[name]).count() == 0, name
            assert second[name].exceptAll(first[name]).count() == 0, name
    finally:
        for frame in [*first.values(), *second.values()]:
            frame.unpersist()


def test_assignment_ignores_covariates_and_changes_with_seed(generated):
    config, tables = generated
    changed = tables["customers"].withColumn("tenure_days", F.lit(999999))
    same = assign_treatment(changed.repartition(3), config)
    assert same.exceptAll(tables["assignments"]).count() == 0
    different = assign_treatment(changed, replace(config, seed=config.seed + 1))
    assert different.exceptAll(same).count() > 100


def test_outcomes_use_assigned_probability_and_activity_definition(generated):
    config, tables = generated
    truth = tables["truth"].withColumns({"p0": F.lit(0.0), "p1": F.lit(1.0)})
    outcomes = generate_outcomes(tables["assignments"], truth, config)
    joined = outcomes.join(tables["assignments"], "customer_id")
    assert joined.where(F.col("retained") != F.col("treatment")).count() == 0
    assert (
        joined.where(
            F.col("retained") != (F.col("qualifying_activity_days") > 0).cast("int")
        ).count()
        == 0
    )
    assert set(outcomes.columns) == {
        "customer_id",
        "qualifying_activity_days",
        "retained",
        "outcome_start",
        "outcome_end",
    }


def test_validator_rejects_corrupted_data(generated):
    config, tables = generated
    broken = dict(tables)
    broken["transactions"] = tables["transactions"].withColumns(
        {
            "event_date": F.lit("2026-02-01").cast("date"),
            "amount_pence": F.lit(-1).cast("long"),
            "customer_id": F.lit("ORPHAN"),
            "transaction_id": F.lit("DUPLICATE"),
        }
    )
    broken["outcomes"] = tables["outcomes"].withColumn("retained", F.lit(2))
    broken["truth"] = tables["truth"].withColumn("p0", F.lit(2.0))
    with pytest.raises(ValueError) as error:
        validate_tables(broken, config)
    for message in ("duplicate", "orphan", "transaction dates", "Invalid outcome", "ground-truth"):
        assert message in str(error.value)


def test_validator_rejects_feature_leakage_column(generated):
    config, tables = generated
    broken = dict(tables)
    broken["features"] = tables["features"].withColumn("tau", F.lit(0.1))
    with pytest.raises(ValueError, match="Unexpected columns in features"):
        validate_tables(broken, config)
