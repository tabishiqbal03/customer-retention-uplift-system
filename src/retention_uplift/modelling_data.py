"""Bounded customer data bridge. This module never reads evaluation-only truth."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pyspark.sql import functions as F
from pyspark.sql.types import StructType

from retention_uplift.features import MODEL_FEATURES, model_inputs
from retention_uplift.storage import LAYOUT


@dataclass(frozen=True)
class Observations:
    ids: np.ndarray
    x: np.ndarray
    treatment: np.ndarray
    outcome: np.ndarray
    propensity: np.ndarray

    def __post_init__(self):
        n = len(self.ids)
        if n == 0 or len(set(self.ids)) != n or any(not str(i) for i in self.ids):
            raise ValueError("Customer IDs must be nonempty and unique")
        if self.x.shape != (n, len(MODEL_FEATURES)) or not np.isfinite(self.x).all():
            raise ValueError("Expected finite allowlisted feature matrix")
        for a in (self.treatment, self.outcome, self.propensity):
            if a.shape != (n,) or not np.isfinite(a).all():
                raise ValueError("Invalid observation shape or values")
        if not np.isin(self.treatment, [0, 1]).all() or not np.isin(self.outcome, [0, 1]).all():
            raise ValueError("Treatment and outcome must be binary")
        if not ((self.propensity > 0) & (self.propensity < 1)).all():
            raise ValueError("Propensity must be strictly between zero and one")

    def subset(self, index):
        return Observations(*(getattr(self, k)[index] for k in self.__dataclass_fields__))


def read_frame(spark, root: Path, name: str):
    folder = root / LAYOUT[name]
    schema = StructType.fromJson(json.loads((folder / "_schema.json").read_text()))
    return spark.read.schema(schema).parquet(
        *[p.resolve().as_uri() for p in sorted(folder.glob("*.parquet"))]
    )


def build_observations(features, assignments, outcomes, max_customers=120000):
    """Validate keys before joining and bound collection before transferring any rows."""
    n = features.count()
    if not 30 <= n <= max_customers:
        raise ValueError("Customer count outside configured collection bound [30, max]")
    for frame in (features, assignments, outcomes):
        summary = frame.agg(
            F.count("*").alias("n"), F.countDistinct("customer_id").alias("u")
        ).first()
        if summary.n != n or summary.u != n:
            raise ValueError("Customer keys must be unique, non-null and have matching coverage")
        if (
            features.select("customer_id")
            .join(frame.select("customer_id"), "customer_id", "left_anti")
            .limit(1)
            .count()
        ):
            raise ValueError("Customer key coverage mismatch")
    # Reuse the Stage 1 allowlist, preserving ID solely for joining/splitting.
    xnames = model_inputs(features).columns
    joined = (
        features.select("customer_id", *xnames)
        .join(assignments.select("customer_id", "treatment", "propensity"), "customer_id")
        .join(outcomes.select("customer_id", "retained"), "customer_id")
    )
    rows = joined.orderBy("customer_id").collect()
    return Observations(
        np.array([r.customer_id for r in rows]),
        np.array([[r[c] for c in MODEL_FEATURES] for r in rows], dtype=float),
        np.array([r.treatment for r in rows], dtype=float),
        np.array([r.retained for r in rows], dtype=float),
        np.array([r.propensity for r in rows], dtype=float),
    )


def load_observations(spark, root: Path, max_customers=120000):
    if not (root / "_SUCCESS").exists():
        raise ValueError("Stage 1 success manifest required")
    return build_observations(
        *(read_frame(spark, root, k) for k in ("features", "assignments", "outcomes")),
        max_customers=max_customers,
    )


def hash_keys(ids, seed, domain):
    return np.array([hashlib.sha256(f"{seed}|{domain}|{i}".encode()).hexdigest() for i in ids])


def split_customers(data: Observations, seed=20261020):
    """60/20/20 within original arm; independent of outcomes and input ordering."""
    membership = np.full(len(data.ids), "", dtype="U10")
    for arm in (0, 1):
        ix = np.flatnonzero(data.treatment == arm)
        if len(ix) < 10:
            raise ValueError("Need at least ten customers per randomized arm")
        ix = ix[np.argsort(hash_keys(data.ids[ix], seed, "split"))]
        a, b = int(0.6 * len(ix)), int(0.8 * len(ix))
        membership[ix[:a]], membership[ix[a:b]], membership[ix[b:]] = "train", "validation", "test"
    return membership
