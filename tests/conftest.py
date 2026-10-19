import pytest

from retention_uplift.config import Config
from retention_uplift.pipeline import build_tables
from retention_uplift.spark import session


@pytest.fixture(scope="session")
def spark():
    instance = session(Config(partitions=2))
    yield instance
    instance.stop()


@pytest.fixture(scope="session")
def generated(spark):
    config = Config(customers=1000, partitions=4)
    tables = build_tables(spark, config)
    yield config, tables
    for frame in tables.values():
        frame.unpersist()
