"""Structural validation and explicitly non-exact randomized-experiment diagnostics."""

import math
from functools import reduce

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from retention_uplift.config import Config
from retention_uplift.features import CUSTOMER_COLUMNS, MODEL_FEATURES, TRANSACTION_COLUMNS

TABLE_COLUMNS = {
    "customers": set(CUSTOMER_COLUMNS),
    "transactions": set(TRANSACTION_COLUMNS),
    "features": {"customer_id", "feature_cutoff", *MODEL_FEATURES},
    "assignments": {"customer_id", "treatment", "propensity", "assignment_date"},
    "outcomes": {
        "customer_id",
        "retained",
        "qualifying_activity_days",
        "outcome_start",
        "outcome_end",
    },
    "truth": {
        "customer_id",
        "archetype",
        "engagement",
        "trend",
        "sensitivity",
        "aversion",
        "tenure_days",
        "has_savings",
        "has_transfers",
        "spend_scale",
        "residual",
        "inactive",
        "p0",
        "p1",
        "tau",
    },
}

# Contract types are checked independently of the inferred/generated schema.
STRING_FIELDS = {"customer_id", "transaction_id", "product", "category", "currency", "archetype"}
DATE_FIELDS = {
    "snapshot_date",
    "event_date",
    "feature_cutoff",
    "assignment_date",
    "outcome_start",
    "outcome_end",
}
INT_FIELDS = {
    "tenure_days",
    "recency_days",
    "products_used",
    "treatment",
    "retained",
    "qualifying_activity_days",
    "has_savings",
    "has_transfers",
    "inactive",
}
LONG_FIELDS = {
    "amount_pence",
    "transaction_count",
    "active_months",
    "transactions_30d",
    "transactions_90d",
    "transactions_previous_30d",
    "activity_change_30d",
    "card_count",
    "savings_count",
    "transfer_count",
}


def expected_type(column: str) -> str:
    for names, dtype in (
        (STRING_FIELDS, "string"),
        (DATE_FIELDS, "date"),
        (INT_FIELDS, "int"),
        (LONG_FIELDS, "bigint"),
    ):
        if column in names:
            return dtype
    return "double"


