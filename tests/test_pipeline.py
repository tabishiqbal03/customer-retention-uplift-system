import json

import pyarrow.parquet as pq
import pytest

from retention_uplift.config import Config
from retention_uplift.pipeline import run
from retention_uplift.storage import write_table

pytestmark = pytest.mark.integration


def test_end_to_end_parquet_smoke_and_no_overwrite(spark, tmp_path):
    output = tmp_path / "smoke"
    report = run(spark, Config(customers=32, partitions=2), output, writer="portable")
    assert report["row_counts"]["features"] == 32
    assert report["parquet_readback"] == "passed"
    assert (output / "_SUCCESS").exists()
    assert json.loads((output / "validation.json").read_text())["config"]["seed"] == 20261019
    with pytest.raises(FileExistsError):
        run(spark, Config(), output)


def test_portable_writer_crosses_batch_and_file_boundaries(spark, tmp_path):
    # Actual I/O across 8,192 row groups and 65,536 row file rotation, no mocked sink.
    output = tmp_path / "rotated"
    write_table(spark.range(65539, numPartitions=4), output, "portable")
    files = sorted(output.glob("*.parquet"))
    assert len(files) == 2
    assert sum(pq.ParquetFile(p).metadata.num_rows for p in files) == 65539
    with pytest.raises(FileExistsError):
        write_table(spark.range(1), output, "portable")


def test_empty_parquet_schema(spark, tmp_path):
    output = tmp_path / "empty"
    write_table(spark.range(0), output, "portable")
    file = next(output.glob("*.parquet"))
    assert pq.ParquetFile(file).metadata.num_rows == 0
