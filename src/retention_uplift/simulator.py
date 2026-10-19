"""Evaluation-only latent simulator. Never import this module into a modelling pipeline."""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from retention_uplift.config import Config
from retention_uplift.randomness import clip, normal, sigmoid, uniform

# Equal-weight overlapping mixtures: engagement, trend, price sensitivity, message aversion.
ARCHETYPES = {
    "stable": (0.80, 0.03, 0.15, 0.05),
    "drifting": (0.60, -0.55, 0.85, 0.05),
    "low_engagement": (0.18, -0.10, 0.12, 0.06),
    "multi_product": (0.70, 0.06, 0.25, 0.06),
    "price_sensitive": (0.48, -0.15, 0.95, 0.08),
    "message_averse": (0.55, -0.10, 0.40, 0.85),
}


def generate_latent(spark: SparkSession, config: Config) -> DataFrame:
    """Established customers only; all accounts exist throughout the historical year."""
    m, seed = config.mechanism, config.seed
    frame = spark.range(config.customers, numPartitions=config.partitions).select(
        F.format_string("C%09d", F.col("id")).alias("customer_id")
    )
    frame = frame.withColumn(
        "archetype_index", F.floor(6 * uniform(seed, "archetype", "customer_id")).cast("int")
    )
    frame = frame.withColumn(
        "archetype", F.get(F.array(*[F.lit(x) for x in ARCHETYPES]), "archetype_index")
    )
    for index, (name, noise, lower, upper) in enumerate(
        [
            ("engagement", m.engagement_noise, 0.01, 0.99),
            ("trend", m.trend_noise, -0.95, 0.70),
            ("sensitivity", m.preference_noise, 0.0, 1.0),
            ("aversion", m.preference_noise, 0.0, 1.0),
        ]
    ):
        mean = F.get(F.array(*[F.lit(v[index]) for v in ARCHETYPES.values()]), "archetype_index")
        frame = frame.withColumn(
            name, clip(mean + noise * normal(seed, name, "customer_id"), lower, upper)
        )
    frame = frame.withColumns(
        {
            "tenure_days": (
                F.lit(config.history_days) + F.floor(1800 * uniform(seed, "tenure", "customer_id"))
            ).cast("int"),
            "has_savings": (
                uniform(seed, "savings", "customer_id") < (0.15 + 0.6 * F.col("engagement"))
            ).cast("int"),
            "has_transfers": (
                uniform(seed, "transfers", "customer_id") < (0.2 + 0.5 * F.col("engagement"))
            ).cast("int"),
            "spend_scale": m.mean_spend_gbp
            * F.exp(0.5 * normal(seed, "spend-scale", "customer_id")),
            "residual": normal(seed, "retention-residual", "customer_id"),
            "inactive": (uniform(seed, "inactive", "customer_id") < 0.04).cast("int"),
        }
    )
    return frame.drop("archetype_index")


def public_customers(latent: DataFrame, config: Config) -> DataFrame:
    """Only observable baseline metadata; response parameters remain evaluation-only."""
    return latent.select("customer_id", "tenure_days").withColumn(
        "snapshot_date", F.lit(config.cutoff)
    )


