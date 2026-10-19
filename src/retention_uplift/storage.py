"""Parquet persistence, including a bounded Windows writer without Hadoop binaries."""

import json
import os
from itertools import islice
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StructType

LAYOUT = {
    "customers": "raw/customers",
    "transactions": "raw/transactions",
    "features": "processed/features",
    "assignments": "experiment/assignments",
    "outcomes": "experiment/outcomes",
    "truth": "evaluation_only/truth",
}


def write_table(frame: DataFrame, destination: Path, writer: str = "auto") -> str:
    """Write new paths only. Portable writes stream partitions, never the full dataset.

    toLocalIterator uses memory proportional to the largest Spark partition. The
    additional Python/Arrow conversion buffer is capped at 8,192 rows; each file has
    at most 65,536 rows. This serial sink is a local compatibility path, not the
    intended distributed 10M+ row production sink. Spark transformations stay distributed.
    """
    if writer == "auto":
        writer = "portable" if os.name == "nt" else "spark"
    if writer not in {"portable", "spark"}:
        raise ValueError("writer must be auto, portable or spark")
    if destination.exists():
        raise FileExistsError(destination)
    if writer == "spark":
        frame.write.mode("error").parquet(destination.resolve().as_uri())
    else:
        destination.mkdir(parents=True)
        types = {
            "string": pa.string(),
            "int": pa.int32(),
            "bigint": pa.int64(),
            "double": pa.float64(),
            "date": pa.date32(),
            "boolean": pa.bool_(),
        }
        schema = pa.schema([pa.field(c, types[t]) for c, t in frame.dtypes])
        rows = frame.toLocalIterator(prefetchPartitions=False)
        index = 0
        while True:
            batch = list(islice(rows, 8192))
            if not batch:
                if index == 0:
                    pq.write_table(
                        pa.Table.from_pylist([], schema=schema), destination / "part-00000.parquet"
                    )
                break
            with pq.ParquetWriter(
                destination / f"part-{index:05d}.parquet", schema, compression="snappy"
            ) as sink:
                for _ in range(8):
                    sink.write_table(
                        pa.Table.from_pylist([r.asDict() for r in batch], schema=schema)
                    )
                    batch = list(islice(rows, 8192)) if _ < 7 else None
                    if batch == []:
                        break
            index += 1
            if batch == []:
                break
    (destination / "_schema.json").write_text(frame.schema.json(), encoding="utf-8")
    return writer


def read_tables(spark: SparkSession, root: Path) -> dict[str, DataFrame]:
    result = {}
    for name, relative in LAYOUT.items():
        folder = root / relative
        schema = StructType.fromJson(
            json.loads((folder / "_schema.json").read_text(encoding="utf-8"))
        )
        # Explicit paths avoid platform-dependent wildcard/directory discovery.
        files = [p.resolve().as_uri() for p in sorted(folder.glob("*.parquet"))]
        if not files:
            raise ValueError(f"No Parquet files in {folder}")
        result[name] = spark.read.schema(schema).parquet(*files)
    return result
