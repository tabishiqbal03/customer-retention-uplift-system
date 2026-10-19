"""Conservative local Spark session defaults."""

import os

from pyspark.sql import SparkSession

from retention_uplift.config import Config


def session(config: Config) -> SparkSession:
    if config.master.startswith("local"):
        os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    spark = (
        SparkSession.builder.master(config.master)
        .appName("retention-stage-1")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", str(config.partitions))
        .config("spark.ui.enabled", "false")
        .config("spark.sql.adaptive.enabled", "false")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    return spark