def generate_transactions(latent: DataFrame, config: Config) -> DataFrame:
    """Explode bounded customer-month counts in Spark; no Python transaction collection."""
    seed, m = config.seed, config.mechanism
    monthly = latent.withColumn("month_index", F.explode(F.sequence(F.lit(0), F.lit(11))))
    monthly = monthly.withColumn(
        "month_start", F.add_months(F.lit(config.history_start).cast("date"), F.col("month_index"))
    )
    rate = (
        m.monthly_rate
        * (0.1 + F.col("engagement"))
        * F.exp(F.col("trend") * F.col("month_index") / 11)
        * (0.35 + 1.3 * uniform(seed, "monthly-noise", "customer_id", "month_index"))
        * F.when(F.month("month_start").isin(11, 12), 1.15).otherwise(1.0)
    )
    monthly = monthly.withColumn(
        "n",
        F.when(F.col("inactive") == 1, 0)
        .otherwise(
            F.floor(
                clip(rate, 0, m.max_monthly_transactions)
                + uniform(seed, "count-rounding", "customer_id", "month_index")
            )
        )
        .cast("int"),
    )
    tx = monthly.where(F.col("n") > 0).withColumn(
        "slot", F.explode(F.sequence(F.lit(1), F.col("n")))
    )
    tx = tx.withColumn("transaction_id", F.concat_ws("-", "customer_id", "month_index", "slot"))
    tx = tx.withColumn(
        "event_date",
        F.date_add(
            "month_start",
            F.floor(
                uniform(seed, "event-day", "transaction_id")
                * F.dayofmonth(F.last_day("month_start"))
            ).cast("int"),
        ),
    )
    product_u = uniform(seed, "product", "transaction_id")
    tx = tx.withColumn(
        "product",
        F.when((F.col("has_savings") == 1) & (product_u < 0.15), "savings")
        .when((F.col("has_transfers") == 1) & (product_u > 0.8), "transfer")
        .otherwise("card"),
    )
    tx = tx.withColumn(
        "category",
        F.when(
            F.col("product") == "card",
            F.get(
                F.array(F.lit("groceries"), F.lit("transport"), F.lit("leisure")),
                F.floor(3 * uniform(seed, "category", "transaction_id")).cast("int"),
            ),
        ).otherwise(F.col("product")),
    )
    # Positive settled GBP outflows. Transfers/savings are not counted as card spending.
    amount = F.col("spend_scale") * F.exp(
        m.spend_log_sigma * normal(seed, "amount", "transaction_id")
    )
    amount = amount * F.when(uniform(seed, "large-event", "transaction_id") < 0.01, 8.0).otherwise(
        1.0
    )
    tx = tx.withColumn("amount_pence", F.round(clip(amount, 0.01, 10000.0) * 100).cast("long"))
    return tx.select(
        "customer_id", "transaction_id", "event_date", "product", "category", "amount_pence"
    ).withColumn("currency", F.lit("GBP"))


def generate_truth(latent: DataFrame, config: Config) -> DataFrame:
    """Probabilities conditional on full simulator state, including unobserved variation."""
    m = config.mechanism
    logit = (
        m.baseline_intercept
        + m.engagement_weight * F.col("engagement")
        + m.trend_weight * F.col("trend")
        + m.savings_weight * F.col("has_savings")
        + m.latent_noise * F.col("residual")
    )
    delta = m.benefit_strength * 4 * F.col("engagement") * (1 - F.col("engagement")) * sigmoid(
        -3 * F.col("trend")
    ) * F.col("sensitivity") - m.harm_strength * F.col("aversion")
    return latent.withColumns({"p0": sigmoid(logit), "p1": sigmoid(logit + delta)}).withColumn(
        "tau", F.col("p1") - F.col("p0")
    )


def assign_treatment(customers: DataFrame, config: Config) -> DataFrame:
    """One independent Bernoulli draw per customer, using an assignment-only hash domain."""
    return customers.select("customer_id").withColumns(
        {
            "treatment": (
                uniform(config.seed, "assignment", "customer_id") < config.treatment_probability
            ).cast("int"),
            "propensity": F.lit(config.treatment_probability),
            "assignment_date": F.lit(config.assignment_date).cast("date"),
        }
    )


def generate_outcomes(assignments: DataFrame, truth: DataFrame, config: Config) -> DataFrame:
    """Retained means >=1 qualifying activity day in (assignment date, outcome_end].

    Sample hurdle occurrence with p_T, then a positive activity-day count conditional
    on occurrence. Only the assigned arm is sampled; no binary counterfactual is stored.
    """
    frame = assignments.join(truth.select("customer_id", "p0", "p1"), "customer_id", "inner")
    probability = F.when(F.col("treatment") == 1, F.col("p1")).otherwise(F.col("p0"))
    active = uniform(config.seed, "outcome-occurrence", "customer_id") < probability
    frame = frame.withColumn(
        "qualifying_activity_days",
        F.when(
            active,
            1 + F.floor(config.outcome_days * uniform(config.seed, "outcome-days", "customer_id")),
        )
        .otherwise(0)
        .cast("int"),
    )
    return frame.select("customer_id", "qualifying_activity_days").withColumns(
        {
            "retained": (F.col("qualifying_activity_days") > 0).cast("int"),
            "outcome_start": F.date_add(F.lit(config.assignment_date).cast("date"), 1),
            "outcome_end": F.lit(config.outcome_end),
        }
    )