def validate_tables(tables: dict[str, DataFrame], config: Config) -> dict:
    """Fail structural corruption; report random imbalances without cherry-picking seeds.

    All driver results are single-row aggregates or two treatment-arm summaries.
    Statistical warnings use conservative four-standard-error thresholds; 95% CIs
    are descriptive and need not cover the truth for every finite simulated sample.
    """
    errors, warnings, counts = [], [], {}
    if set(tables) != set(TABLE_COLUMNS):
        raise ValueError("Expected exactly the six Stage 1 tables")
    for name, frame in tables.items():
        if set(frame.columns) != TABLE_COLUMNS[name]:
            raise ValueError(f"Unexpected columns in {name}: {frame.columns}")
        if any(dtype != expected_type(column) for column, dtype in frame.dtypes):
            raise ValueError(f"Unexpected types in {name}: {frame.dtypes}")
        key = "transaction_id" if name == "transactions" else "customer_id"
        invalid = reduce(lambda a, b: a | b, [F.col(c).isNull() for c in frame.columns])
        for col, dtype in frame.dtypes:
            if dtype in ("double", "float"):
                invalid = invalid | F.isnan(col) | (F.abs(F.col(col)) == float("inf"))
        summary = frame.agg(
            F.count("*").alias("n"),
            F.countDistinct(key).alias("unique"),
            F.count(F.when(invalid, 1)).alias("invalid"),
        ).first()
        counts[name] = summary.n
        if summary.n != summary.unique or summary.invalid:
            errors.append(f"{name}: duplicate/null keys or null/nonfinite values")
        if name != "transactions" and summary.n != config.customers:
            errors.append(f"{name}: incorrect customer count")
        if (
            name != "customers"
            and frame.select("customer_id")
            .join(tables["customers"].select("customer_id"), "customer_id", "left_anti")
            .limit(1)
            .count()
        ):
            errors.append(f"{name}: orphan customer reference")

    def reject(name: str, condition, message: str) -> None:
        if tables[name].where(condition).limit(1).count():
            errors.append(message)

    reject(
        "customers",
        (F.col("snapshot_date") != F.lit(config.cutoff))
        | (F.col("tenure_days") < config.history_days),
        "Invalid historical customer snapshot/tenure",
    )
    reject(
        "transactions",
        (F.col("event_date") < F.lit(config.history_start).cast("date"))
        | (F.col("event_date") > F.lit(config.cutoff))
        | (F.col("amount_pence") <= 0)
        | (F.col("amount_pence") > 1000000)
        | (F.col("currency") != "GBP")
        | ~F.col("product").isin("card", "savings", "transfer")
        | ~F.col("category").isin("groceries", "transport", "leisure", "savings", "transfer")
        | (
            (F.col("product") == "card")
            & ~F.col("category").isin("groceries", "transport", "leisure")
        )
        | ((F.col("product") != "card") & (F.col("category") != F.col("product"))),
        "Invalid historical transaction dates, amounts, currency or product/category",
    )
    reject(
        "assignments",
        ~F.col("treatment").isin(0, 1)
        | (F.abs(F.col("propensity") - config.treatment_probability) > 1e-12)
        | (F.col("assignment_date") != F.lit(config.assignment_date).cast("date")),
        "Invalid assignment",
    )
    reject(
        "outcomes",
        ~F.col("retained").isin(0, 1)
        | (F.col("outcome_start") != F.date_add(F.lit(config.assignment_date).cast("date"), 1))
        | (F.col("outcome_end") != F.lit(config.outcome_end))
        | (F.col("qualifying_activity_days") < 0)
        | (F.col("qualifying_activity_days") > config.outcome_days)
        | (F.col("retained") != (F.col("qualifying_activity_days") > 0).cast("int")),
        "Invalid outcome",
    )
    reject(
        "truth",
        ~F.col("p0").between(0, 1)
        | ~F.col("p1").between(0, 1)
        | ~F.col("tau").between(-1, 1)
        | (F.abs(F.col("tau") - F.col("p1") + F.col("p0")) > 1e-12),
        "Invalid ground-truth probabilities/effect",
    )
    reject(
        "features",
        (F.col("feature_cutoff") != F.lit(config.cutoff))
        | ~F.col("recency_days").between(0, config.history_days)
        | ~F.col("active_months").between(0, 12)
        | (F.col("transactions_30d") > F.col("transactions_90d"))
        | (F.col("transactions_90d") > F.col("transaction_count"))
        | (
            F.col("transaction_count")
            != F.col("card_count") + F.col("savings_count") + F.col("transfer_count")
        )
        | (F.col("card_spend_gbp") < 0),
        "Invalid feature dates/counts/amounts",
    )
    if errors:
        raise ValueError("; ".join(errors))

    experiment = (
        tables["assignments"]
        .join(tables["outcomes"], "customer_id")
        .join(tables["features"], "customer_id")
    )
    covariates = ("tenure_days", "transaction_count", "card_spend_gbp", "recency_days")
    arm_rows = (
        experiment.groupBy("treatment")
        .agg(
            F.count("*").alias("n"),
            F.avg("retained").alias("rate"),
            F.var_samp("retained").alias("outcome_variance"),
            *[
                expr
                for c in covariates
                for expr in (F.avg(c).alias(c + "_mean"), F.var_samp(c).alias(c + "_var"))
            ],
        )
        .collect()
    )  # Strictly bounded: treatment validated to {0, 1} above.
    arms = {r.treatment: r.asDict() for r in arm_rows}
    if set(arms) != {0, 1} or min(a["n"] for a in arms.values()) < 2:
        raise ValueError("Need at least two observed customers in each randomized arm")
    control, treated = arms[0], arms[1]
    fraction = treated["n"] / config.customers
    allocation_z = (fraction - config.treatment_probability) / math.sqrt(
        config.treatment_probability * (1 - config.treatment_probability) / config.customers
    )
    if abs(allocation_z) > 4:
        warnings.append("Treatment allocation exceeds four binomial standard errors")
    balance = {}
    for covariate in covariates:
        delta = treated[covariate + "_mean"] - control[covariate + "_mean"]
        var0, var1 = control[covariate + "_var"], treated[covariate + "_var"]
        se = math.sqrt(var0 / control["n"] + var1 / treated["n"])
        pooled = math.sqrt((var0 + var1) / 2)
        z = delta / se if se else 0.0
        balance[covariate] = {"standardized_difference": delta / pooled if pooled else 0.0, "z": z}
        if abs(z) > 4:
            warnings.append(f"Randomized balance warning for {covariate}: |z| > 4")
    truth = (
        tables["truth"]
        .agg(
            F.avg("tau").alias("true_ate"),
            F.min("tau").alias("tau_min"),
            F.max("tau").alias("tau_max"),
            F.avg((F.col("tau") > 0.01).cast("double")).alias("positive_share"),
            F.avg((F.abs(F.col("tau")) <= 0.01).cast("double")).alias("near_zero_share"),
            F.avg((F.col("tau") < -0.01).cast("double")).alias("negative_share"),
        )
        .first()
        .asDict()
    )
    difference = treated["rate"] - control["rate"]
    se = math.sqrt(
        treated["outcome_variance"] / treated["n"] + control["outcome_variance"] / control["n"]
    )
    discrepancy = difference - truth["true_ate"]
    if abs(discrepancy) > 4 * se:
        warnings.append("Observed difference is more than four estimated SEs from true ATE")
    fingerprints = {}
    for name, frame in tables.items():
        # Order-independent diagnostic, not a collision-free equality proof.
        row = (
            frame.select(F.xxhash64(*sorted(frame.columns)).cast("decimal(38,0)").alias("h"))
            .agg(F.sum("h"))
            .first()
        )
        fingerprints[name] = str(row[0])
    return {
        "structural_validation": "passed",
        "row_counts": counts,
        "warnings": warnings,
        "treatment_fraction": fraction,
        "allocation_z": allocation_z,
        "covariate_balance": balance,
        **truth,
        "treated_retention_rate": treated["rate"],
        "control_retention_rate": control["rate"],
        "treated_customers": treated["n"],
        "control_customers": control["n"],
        "observed_difference": difference,
        "difference_standard_error": se,
        "difference_95ci": [difference - 1.96 * se, difference + 1.96 * se],
        "ate_discrepancy": discrepancy,
        "fingerprints": fingerprints,
    }
