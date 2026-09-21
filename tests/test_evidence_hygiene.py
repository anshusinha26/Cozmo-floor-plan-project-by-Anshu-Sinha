"""Guards on committed evidence directories.

Snapshots under fix_loop/ are evidence for a comparison made at a point in
time. Nothing that runs later may quietly add to them, and nothing produced by
the stub pipeline may be presented as a benchmark result. Both mistakes are
invisible on inspection of a diff, so they are checked here instead.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
STUB_MARKER = "STUB PIPELINE"


def _loop1_ids() -> set[str]:
    reg = yaml.safe_load((ROOT / "fix_loop" / "captures_loop1.yaml").read_text(encoding="utf-8"))
    return {c["capture_id"] for c in reg["captures"]}


@pytest.mark.parametrize("side", ["before", "after"])
def test_loop1_snapshot_holds_only_loop1_captures(side: str) -> None:
    """A snapshot that grew a capture is a snapshot of nothing.

    Loop 1 compared two room segmentations across the captures that existed
    then. A later benchmark sweep that reads the live registry would drop new
    runs into fix_loop/<side>/ and change what the loop appears to have
    measured, without touching a single line of its write-up.
    """
    runs = ROOT / "fix_loop" / side / "bench" / "runs"
    if not runs.is_dir():
        pytest.skip(f"fix_loop/{side} has not been regenerated in this checkout")
    assert {d.name for d in runs.iterdir() if d.is_dir()} == _loop1_ids()


def test_loop1_regenerate_reads_the_pinned_registry() -> None:
    """The pin is the mechanism; without it the snapshot test only finds the damage later."""
    text = (ROOT / "fix_loop" / "regenerate.sh").read_text(encoding="utf-8")
    assert "fix_loop/captures_loop1.yaml" in text
    assert "--set benchmarks/captures.yaml" not in text


def _plans(root: Path):
    return sorted(root.rglob("plan.json"))


def test_no_stub_plan_is_published_as_a_benchmark_result() -> None:
    """The stub emits a fixed shape with no reconstruction behind it.

    It exists so the contract and the runner can be tested without weights.
    A stub plan sitting in docs/benchmark reads as a measured result, which
    would make every table containing it a lie.
    """
    docs = ROOT / "docs" / "benchmark"
    if not docs.is_dir():
        pytest.skip("docs/benchmark is not present in this checkout")
    offenders = [
        p.relative_to(ROOT)
        for p in _plans(docs)
        if any(STUB_MARKER in w for w in json.loads(p.read_text(encoding="utf-8")).get("warnings", []))
    ]
    assert offenders == []


def test_loop1_snapshots_do_not_leak_into_the_benchmark_directory() -> None:
    """Loop 1 ran the synthetic EXAMPLE fixtures; they belong to the loop, not the benchmark."""
    docs = ROOT / "docs" / "benchmark" / "runs"
    if not docs.is_dir():
        pytest.skip("docs/benchmark/runs is not present in this checkout")
    assert not {d.name for d in docs.iterdir() if d.is_dir()} & {"EXAMPLE", "EXAMPLE_REPEAT"}


def test_the_benchmark_report_does_not_list_the_stub_fixtures() -> None:
    """A row naming a capture reads as a result, even when its plan cell is empty.

    The EXAMPLE fixtures are placeholder files with a stub pipeline behind
    them. Listing them in the published benchmark invites a reader to count
    them among the captures the tiers were measured on.
    """
    report = ROOT / "docs" / "benchmark" / "benchmark.md"
    if not report.is_file():
        pytest.skip("docs/benchmark/benchmark.md is not present in this checkout")
    # Prose may name them to explain the exclusion; a table row may not, because
    # a row is read as a capture the tiers were scored on.
    rows = [ln for ln in report.read_text(encoding="utf-8").splitlines() if ln.startswith("|")]
    assert [ln for ln in rows if "EXAMPLE" in ln] == []


def _tracked(path: Path) -> bool:
    """Whether git tracks this path. A file that exists but is ignored is not evidence."""
    import subprocess

    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))],
                       cwd=ROOT, capture_output=True)
    return r.returncode == 0


def _benchmark_captures_with_plans() -> list[str]:
    """Capture ids the benchmark's provenance says it has a plan for."""
    prov = ROOT / "docs" / "benchmark" / "provenance.json"
    if not prov.is_file():
        return []
    rows = json.loads(prov.read_text(encoding="utf-8"))
    rows = rows if isinstance(rows, list) else rows.get("provenance", [])
    return [r["capture_id"] for r in rows if r.get("source") not in (None, "no plan available")]


def test_every_benchmark_capture_with_a_plan_has_that_plan_tracked() -> None:
    """Tables without their plans are numbers nobody can check.

    `runs/` is ignored repo-wide, which silently swallowed the benchmark's own
    output for a long time: the report named captures whose plan.json existed
    only on the machine that built it.
    """
    import subprocess

    if subprocess.run(["git", "rev-parse"], cwd=ROOT, capture_output=True).returncode != 0:
        pytest.skip("not a git checkout")
    missing = []
    for capture_id in _benchmark_captures_with_plans():
        for name in ("plan.json", "plan.png", "run_manifest.json"):
            f = ROOT / "docs" / "benchmark" / "runs" / capture_id / name
            if not (f.is_file() and _tracked(f)):
                missing.append(f"{capture_id}/{name}")
    assert missing == []
