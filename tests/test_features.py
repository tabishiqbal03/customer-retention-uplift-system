from datetime import date

import pytest
from pyspark.sql import functions as F

from retention_uplift.config import Config
from retention_uplift.features import MODEL_FEATURES, build_features, model_inputs

pytestmark = pytest.mark.integration


@pytest.fixture
def sources(spark):
    customers = spark.sql("""
        SELECT * FROM VALUES ('A', 400, DATE '2025-12-31'), ('B', 700, DATE '2025-12-31')
        AS c(customer_id, tenure_days, snapshot_date)
    """)
    transactions = spark.sql("""
        SELECT * FROM VALUES
          ('A', 't1', DATE '2025-01-01', 'card', 'groceries', 10000L, 'GBP'),
          ('A', 't2', DATE '2025-11-30', 'transfer', 'transfer', 20000L, 'GBP'),
          ('A', 't3', DATE '2025-12-02', 'card', 'leisure', 30000L, 'GBP'),
          ('A', 't4', DATE '2025-12-31', 'savings', 'savings', 40000L, 'GBP')
        AS t(customer_id, transaction_id, event_date, product, category, amount_pence, currency)
    """)
    return customers, transactions


def equal_rows(a, b):
    assert a.schema == b.schema
    assert a.exceptAll(b).count() == 0
    assert b.exceptAll(a).count() == 0


def test_hand_calculated_aggregation_and_empty_customer(sources):
    features = build_features(*sources, Config())
    rows = {r.customer_id: r for r in features.collect()}  # Exactly two fixture customers.
    a, b = rows["A"], rows["B"]
    assert a.transaction_count == 4
    assert a.card_spend_gbp == 400.0
    assert a.mean_transaction_gbp == 250.0
    assert a.transaction_stddev_gbp == pytest.approx(111.803398875)
    assert a.active_months == 3 and a.recency_days == 0
    assert a.transactions_30d == 2 and a.transactions_90d == 3
    assert a.transactions_previous_30d == 1 and a.activity_change_30d == 1
    assert a.card_spend_30d_gbp == 300.0 and a.card_spend_90d_gbp == 300.0
    assert a.card_count == 2 and a.savings_count == 1 and a.transfer_count == 1
    assert a.products_used == 3 and a.card_share == 0.5 and a.groceries_share == 0.25
    assert a.monthly_frequency == pytest.approx(4 / 12)
    assert b.transaction_count == 0 and b.recency_days == 365
    assert b.mean_transaction_gbp == 0 and b.card_share == 0 and b.products_used == 0
    assert all(value is not None for value in b)
    assert a.feature_cutoff == date(2025, 12, 31)
    assert tuple(model_inputs(features).columns) == MODEL_FEATURES


def test_future_and_pre_history_events_cannot_change_features(sources):
    customers, tx = sources
    original = build_features(customers, tx, Config())
    for day in ("2026-01-01", "2026-01-31", "2024-12-31"):
        injected = (
            tx.limit(1)
            .withColumn("event_date", F.lit(day).cast("date"))
            .withColumn("amount_pence", F.lit(999999999).cast("long"))
        )
        equal_rows(original, build_features(customers, tx.unionByName(injected), Config()))


def test_labels_treatment_and_latents_cannot_change_features(sources):
    customers, tx = sources
    original = build_features(customers, tx, Config())
    forbidden = (
        "retained",
        "treatment",
        "p0",
        "p1",
        "tau",
        "archetype",
        "engagement",
        "future_spend",
    )
    contaminated_customers = customers.withColumns({key: F.lit(999) for key in forbidden})
    contaminated_tx = tx.withColumns({key: F.lit(-999) for key in forbidden})
    contaminated = build_features(contaminated_customers, contaminated_tx, Config())
    equal_rows(original, contaminated)
    assert set(forbidden).isdisjoint(contaminated.columns)


def test_duplicate_customers_and_future_snapshots_rejected(sources):
    customers, tx = sources
    with pytest.raises(ValueError, match="unique"):
        build_features(customers.unionByName(customers), tx, Config())
    with pytest.raises(ValueError, match="snapshot"):
        build_features(
            customers.withColumn("snapshot_date", F.lit("2026-01-01").cast("date")), tx, Config()
        )
