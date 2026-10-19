"""Cross-platform CLI; executable with python -m retention_uplift.cli."""

import argparse
import json
from pathlib import Path

from retention_uplift.config import Config, Mechanism
from retention_uplift.pipeline import run
from retention_uplift.spark import session
from retention_uplift.storage import read_tables
from retention_uplift.validation import validate_tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("--config", type=Path, default=Path("configs/smoke.toml"))
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--writer", choices=("auto", "portable", "spark"), default="auto")
    validate = commands.add_parser("validate")
    validate.add_argument("--input", type=Path, required=True)
    stage2 = commands.add_parser("run-stage2")
    stage2.add_argument("--input", type=Path, required=True)
    stage2.add_argument("--output", type=Path, required=True)
    stage2.add_argument("--bootstrap", type=int, default=1000)
    args = parser.parse_args()
    if args.command == "generate":
        config = Config.read(args.config)
    else:
        raw = json.loads((args.input / "config.json").read_text(encoding="utf-8"))
        raw["mechanism"] = Mechanism(**raw["mechanism"])
        config = Config(**raw)
    spark = session(config)
    try:
        if args.command == "run-stage2":
            from retention_uplift.stage2 import run_stage2

            report = run_stage2(spark, args.input, args.output, args.bootstrap)
            print(json.dumps(report, indent=2))
            return
        report = (
            run(spark, config, args.output, args.writer)
            if args.command == "generate"
            else validate_tables(read_tables(spark, args.input), config)
        )
        print(json.dumps(report, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
