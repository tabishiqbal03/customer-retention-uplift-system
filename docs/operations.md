# Reproduction and environment

`pyproject.toml` pins direct dependencies: PySpark 4.2.0, PyArrow 26.0.0, pytest 9.1.1 and Ruff
0.17.1. The declared Python minimum is 3.12; the verified interpreter is 3.14.3.
Java is installed separately. These direct pins and recorded versions are not a universal
transitive lockfile. Install the src-layout package with `python -m pip install -e ".[dev]"`.
No paid service or API key is required. Stage 2/3 use NumPy and scikit-learn; optional Stage 4
inference needs a separately installed local Ollama model.

When Java is not configured, Windows CMD example (adjust to your actual installation):

```bat
set "JAVA_HOME=C:\Program Files\Java\jdk-25.0.2"
set "PATH=%JAVA_HOME%\bin;%PATH%"
java -version
python --version
python -c "import pyspark; print(pyspark.__version__)"
```

Application code has no user-specific paths. Run commands from the repository root. Use the
README's commands for the explanation demo and [pipeline reproduction](pipeline-reproduction.md)
for generation and independent validation.

## Windows storage

On the tested machine, Spark computation succeeded but native Parquet writing failed in Hadoop
permission-setting code because HADOOP_HOME/winutils was absent. No unofficial binary was fetched.
`--writer auto` chooses portable PyArrow writes on Windows and native Spark writes elsewhere.
Spark reads the resulting files back using explicit file paths. Both modes can be requested with
`--writer portable` or `--writer spark`; native Windows writing still needs working Hadoop support.

The portable sink uses `toLocalIterator(prefetchPartitions=False)`: driver memory can hold the
largest Spark partition, plus an 8,192-row conversion buffer. Files rotate at 65,536 rows. It never
collects all transactions or calls toPandas. A real 65,539-row test crosses batch/file boundaries,
and an empty-table test verifies schema persistence. This serial sink is a local compatibility
path, not a demonstrated large-scale distributed writer. No PySpark feature logic is replaced.

## Resources and scale

Profiles use local[2], with 8 partitions for smoke and 64 for standard. Reused DataFrames use
MEMORY_AND_DISK and are unpersisted after execution. The generator expands 12 customer-months
before bounded slots, instead of enumerating every possible customer/day/transaction opportunity.
The standard profile is intended for several million transactions; actual counts depend on seed
and configuration. The verified modelling scale is 25,000 customers / 1,280,055 transactions. The 100,000-customer
attempt exhausted Java heap during readback; no successful full-scale claim is supported.

To explore 500,000 customers, copy the standard TOML and increase customers and partitions for
the available memory. For 10M+ events, prefer the native Spark writer on a suitable environment;
the transformation API remains distributed. These are extension points, not verified benchmarks.

Validation uses distributed distinct counts, anti-joins and aggregates, with real shuffle costs.
Stage 1 validation collects treatment-arm rows and single-row aggregates. Stage 2/3 additionally
collect bounded customer-level feature arrays (up to 120,000 customers), never full transaction
histories.
Order-independent summed row hashes diagnose roundtrip/repeat differences, but are not collision-free
content proofs. Small integration fixtures use exact exceptAll equality. Integer monetary moments
avoid partition-order differences in variability features; cross-platform JVM math can still vary
slightly, so retain the recorded stack for exact reproduction.

## Tests and errors

```bat
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration" --basetemp=data/test-unit-tmp
python -m pytest -q -m integration --basetemp=data/test-spark-tmp
```

Data integration tests use actual Spark. Assistant tests mock Ollama and do not establish live
model reliability. Local sockets/JVM subprocesses must be allowed.
A restricted sandbox blocked initial process startup/temp-file operations; final integration runs
use local process permissions and explicit workspace temporary paths. This is not cloud execution.

Structural errors fail the command. Statistical warnings are reported and never trigger seed
selection. Output paths must be new: failed runs retain partial data without `_SUCCESS`. The
standalone validator reads saved configuration and checks stored records. There is no automatic
recursive deletion or overwrite. Pytest owns and cleans its specified temporary directories.

## References

- [Apache Spark installation](https://spark.apache.org/docs/4.2.0/api/python/getting_started/install.html)
- [Apache Arrow Parquet row groups](https://arrow.apache.org/docs/python/parquet/parquet.html)
- [Hadoop Windows filesystem notes](https://cwiki.apache.org/confluence/display/HADOOP2/WindowsProblems)

Documentation support and verified operations are different claims; a successful range count
does not establish working file I/O. See the completion report for measured checks and limitations.
