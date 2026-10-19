"""Generate, persist and validate the six physically separated Stage 1 tables."""

import json
import platform
import time
from pathlib import Path

from pyspark import StorageLevel
from pyspark.sql import SparkSession

from retention_uplift.config import Config
from retention_uplift.features import build_features
from retention_uplift.simulator import (
    assign_treatment,
    generate_latent,
    generate_outcomes,
    generate_transactions,
    generate_truth,
    public_customers,
)
from retention_uplift.storage import LAYOUT, read_tables, write_table
from retention_uplift.validation import validate_tables


def build_tables(spark: SparkSession, config: Config) -> dict:
    """Persist reusable stages; caller owns unpersisting returned DataFrames."""
    truth = generate_truth(generate_latent(spark, config), config).persist(
        StorageLevel.MEMORY_AND_DISK
    )
    customers = public_customers(truth, config).persist(StorageLevel.MEMORY_AND_DISK)
    transactions = generate_transactions(truth, config).persist(StorageLevel.MEMORY_AND_DISK)
    assignments = assign_treatment(customers, config).persist(StorageLevel.MEMORY_AND_DISK)
    return {
        "customers": customers,
        "transactions": transactions,
        "features": build_features(customers, transactions, config).persist(
            StorageLevel.MEMORY_AND_DISK
        ),
        "assignments": assignments,
        "outcomes": generate_outcomes(assignments, truth, config).persist(
            StorageLevel.MEMORY_AND_DISK
        ),
        "truth": truth,
    }


def run(spark: SparkSession, config: Config, output: Path, writer: str = "auto") -> dict:
    """Refuse existing output. Success manifest is written only after disk readback checks."""
    if output.exists():
        raise FileExistsError(f"Choose a new output directory; refusing to overwrite {output}")
    started = time.perf_counter()
    output.mkdir(parents=True)
    (output / "config.json").write_text(json.dumps(config.as_dict(), indent=2), encoding="utf-8")
    tables = build_tables(spark, config)
    try:
        report = validate_tables(tables, config)
        writers = {
            name: write_table(tables[name], output / relative, writer)
            for name, relative in LAYOUT.items()
        }
        # Generation is complete. Do not retain its cache while validating disk copies.
        # Blocking release avoids overlapping two representations on small local heaps.
        for frame in tables.values():
            frame.unpersist(blocking=True)
        # Validate actual persisted data as well as generation plans.
        saved = read_tables(spark, output)
        disk_report = validate_tables(saved, config)
        if report["fingerprints"] != disk_report["fingerprints"]:
            raise ValueError("Parquet roundtrip changed table fingerprints")
        report.update(
            {
                "config": config.as_dict(),
                "python": platform.python_version(),
                "platform": platform.platform(),
                "spark": spark.version,
                "java": spark.sparkContext._jvm.java.lang.System.getProperty("java.version"),
                "writers": writers,
                "parquet_readback": "passed",
                "elapsed_seconds": time.perf_counter() - started,
                "parquet_bytes": sum(p.stat().st_size for p in output.rglob("*.parquet")),
                "schemas": {name: frame.schema.simpleString() for name, frame in tables.items()},
            }
        )
        (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (output / "_SUCCESS").write_text(
            "All six tables validated, including Parquet readback.\n", encoding="utf-8"
        )
        return report
    finally:
        for frame in tables.values():
            frame.unpersist()
