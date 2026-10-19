"""Historical-only feature interface. No dependency on simulator or experiment tables."""

from datetime import date, timedelta

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from retention_uplift.config import Config

MODEL_FEATURES = (
    "tenure_days",
    "transaction_count",
    "monthly_frequency",
    "card_spend_gbp",
    "mean_transaction_gbp",
    "transaction_stddev_gbp",
    "active_months",
    "recency_days",
    "transactions_30d",
    "transactions_90d",
    "transactions_previous_30d",
    "activity_change_30d",
    "card_spend_30d_gbp",
    "card_spend_90d_gbp",
    "card_count",
    "savings_count",
    "transfer_count",
    "products_used",
    "card_share",
    "groceries_share",
    "transport_share",
    "leisure_share",
)
CUSTOMER_COLUMNS = ("customer_id", "tenure_days", "snapshot_date")
TRANSACTION_COLUMNS = (
    "customer_id",
    "transaction_id",
    "event_date",
    "product",
    "category",
    "amount_pence",
    "currency",
)


def build_features(customers: DataFrame, transactions: DataFrame, config: Config) -> DataFrame:
    """One row per customer, only selected source columns and dates inside history.

    Validate customer keys before joining; projection discards even adversarially
    supplied outcome/latent/treatment columns. Raw-data integrity is checked separately
    by validate_tables, so a contaminated source is flagged as well as filtered here.
    """
    customers = customers.select(*CUSTOMER_COLUMNS)
    bad = customers.agg(
        F.count("*").alias("n"),
        F.countDistinct("customer_id").alias("unique"),
        F.count(
            F.when(
                F.col("snapshot_date").isNull()
                | (F.col("snapshot_date") != F.lit(config.cutoff))
                | F.col("tenure_days").isNull()
                | (F.col("tenure_days") < 0),
                1,
            )
        ).alias("invalid"),
    ).first()
    if bad.n != bad.unique or bad.invalid:
        raise ValueError("Customer keys must be unique/non-null and snapshot must equal cutoff")
    assignment = date.fromisoformat(config.assignment_date)
    tx = transactions.select(*TRANSACTION_COLUMNS).where(
        (F.col("event_date") >= F.lit(config.history_start).cast("date"))
        & (F.col("event_date") <= F.lit(config.cutoff))
    )
    recent30 = F.col("event_date") >= F.lit(assignment - timedelta(days=30))
    recent90 = F.col("event_date") >= F.lit(assignment - timedelta(days=90))
    previous30 = (F.col("event_date") >= F.lit(assignment - timedelta(days=60))) & ~recent30
    card = F.col("product") == "card"

    def count_if(condition):
        return F.sum(F.when(condition, 1).otherwise(0)).cast("long")

    agg = tx.groupBy("customer_id").agg(
        F.count("*").alias("transaction_count"),
        F.sum(F.when(card, F.col("amount_pence")).otherwise(0)).alias("card_spend_pence"),
        F.sum("amount_pence").alias("sum_amount_pence"),
        F.sum(F.col("amount_pence") * F.col("amount_pence")).alias("sum_squared_pence"),
        F.countDistinct(F.date_format("event_date", "yyyy-MM")).alias("active_months"),
        F.max("event_date").alias("last_event_date"),
        count_if(recent30).alias("transactions_30d"),
        count_if(recent90).alias("transactions_90d"),
        count_if(previous30).alias("transactions_previous_30d"),
        F.sum(F.when(card & recent30, F.col("amount_pence")).otherwise(0)).alias("spend30_pence"),
        F.sum(F.when(card & recent90, F.col("amount_pence")).otherwise(0)).alias("spend90_pence"),
        *[
            count_if(F.col("product") == product).alias(product + "_count")
            for product in ("card", "savings", "transfer")
        ],
        *[
            count_if(F.col("category") == category).alias(category + "_count")
            for category in ("groceries", "transport", "leisure")
        ],
    )
    frame = customers.join(agg, "customer_id", "left").fillna(0)
    denominator = F.greatest(F.col("transaction_count"), F.lit(1))
    frame = frame.withColumns(
        {
            "monthly_frequency": F.col("transaction_count") / config.months,
            "card_spend_gbp": F.col("card_spend_pence") / 100,
            "mean_transaction_gbp": F.col("sum_amount_pence") / denominator / 100,
            # Integer moments are associative. Generator bounds keep sums below 2^53.
            "transaction_stddev_gbp": F.sqrt(
                F.greatest(
                    F.lit(0.0),
                    F.col("sum_squared_pence") / denominator
                    - F.pow(F.col("sum_amount_pence") / denominator, 2),
                )
            )
            / 100,
            "recency_days": F.coalesce(
                F.datediff(F.lit(config.cutoff), "last_event_date"), F.lit(config.history_days)
            ),
            "activity_change_30d": F.col("transactions_30d") - F.col("transactions_previous_30d"),
            "card_spend_30d_gbp": F.col("spend30_pence") / 100,
            "card_spend_90d_gbp": F.col("spend90_pence") / 100,
            "products_used": sum(
                (F.col(p + "_count") > 0).cast("int") for p in ("card", "savings", "transfer")
            ),
            **{
                c + "_share": F.col(c + "_count") / denominator
                for c in ("card", "groceries", "transport", "leisure")
            },
            "feature_cutoff": F.lit(config.cutoff),
        }
    )
    return frame.select("customer_id", *MODEL_FEATURES, "feature_cutoff")


def model_inputs(features: DataFrame) -> DataFrame:
    """Future modelling entry point: explicit predictor allowlist, no IDs or dates."""
    return features.select(*MODEL_FEATURES)
