from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

Handler = Callable[[argparse.Namespace], int]


class CommandError(RuntimeError):
    pass


def _not_implemented(_: argparse.Namespace) -> int:
    raise CommandError("command is not implemented yet")


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("../.."),
        help="repository root (default: ../..)",
    )


def _handle_init_run(args: argparse.Namespace) -> int:
    from q0.baseline import initialize_run

    run_id = initialize_run(args.root)
    print(run_id)
    return 0


def _handle_run_id(args: argparse.Namespace) -> int:
    from q0.baseline import discover_q01_run_id

    print(discover_q01_run_id(args.root))
    return 0


def _handle_baseline_prepare(args: argparse.Namespace) -> int:
    from q0.baseline import prepare_baseline

    summary = prepare_baseline(root=args.root, run_id=args.run_id)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _handle_hybrid_preflight(args: argparse.Namespace) -> int:
    from q0.hybrid import run_hybrid_preflight

    summary = run_hybrid_preflight(root=args.root, run_id=args.run_id)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _handle_hybrid_run(args: argparse.Namespace) -> int:
    from q0.hybrid import run_hybrid_measurement

    summary = run_hybrid_measurement(root=args.root, run_id=args.run_id)
    print(json.dumps(summary, sort_keys=True))
    return 0


def _handle_hybrid_evaluate(args: argparse.Namespace) -> int:
    from q0.hybrid import evaluate_hybrid_measurement

    summary = evaluate_hybrid_measurement(root=args.root, run_id=args.run_id)
    if summary.get("passed") is not True:
        failure_reasons = summary.get("failure_reasons")
        detail = (
            "; ".join(str(reason) for reason in failure_reasons)
            if isinstance(failure_reasons, list) and failure_reasons
            else "unspecified gate failure"
        )
        raise CommandError(f"hybrid gate failed: {detail}")
    print(json.dumps(summary, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q01",
        description="Temporary Q0.1 hybrid technical-qualification probe",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    init_run = commands.add_parser("init-run", help="initialize one Q0.1 run")
    _add_root_argument(init_run)
    init_run.set_defaults(handler=_handle_init_run)

    run_id = commands.add_parser("run-id", help="print the initialized Q0.1 run ID")
    _add_root_argument(run_id)
    run_id.set_defaults(handler=_handle_run_id)

    baseline = commands.add_parser("baseline", help="rebuild the inherited baseline")
    baseline_commands = baseline.add_subparsers(
        dest="baseline_command", metavar="COMMAND", required=True
    )
    baseline_prepare = baseline_commands.add_parser(
        "prepare", help="verify and regenerate exact baseline inputs"
    )
    baseline_prepare.add_argument("--run-id", required=True)
    _add_root_argument(baseline_prepare)
    baseline_prepare.set_defaults(handler=_handle_baseline_prepare)

    hybrid = commands.add_parser("hybrid", help="run hybrid retrieval qualification")
    hybrid_commands = hybrid.add_subparsers(
        dest="hybrid_command", metavar="COMMAND", required=True
    )
    for name, help_text, handler in (
        ("preflight", "verify fixed BGE and Qdrant identities", _handle_hybrid_preflight),
        ("run", "measure the fixed dense + BM25 + RRF configuration", _handle_hybrid_run),
        ("evaluate", "apply the complete Track B-H gate", _handle_hybrid_evaluate),
    ):
        hybrid_command = hybrid_commands.add_parser(name, help=help_text)
        hybrid_command.add_argument("--run-id", required=True)
        _add_root_argument(hybrid_command)
        hybrid_command.set_defaults(handler=handler)

    for name in ("generation", "proof"):
        future = commands.add_parser(name, help=f"run the {name} qualification stage")
        future.set_defaults(handler=_not_implemented)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(args)
    except (CommandError, ValueError) as error:
        print(f"q01: error: {error}", file=sys.stderr)
        return 2
