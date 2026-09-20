from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

import psutil

from q0.corpus import (
    CorpusValidationError,
    GoldValidationError,
    fetch_corpus,
    load_manifest,
    summary_json,
    validate_gold,
)
from q0.models import EnvironmentResult, ThresholdOutcome, write_json_atomic

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


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or str(error)
        raise CommandError(f"git {' '.join(arguments)} failed: {detail}") from error
    return completed.stdout.strip()


def _handle_corpus_fetch(args: argparse.Namespace) -> int:
    manifest = fetch_corpus(args.root)
    print(
        json.dumps(
            {
                "papers": len(manifest.papers),
                "paper_ids": [paper.paper_id for paper in manifest.papers],
                "page_counts": {
                    paper.paper_id: paper.page_count for paper in manifest.papers
                },
                "valid": True,
            },
            sort_keys=True,
        )
    )
    return 0


def _handle_gold_validate(args: argparse.Namespace) -> int:
    print(summary_json(validate_gold(args.root)))
    return 0


def _environment_files(root: Path) -> list[Path]:
    results = root / "qualification" / "results"
    return sorted(results.glob("*/environment.json")) if results.exists() else []


def _handle_init_run(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    existing = _environment_files(root)
    if existing:
        raise CommandError(
            "a Q0 run is already initialized: " + ", ".join(str(path) for path in existing)
        )

    tracked_status = _git(root, "status", "--porcelain=v1", "--untracked-files=no")
    if tracked_status:
        raise CommandError("tracked tree must be clean before initializing a run")
    revision = _git(root, "rev-parse", "HEAD")

    validation_summary = validate_gold(root)
    manifest_path = root / "qualification" / "corpus" / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_manifest(root)

    initialized_at = datetime.now(timezone.utc)
    run_id = f"q0-{initialized_at.strftime('%Y%m%dT%H%M%SZ')}-{revision[:7]}"
    macos_version = platform.mac_ver()[0]
    os_version = f"macOS {macos_version}" if macos_version else platform.platform()
    environment = EnvironmentResult(
        run_id=run_id,
        initialized_at_utc=initialized_at,
        run_initialized_git_revision=revision,
        producer_git_revision=revision,
        tracked_tree_clean=True,
        os_version=os_version,
        architecture=platform.machine(),
        physical_memory_bytes=psutil.virtual_memory().total,
        corpus_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        pdf_sha256={paper.paper_id: paper.sha256 for paper in manifest.papers},
        python_version=platform.python_version(),
        identities={
            "corpus_artifact_version": manifest.artifact_version,
            "corpus_paper_ids": [paper.paper_id for paper in manifest.papers],
            "git_revision": revision,
        },
        measurements=validation_summary,
        threshold_outcomes={
            "tracked_tree_clean": ThresholdOutcome(
                passed=True,
                requirement="tracked tree is clean at run initialization",
                observed=True,
            ),
            "corpus_valid": ThresholdOutcome(
                passed=True,
                requirement="fixed corpus and independent gold validation pass",
                observed=validation_summary,
            ),
        },
    )
    output_path = root / "qualification" / "results" / run_id / "environment.json"
    write_json_atomic(output_path, environment)

    private_id_path = root / "qualification" / "private" / "run-id.txt"
    private_id_path.parent.mkdir(parents=True, exist_ok=True)
    temp_private = private_id_path.with_name(f".{private_id_path.name}.tmp")
    temp_private.write_text(f"{run_id}\n", encoding="utf-8")
    with open(temp_private, "r", encoding="utf-8") as f:
        os.fsync(f.fileno())
    os.replace(temp_private, private_id_path)
    dir_fd = os.open(private_id_path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)

    print(run_id)
    return 0


def _handle_run_id(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    private_id_path = root / "qualification" / "private" / "run-id.txt"
    private_run_id: str | None = None
    if private_id_path.is_file():
        private_run_id = private_id_path.read_text(encoding="utf-8").strip()

    environment_files = _environment_files(root)
    if len(environment_files) != 1:
        raise CommandError(
            f"expected exactly one initialized run, observed {len(environment_files)}"
        )
    try:
        environment = EnvironmentResult.model_validate_json(
            environment_files[0].read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as error:
        raise CommandError(
            f"invalid environment result {environment_files[0]}: {error}"
        ) from error

    if private_run_id is not None and private_run_id != environment.run_id:
        raise CommandError(
            f"private run ID '{private_run_id}' does not match environment run ID '{environment.run_id}'"
        )

    print(environment.run_id)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="q0",
        description="Temporary balanced technical-qualification probe",
    )
    commands = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    init_run = commands.add_parser("init-run", help="initialize one qualification run")
    _add_root_argument(init_run)
    init_run.set_defaults(handler=_handle_init_run)

    run_id = commands.add_parser("run-id", help="print the initialized run ID")
    _add_root_argument(run_id)
    run_id.set_defaults(handler=_handle_run_id)

    corpus = commands.add_parser("corpus", help="manage the fixed two-paper corpus")
    corpus_commands = corpus.add_subparsers(
        dest="corpus_command", metavar="COMMAND", required=True
    )
    corpus_fetch = corpus_commands.add_parser(
        "fetch", help="fetch and identify the corpus"
    )
    _add_root_argument(corpus_fetch)
    corpus_fetch.set_defaults(handler=_handle_corpus_fetch)

    gold = commands.add_parser("gold", help="validate independent gold annotations")
    gold_commands = gold.add_subparsers(
        dest="gold_command", metavar="COMMAND", required=True
    )
    gold_validate = gold_commands.add_parser(
        "validate", help="validate frozen gold annotations"
    )
    _add_root_argument(gold_validate)
    gold_validate.set_defaults(handler=_handle_gold_validate)

    for name in ("parser", "embedding", "generation", "proof"):
        future = commands.add_parser(name, help=f"run the {name} qualification stage")
        future.set_defaults(handler=_not_implemented)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Handler = args.handler
    try:
        return handler(args)
    except (CommandError, CorpusValidationError, GoldValidationError) as error:
        print(f"q0: error: {error}", file=sys.stderr)
        return 2
