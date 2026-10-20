"""Local assistant commands, deliberately independent of Spark imports."""

import argparse
import json

from pydantic import ValidationError

from .contracts import AssistantError, ExplainRequest
from .engine import ExplanationEngine
from .evidence import EvidenceStore
from .ollama import OllamaAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    explain = sub.add_parser("explain")
    explain.add_argument("question")
    explain.add_argument("--scenario", default="base")
    explain.add_argument("--compare-scenario")
    explain.add_argument("--mode", choices=["deterministic", "ollama"], default="deterministic")
    explain.add_argument("--strategy", choices=["basic", "bound"], default="bound")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--output", required=True, help="A new directory; never overwritten")
    evaluation.add_argument(
        "--modes",
        nargs="+",
        choices=["deterministic", "basic", "bound"],
        default=["deterministic", "basic", "bound"],
    )
    recover = sub.add_parser("summarize")
    recover.add_argument(
        "--input", required=True, help="Evaluation directory with saved rows and configuration"
    )
    args = parser.parse_args()
    try:
        if args.command == "serve":
            import uvicorn

            uvicorn.run(
                "retention_uplift.assistant.api:create_app",
                factory=True,
                host="127.0.0.1",
                port=args.port,
            )
        elif args.command == "summarize":
            from .evaluate import summarize_saved

            print(json.dumps(summarize_saved(args.input), indent=2))
        elif args.command == "evaluate":
            from .evaluate import evaluate

            print(json.dumps(evaluate(args.output, args.modes), indent=2))
        else:
            adapter = OllamaAdapter() if args.mode == "ollama" else None
            try:
                result = ExplanationEngine(EvidenceStore(), adapter).explain(
                    ExplainRequest(
                        question=args.question,
                        scenario=args.scenario,
                        compare_scenario=args.compare_scenario,
                        mode=args.mode,
                        strategy=args.strategy,
                    )
                )
                print(result.model_dump_json(indent=2))
            finally:
                if adapter:
                    adapter.close()
    except AssistantError as exc:
        parser.exit(1, exc.body.model_dump_json() + "\n")
    except ValidationError:
        parser.exit(
            1, "Invalid request. Use an approved scenario and a 3–1000 character question.\n"
        )
    except FileExistsError:
        parser.exit(
            1, "Choose a new output directory; existing evaluation results are not overwritten.\n"
        )


if __name__ == "__main__":
    main()
